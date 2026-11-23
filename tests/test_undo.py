"""v0.19.0: a stopped or failed task's file changes can be undone - only files still exactly as the task left them."""
import asyncio

from app.tools import undo
from app.tools.registry import TOOLS, ToolContext


def _ctx(root, sdir, run="run1"):
    return ToolContext("t", root, "full", asyncio.Event(), session_dir=sdir, owner=f"abc123:{run}")


def test_undo_puts_back_edits_new_files_and_deletes(tmp_path):
    root, sdir = tmp_path / "work", tmp_path / "rec"
    root.mkdir()
    (root / "keep.txt").write_text("original\n", encoding="utf-8")
    (root / "gone.txt").write_text("will be deleted\n", encoding="utf-8")
    (root / "user.txt").write_text("v1\n", encoding="utf-8")
    ctx = _ctx(root, sdir)
    run = lambda name, args, body="": asyncio.run(TOOLS[name].fn(ctx, args, body))  # noqa: E731
    assert run("write_file", {"path": "keep.txt"}, "changed by the task\n").ok
    assert run("edit_file", {"path": "keep.txt", "old": "changed", "new": "edited"}).ok  # second change, same file
    assert run("write_file", {"path": "new/made.txt"}, "new file\n").ok
    assert run("delete_file", {"path": "gone.txt"}).ok
    assert run("write_file", {"path": "user.txt"}, "v2 by the task\n").ok
    (root / "user.txt").write_text("v3 by the user\n", encoding="utf-8")  # changed after the task
    assert sorted(undo.changed_files(sdir, "run1")) == ["gone.txt", "keep.txt", "new/made.txt", "user.txt"]

    res = undo.restore(sdir, root, "run1")
    assert (root / "keep.txt").read_text(encoding="utf-8") == "original\n"
    assert (root / "gone.txt").read_text(encoding="utf-8") == "will be deleted\n"
    assert not (root / "new" / "made.txt").exists()
    assert (root / "user.txt").read_text(encoding="utf-8") == "v3 by the user\n"  # the user's change is kept
    assert sorted(res["restored"]) == ["gone.txt", "keep.txt"] and res["removed"] == ["new/made.txt"]
    assert [s["path"] for s in res["skipped"]] == ["user.txt"]
    # undone once: nothing left to undo
    assert undo.changed_files(sdir, "run1") == []


def test_only_the_last_tasks_are_kept(tmp_path):
    root, sdir = tmp_path / "w", tmp_path / "r"
    root.mkdir()
    for i in range(undo.KEEP + 3):
        asyncio.run(TOOLS["write_file"].fn(_ctx(root, sdir, f"run{i:02d}"), {"path": f"f{i}.txt"}, "x\n"))
    kept = sorted(p.name for p in (sdir / "undo").iterdir())
    assert len(kept) == undo.KEEP and kept[-1] == f"run{undo.KEEP + 2:02d}"
