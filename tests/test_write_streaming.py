"""Long files streamed by a model: written live into the real path, saved and continued after a break without ever
becoming two documents in one, the provider's request time limit learned, native calls only where they stream.
Run: python -m pytest tests/test_write_streaming.py"""
import asyncio
import types
from pathlib import Path

from app.agents.continuity import _live_write, cap_chars, _split_rule
from app.llm import router
from app.tools.file_tools import live_restore, starts_over, trim_overlap
from app.tools.registry import TOOLS, ToolContext

HTML_A = ("<!DOCTYPE html>\n<html lang=\"tr\">\n<head>\n<meta charset=\"utf-8\">\n<title>Neon</title>\n<style>body{margin:0}"
          "</style>\n</head>\n<body>\n<canvas id=\"c\"></canvas>\n<script>\nconst W = 390, H = 844;\n"
          "function spawnParticle(x, y) { return { x, y, life: 1 }; }\n")


def _ctx(root: Path) -> ToolContext:
    return ToolContext("t", root, "full", asyncio.Event())


def _write(ctx, **args):
    body = args.pop("body")
    return asyncio.run(TOOLS["write_file"].fn(ctx, args, body))


def test_restart_is_recognised():
    assert starts_over(HTML_A, "<!DOCTYPE html>\n<html lang=\"en\">\n<head><title>Other</title>")
    assert not starts_over(HTML_A, "function update(dt) { return dt; }\n</script>\n</body>\n</html>\n")


def test_overlap_is_trimmed():
    rest, n = trim_overlap(HTML_A, "function spawnParticle(x, y) { return { x, y, life: 1 }; }\nfunction next() {}\n")
    assert rest == "function next() {}\n" and n > 40


def test_append_that_starts_the_file_over_replaces_it(tmp_path):
    # A model told to continue after a break wrote the whole page again with append=true: it used to become two
    # <!DOCTYPE html> in one file (a broken game).
    ctx = _ctx(tmp_path)
    (tmp_path / "index.html").write_text(HTML_A, encoding="utf-8")
    ctx.files_changed.append("index.html")
    again = HTML_A.replace("Neon", "Neon Drift") + "function update() {}\n</script>\n</body>\n</html>\n"
    res = _write(ctx, path="index.html", append="true", body=again)
    text = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert res.ok and text.count("<!DOCTYPE html>") == 1 and "Neon Drift" in text and "REPLACED" in res.output


def test_plain_write_after_a_saved_part_continues_or_replaces(tmp_path):
    ctx = _ctx(tmp_path)
    (tmp_path / "index.html").write_text(HTML_A, encoding="utf-8")
    ctx.salvaged = {"index.html": HTML_A}
    res = _write(ctx, path="index.html", body="function update(dt) { return dt; }\n</script>\n</body>\n</html>\n")
    text = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert res.ok and text.startswith("<!DOCTYPE html>") and text.rstrip().endswith("</html>")  # appended
    ctx.salvaged = {"index.html": text}
    _write(ctx, path="index.html", body=HTML_A.replace("Neon", "Neo") + "</script></body></html>\n")
    assert (tmp_path / "index.html").read_text(encoding="utf-8").count("<!DOCTYPE html>") == 1  # replaced


def test_live_write_and_restore(tmp_path):
    ctx = _ctx(tmp_path)
    run = types.SimpleNamespace(live_ctx=ctx)
    _live_write(run, ("write_file", {"path": "game.js", "content": "const a = 1;\nconst b = 2;\nconst c"}, False))
    assert (tmp_path / "game.js").read_text(encoding="utf-8") == "const a = 1;\nconst b = 2;\n"  # whole lines only
    res = _write(ctx, path="game.js", body="const a = 1;\nconst b = 2;\nconst c = 3;\n")
    assert res.ok and "created" in res.output  # a new file, written once
    assert (tmp_path / "game.js").read_text(encoding="utf-8").endswith("const c = 3;\n")
    # an existing project file that this task did not write is never replaced before its call has finished
    (tmp_path / "keep.css").write_text("body{}", encoding="utf-8")
    _live_write(run, ("write_file", {"path": "keep.css", "content": "x{}\n"}, False))
    assert (tmp_path / "keep.css").read_text(encoding="utf-8") == "body{}"
    # a refused / broken call leaves nothing half-written
    _live_write(run, ("write_file", {"path": "tmp/new.js", "content": "let x = 1;\n"}, False))
    assert live_restore(ctx, tmp_path / "tmp" / "new.js") and not (tmp_path / "tmp" / "new.js").exists()


def test_request_cap_is_learned_per_provider():
    assert router.request_cap("nvidia:a") is None
    router.note_request_break("nvidia:a", 287)
    assert router.request_cap("nvidia:a") is None  # one break at an odd time is chance
    router.note_request_break("nvidia:b", 279)  # another model of the same provider at about the same time
    assert router.request_cap("nvidia:c") == 279  # the provider's limit, for all its models
    router.note_request_break("groq:x", 301)  # right at a round gateway limit: known at once
    assert router.request_cap("groq:y") == 300
    router._CAPS["nvidia"]["cap"] = 300
    secs, chars = cap_chars("nvidia:c", 35)
    assert secs == 300 and 15000 <= chars <= 30000
    rule = _split_rule(True, "nvidia:c", 35)
    assert "append=true" in rule and "300 s" in rule
    assert "ONE call" in _split_rule(True, "evren:x", 35)


def test_native_calls_only_where_they_stream():
    assert router.streams_tool_args("evren:qwen")
    assert not router.streams_tool_args("nvidia:nvidia/nemotron-3.5-super")
