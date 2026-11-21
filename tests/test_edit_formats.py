"""edit_file accepts every edit shape models send: aider blocks and their variants, old/new under other names, a
JSON list, a unified diff, or the whole new text; nothing given says what is expected."""
import asyncio

from app.tools.registry import TOOLS, ToolContext

ORIGINAL = "<html>\n<head><title>A</title></head>\n<body>\n<h1>Old</h1>\n</body>\n</html>\n"


def run(tmp_path, args, body=""):
    f = tmp_path / "p.html"
    f.write_text(ORIGINAL, encoding="utf-8")
    res = asyncio.run(TOOLS["edit_file"].fn(ToolContext("t", tmp_path, "full", asyncio.Event()), {"path": "p.html", **args}, body))
    return res, f.read_text(encoding="utf-8")


def test_aider_block_and_variants(tmp_path):
    for body in ("<<<<<<< SEARCH\n<h1>Old</h1>\n=======\n<h1>New</h1>\n>>>>>>> REPLACE",
                 "<<<< ORIGINAL\n<h1>Old</h1>\n====\n<h1>New</h1>\n>>>> UPDATED",
                 "```\n<<<<<<< SEARCH\n<h1>Old</h1>\n=======\n<h1>New</h1>\n>>>>>>> REPLACE\n```"):
        res, text = run(tmp_path, {}, body)
        assert res.ok and "<h1>New</h1>" in text, body


def test_other_argument_names(tmp_path):
    for a in ({"old_string": "<h1>Old</h1>", "new_string": "<h1>New</h1>"},
              {"search": "<h1>Old</h1>", "replace": "<h1>New</h1>"}):
        res, text = run(tmp_path, a)
        assert res.ok and "<h1>New</h1>" in text


def test_json_list_and_unified_diff(tmp_path):
    res, text = run(tmp_path, {}, '[{"old": "<h1>Old</h1>", "new": "<h1>New</h1>"}]')
    assert res.ok and "<h1>New</h1>" in text
    diff = "--- a/p.html\n+++ b/p.html\n@@ -3,3 +3,3 @@\n <body>\n-<h1>Old</h1>\n+<h1>New</h1>\n </body>\n"
    res, text = run(tmp_path, {}, diff)
    assert res.ok and "<h1>New</h1>" in text


def test_whole_new_text_is_taken_as_the_content(tmp_path):
    res, text = run(tmp_path, {}, ORIGINAL.replace("Old", "Brand new"))
    assert res.ok and "Brand new" in text


def test_snippet_retyped_from_memory_still_lands_in_the_one_close_place():
    from app.tools.editing import apply_edit
    text = "CREATE TABLE t (\n    id INTEGER,\n    priority VARCHAR(20) CHECK(priority IN ('Low', 'High')) DEFAULT 'Low',\n" \
           "    status TEXT\n);\n"
    old = "    id INTEGER,\n    priority VARCHAR(20) CHECK(priority IN (\"Low\",\"High\")) DEFAULT 'Low',"
    out, n = apply_edit(text, old, "    id INTEGER,\n    priority TEXT,")
    assert n == 1 and "priority TEXT," in out and "status TEXT" in out


def test_whitespace_inside_a_line_does_not_matter():
    from app.tools.editing import apply_edit
    assert apply_edit("a  =   1\nb = 2\n", "a = 1", "a = 5")[0].startswith("a = 5")


def test_a_plain_write_after_a_dropped_connection_continues_the_saved_part(tmp_path):
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    saved = "<?php\n// index\n" + "echo 'satir';\n" * 40
    (tmp_path / "index.php").write_text(saved, encoding="utf-8")
    ctx.salvaged = {"index.php": saved}
    res = asyncio.run(TOOLS["write_file"].fn(ctx, {"path": "index.php"}, "echo 'devam';\n?>\n"))
    text = (tmp_path / "index.php").read_text(encoding="utf-8")
    assert res.ok and text.startswith(saved) and text.rstrip().endswith("?>")
    # a complete rewrite (it starts like the saved file) replaces it as asked
    ctx.salvaged = {"index.php": text}
    asyncio.run(TOOLS["write_file"].fn(ctx, {"path": "index.php"}, saved + "?>\n"))
    assert (tmp_path / "index.php").read_text(encoding="utf-8") == saved + "?>\n"


def test_a_generation_loop_in_a_file_is_kept_once(tmp_path):
    from app.tools.editing import collapse_repeats
    block = '<script src="assets/js/app.js?v=2"></script>\n<script>initCalendar(document.body);</script>'
    text = "<html><body>\n" + "\n".join([block] * 300) + "\n</body></html>"
    out, removed = collapse_repeats(text)
    assert removed == 299 and out.count("initCalendar") == 1 and out.endswith("</html>")
    # short lines that really repeat stay
    ok = "<ul>\n" + "\n".join(["  <li></li>"] * 10) + "\n</ul>"
    assert collapse_repeats(ok) == (ok, 0)
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    res = asyncio.run(TOOLS["write_file"].fn(ctx, {"path": "i.html"}, text))
    assert res.ok and "generation loop" in res.output and (tmp_path / "i.html").read_text(encoding="utf-8").count("initCalendar") == 1


def test_nothing_usable_explains_the_format(tmp_path):
    res, _ = run(tmp_path, {})
    assert not res.ok and "SEARCH" in res.output


def test_matching_blocks_are_saved_and_failed_ones_come_back_with_the_file(tmp_path):
    body = ("<<<<<<< SEARCH\n<h1>Old</h1>\n=======\n<h1>New</h1>\n>>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\n<footer>never there at all</footer>\n=======\n<footer>x</footer>\n>>>>>>> REPLACE")
    res, text = run(tmp_path, {}, body)
    assert "<h1>New</h1>" in text  # the block that matched was kept
    assert not res.ok and "Edit 2 of 2 NOT applied" in res.output and "Current content of" in res.output
    res, text = run(tmp_path, {}, "<<<<<<< SEARCH\n<nav>gone</nav>\n=======\n<nav>x</nav>\n>>>>>>> REPLACE")
    assert not res.ok and text == ORIGINAL and "<title>A</title>" in res.output


def test_any_spelling_and_nesting_of_old_new(tmp_path):
    for args, body in (({"oldText": "<h1>Old</h1>", "newText": "<h1>New</h1>"}, ""),
                       ({"changes": [{"old_str": "<h1>Old</h1>", "new_str": "<h1>New</h1>"}]}, ""),
                       ({}, '{"replacements": [{"OldString": "<h1>Old</h1>", "NewString": "<h1>New</h1>"}]}')):
        res, text = run(tmp_path, args, body)
        assert res.ok and "<h1>New</h1>" in text, args
