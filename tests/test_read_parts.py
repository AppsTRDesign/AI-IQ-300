"""read_file returns whole lines up to its limit (never a cut in the middle) and names the next range; the same
unchanged range read again is answered from memory."""
import asyncio

from app.tools.registry import TOOLS, ToolContext


def read(ctx, **args):
    return asyncio.run(TOOLS["read_file"].fn(ctx, {"path": "a.php", **args}, ""))


def test_a_normal_file_comes_whole(tmp_path):
    (tmp_path / "a.php").write_text("\n".join(f"<p>line {i} " + "x" * 40 + "</p>" for i in range(240)), encoding="utf-8")
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    res = read(ctx)
    assert res.ok and "omitted" not in res.output and "line 239" in res.output and "line 0 " in res.output


def test_a_big_file_comes_in_whole_line_parts_with_the_next_range(tmp_path):
    (tmp_path / "a.php").write_text("\n".join(f"row {i} " + "y" * 90 for i in range(1000)), encoding="utf-8")
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    ctx.read_limit = 12000
    res = read(ctx)
    assert "omitted" not in res.output and "row 0 " in res.output
    head = res.output.split("\n")[0]
    assert "of 1000" in head and "the rest: read_file lines=" in head
    nxt = head.split("lines=")[1].rstrip("]")
    res2 = read(ctx, lines=nxt)
    first = int(nxt.split("-")[0]) - 1
    assert f"row {first} " in res2.output
    again = read(ctx, lines=res2.output.split("lines ")[1].split(" of")[0])
    assert "unchanged" in again.output
