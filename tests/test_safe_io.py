"""v0.19.0: safe file writes - per-file locks, atomic replace with read-back check and rollback, no lost update between
parallel agents, cut-off file parts that never end in a broken character."""
import asyncio

import pytest

from app.tools import safe_io
from app.tools.registry import TOOLS, ToolContext


def _ctx(root, agent="", owner="abc123:run1"):
    return ToolContext("t", root, "full", asyncio.Event(), owner=owner, agent=agent)


def _run(coro):
    return asyncio.run(coro)


def test_atomic_write_leaves_no_temp_and_returns_sha(tmp_path):
    f = tmp_path / "a" / "x.txt"
    sha = safe_io.atomic_write_text(f, "merhaba ğüşiöç\r\nline2")
    assert f.read_bytes() == "merhaba ğüşiöç\r\nline2".encode() and sha == safe_io.sha_file(f)
    assert not [p for p in f.parent.iterdir() if p.name.endswith(".aiiq-tmp")]


def test_failed_check_restores_previous_content(tmp_path, monkeypatch):
    f = tmp_path / "x.txt"
    f.write_text("old version", encoding="utf-8")
    monkeypatch.setattr(safe_io, "sha_file", lambda p: "not-the-same")
    with pytest.raises(safe_io.WriteError):
        safe_io.atomic_write_text(f, "new version")
    assert f.read_text(encoding="utf-8") == "old version"


def test_clean_tail_drops_broken_characters():
    assert safe_io.clean_tail("abc�") == "abc"
    assert safe_io.clean_tail("ab\ud83d") == "ab"  # half of an emoji's surrogate pair
    assert safe_io.clean_tail("tamam ✅") == "tamam ✅"


def test_parallel_agent_cannot_erase_anothers_change(tmp_path):
    a, b = _ctx(tmp_path, "Frontend"), _ctx(tmp_path, "Backend")
    w = TOOLS["write_file"].fn
    assert _run(w(a, {"path": "app.js"}, "const a = 1;\n")).ok
    _run(TOOLS["read_file"].fn(b, {"path": "app.js"}, ""))  # B has version 1
    assert _run(w(a, {"path": "app.js"}, "const a = 1;\nconst fromA = 2;\n")).ok  # A changes it again
    res = _run(w(b, {"path": "app.js"}, "const b = 1;\n"))  # B would overwrite A's new line
    assert not res.ok and "Frontend" in res.output and "read_file" in res.output
    assert "fromA" in (tmp_path / "app.js").read_text(encoding="utf-8")
    _run(TOOLS["read_file"].fn(b, {"path": "app.js"}, ""))  # after reading the new version B may write
    assert _run(w(b, {"path": "app.js"}, "const a = 1;\nconst fromA = 2;\nconst b = 1;\n")).ok
    # the same agent rewriting its own file is never refused
    assert _run(w(b, {"path": "app.js"}, "const all = 3;\n")).ok
    # a later task of the chat is not a parallel writer
    assert _run(w(_ctx(tmp_path, owner="abc123:run2"), {"path": "app.js"}, "const next = 4;\n")).ok


def test_concurrent_appends_and_edits_keep_every_change(tmp_path):
    (tmp_path / "log.txt").write_text("start\n", encoding="utf-8")
    (tmp_path / "cfg.py").write_text("".join(f"v{i} = 0\n" for i in range(12)), encoding="utf-8")

    async def go():
        ctxs = [_ctx(tmp_path, f"m{i}") for i in range(4)]
        appends = [TOOLS["write_file"].fn(ctxs[i % 4], {"path": "log.txt", "append": "true"}, f"part {i:02d}\n" + "x" * 50 + "\n")
                   for i in range(16)]
        edits = [TOOLS["edit_file"].fn(ctxs[i % 4], {"path": "cfg.py", "old": f"v{i} = 0", "new": f"v{i} = {i + 100}"}, "")
                 for i in range(12)]
        return await asyncio.gather(*appends, *edits)

    results = _run(go())
    assert all(r.ok for r in results), [r.output for r in results if not r.ok]
    log = (tmp_path / "log.txt").read_text(encoding="utf-8")
    assert all(f"part {i:02d}" in log for i in range(16))
    cfg = (tmp_path / "cfg.py").read_text(encoding="utf-8")
    assert all(f"v{i} = {i + 100}" in cfg for i in range(12))


def test_saved_part_after_a_break_is_clean_and_whole(tmp_path):
    from app.agents.continuity import save_partial
    (tmp_path / "page.html").write_text("<html>\n<body>\n" + "<p>x</p>\n" * 40, encoding="utf-8")
    cut = "<p>yeni bölüm</p>\n" * 20 + "<p>yarım karakter �"
    rel, n, mode = save_partial(tmp_path, "write_file", {"path": "page.html", "content": cut}, True)
    text = (tmp_path / "page.html").read_text(encoding="utf-8")
    assert mode == "appended" and "�" not in text and text.endswith("<p>yeni bölüm</p>\n")
    assert text.startswith("<html>\n<body>\n") and text.count("yeni bölüm") == 20
