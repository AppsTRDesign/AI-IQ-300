"""File tools: write_file, edit_file, read_file, read_document, list_dir, search_code, delete_file.

Split out of registry.py (round 2026-11-20). registry imports this module at its end and re-exports every name, so registry.X keeps working; import tools from registry, not from here."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from .. import approvals, policy
from ..config import LANG_DIR, load_settings
from ..process_manager import manager

from .registry import EMPTY_OK, PREVIEW_LIMIT, S, TEMP_NAME, ToolResult, _current_file_note, _path, _rel, _syntax_note, _text_of, app_placeholder, broken_chars_note, change_preview, clean_file_content, clip, garbled_path, gate, js_check, tool, with_charset  # noqa: F401
from .shell_tools import _did_you_mean, start

DOC_START = re.compile(r"(?i)\s*(<!doctype|<html\b|<\?php|<\?xml)")


def starts_over(old: str, new: str) -> bool:
    """`new` is the file written from its beginning again, not its next part: the same document opening (<!DOCTYPE,
    <html, <?php), the same first line, or its first lines found at the start of the file. A model told to continue
    after a break that rewrote everything was appended to the saved part: two documents in one file."""
    o, n = old.lstrip(), new.lstrip()
    if not o or not n:
        return False
    if DOC_START.match(n) and DOC_START.match(o):
        return True
    first = lambda s: next((ln.strip() for ln in s.splitlines() if ln.strip()), "")  # noqa: E731
    fo, fn = first(o), first(n)
    if len(fo) >= 12 and fo == fn:
        return True
    head = re.sub(r"\s+", "", n[:500])[:160]
    return len(head) >= 80 and head in re.sub(r"\s+", "", o[:4000])


def live_restore(ctx, target: Path) -> bool:
    """The file was being written live while its call streamed (continuity._live_write): it goes back to how it was
    before that call, so the finished call (or the saved part after a break) is written once, by the usual rules."""
    live = getattr(ctx, "live_files", None)
    if not live:
        return False
    key = str(Path(target).resolve())
    if key not in live:
        return False
    base = live.pop(key)
    try:
        if base is None:
            Path(target).unlink(missing_ok=True)
        else:
            Path(target).write_text(base, encoding="utf-8", newline="")
    except OSError:
        pass
    return True


def shrink_guard(ctx, target: Path, rel: str, content: str) -> str:
    """The file guard: a file this task wrote (or saved after a break) is never cut down by a plain rewrite without
    the model seeing what it would lose. Weak models forgot what they had written and "wrote it again" from the top
    after a break: 80K of a page became the few K of the new start. The first such write is refused with the file's
    real end shown; written again (the model has seen it and means it), it goes through and the old version is
    kept in .aiiq/backups."""
    old = _text_of(target) or ""
    ours = rel in (getattr(ctx, "files_changed", None) or []) or rel in (getattr(ctx, "salvaged", None) or {})
    if not ours or len(old) < 2000 or len(content) >= len(old) * 0.6:
        return ""
    seen = getattr(ctx, "shrink_seen", None)
    if seen is None:
        seen = ctx.shrink_seen = {}
    if seen.get(rel):
        seen.pop(rel)
        return ""  # asked once already: a deliberate smaller version
    seen[rel] = True
    lines = old.count("\n") + 1
    return (f"Not written (file guard): {rel} already has {len(old)} characters ({lines} lines) written in this task; "
            f"this write would replace it with {len(content)} characters and lose about {len(old) - len(content)}. "
            f"You may have forgotten what is already there. The file ends with:\n...{old[-1200:]}\n\n"
            "- To add what is missing: write_file append=true with ONLY the part after that end.\n"
            "- To change a part: edit_file with that part.\n"
            "- Only if a shorter file is really intended: send this same write_file again (the old version is kept "
            "in .aiiq/backups).")


def trim_overlap(old: str, new: str) -> tuple[str, int]:
    """A continuation that begins by repeating the end of the file (the model re-sent its last lines): the repeated
    part is dropped. Returns (new without the overlap, characters dropped)."""
    tail = old[-4000:]
    probe = new[:40]  # an overlap shorter than this is not worth guessing
    if len(probe) < 40:
        return repair_seam(old, new), 0
    idx = tail.rfind(probe)
    while idx != -1:
        ov = tail[idx:]
        if new.startswith(ov):
            return repair_seam(old, new[len(ov):].lstrip("\n") if ov.endswith("\n") else new[len(ov):]), len(ov)
        idx = tail.rfind(probe, 0, idx)
    return repair_seam(old, new), 0


_ORPHAN_CLOSE = re.compile(r"^[^<\n]{0,60}</([a-zA-Z][\w-]*)>[ \t]*\n?")
_BLOCK_START = re.compile(r"\s*<(h[1-6]|section|article|p|div)\b", re.I)


def repair_seam(old: str, new: str) -> str:
    """The joint of a markup file continued after a break. Seen live (a PDF report's source): the part after the
    break began with "content</h2>" - a fragment of a tag that was never opened - and started the next section while
    the table before it was still open, so the document rendered with a stray word and a broken table. The fragment
    is dropped and the open table / list is closed before the new section."""
    if "<" not in old[-4000:] or not new:
        return new
    last = old.rstrip("\n").rsplit("\n", 1)[-1].lower()
    m = _ORPHAN_CLOSE.match(new)
    if m and f"<{m.group(1).lower()}" not in last:
        new = new[m.end():]
    if _BLOCK_START.match(new):
        t = old[-8000:].lower()
        closing = ""
        for inner, outer in (("tbody", "table"), ("ul", None), ("ol", None)):
            if t.count(f"<{inner}") > t.count(f"</{inner}>"):
                closing += f"</{inner}>"
            if outer and t.count(f"<{outer}") > t.count(f"</{outer}>"):
                closing += f"</{outer}>"
        if closing:
            new = closing + "\n" + new
    return new


@tool("write_file", '<tool name="write_file" path="REL/PATH">full file content</tool>',
      "Create or overwrite a file (parent folders are created). Always write the COMPLETE file content in ONE call, "
      "however large (a whole web page, a full script): every extra call is a full model round trip. append=true adds "
      "to the end of an existing file (only to continue a file that was cut off).",
      {"path": S("File path relative to the working directory"), "content": S("Complete file content (or the next part with append)"),
       "append": {"type": "boolean", "description": "Add content to the end of the existing file (large files in parts)"}},
      main="content", required=("path", "content"))
async def write_file(ctx, args, body):
    guessed = ""
    if not str(args.get("path") or "").strip() and str(args.get("append", "")).lower() in ("true", "1", "yes") \
            and ctx.files_changed and body.strip():
        # A weak model continued a file in parts and left out the path of the next part (seen live: minutes of
        # admin.js content refused for "missing path"). An append can only mean the file being written: the latest one.
        from .verify import is_binary_name
        guessed = next((str(f) for f in reversed(ctx.files_changed) if not is_binary_name(Path(str(f)))), "")
        if guessed:
            args = {**args, "path": guessed}
    res = await _write_file(ctx, args, body)
    if guessed and res.ok:
        res.output = (f"(path was missing; appended to {guessed}, the file you were writing - always give path) "
                      + res.output)
    return res


async def _write_file(ctx, args, body):
    target = _path(ctx, args["path"])
    live_restore(ctx, target)  # what streamed in live is replaced by this finished call
    from .verify import is_binary_name, text_into_binary
    if is_binary_name(target):  # an .mp4/.png/.pdf/.docx made of text is a fake file with the right name
        if target.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            # The system's rule (SYSTEM_CONTRACT 3): pictures come from the picture tools only. The exact call is
            # shown; nothing is guessed or written for the model.
            folder = str(Path(args["path"]).parent).replace("\\", "/")
            subject = " ".join(w for w in re.split(r"[^A-Za-z]+", target.stem) if len(w) > 1) or "the page's subject"
            return ToolResult(False, f"Refused: {args['path']} is an image and write_file only writes text. Pictures "
                                     f"come from the picture tools: stock_photo query=\"{subject}, ...\" folder=\""
                                     f"{folder if folder != '.' else 'images'}\" count=N (real photos, several subjects "
                                     "in ONE call), or generate_image for a new picture. Then use the paths it returns.")
        return ToolResult(False, text_into_binary(target))
    op = {"tool": "write_file", "path": str(target), "sha": hashlib.sha256(body.encode()).hexdigest()[:16]}
    from .editing import MARKER_LINE, collapse_repeats
    if msg := app_placeholder(body, args["path"]):
        return ToolResult(False, msg)
    if msg := garbled_path(args["path"]):
        return ToolResult(False, msg)
    appending = str(args.get("append", "")).lower() in ("true", "1", "yes")
    if not body.strip() and not appending and target.name not in EMPTY_OK and not target.exists():
        # 0-byte placeholders (app-core-utils.txt, cart-icon-content.txt) were left in the project: a call whose
        # content went into an attribute or got lost. Nothing is created; the model sends the real content.
        return ToolResult(False, f"Not written: the content for {args['path']} is empty. Put the complete file text "
                                 "between the tags (<tool name=\"write_file\" path=\"...\">TEXT</tool>), not into an "
                                 "attribute; if the file is not needed, do not create it.")
    if len(MARKER_LINE.findall(body)) >= 2:
        return ToolResult(False, "Not written: the content holds SEARCH/REPLACE (=======) markers. To change part of "
                                 "an existing file use edit_file; write_file takes the final file text only.")
    content, looped = collapse_repeats(clean_file_content(body))
    content = with_charset(target, content)
    loop_note = (f" Warning: your content repeated the same block {looped} more times (a generation loop); it was "
                 "written once. Read the end of the file and continue it properly - never repeat a block.") if looped else ""
    existed = target.exists()
    salvaged = getattr(ctx, "salvaged", None) or {}
    rel0 = _rel(ctx, target)
    restart_note = ""
    if rel0 in salvaged and existed and str(args.get("append", "")).lower() not in ("true", "1", "yes"):
        salvaged.pop(rel0)
        if not starts_over(_text_of(target) or "", content):
            # The continuation of a file whose first part was saved after a dropped connection, sent as a plain
            # write: it goes after the saved part instead of replacing it.
            args = {**args, "append": "true"}
    elif rel0 in salvaged:
        salvaged.pop(rel0)  # continued the right way (append=true): later plain writes are ordinary again
    if str(args.get("append", "")).lower() in ("true", "1", "yes") and existed:
        old = target.read_bytes().decode("utf-8", errors="replace")
        if starts_over(old, content):
            # "Continuing" with the whole file from its first line again: appended, it became two documents in one
            # (two <!DOCTYPE html>, a broken page). It replaces the file instead.
            args = {k: v for k, v in args.items() if k != "append"}
            restart_note = (" Note: this content started the file from its beginning again, so it REPLACED the file "
                            "instead of being appended (two copies would have broken it). If it is only the first "
                            "part, continue with write_file append=true from its end - never start over.")
    if existed and str(args.get("append", "")).lower() not in ("true", "1", "yes"):
        if msg := shrink_guard(ctx, target, rel0, content):
            return ToolResult(False, msg)
    if str(args.get("append", "")).lower() in ("true", "1", "yes") and existed:
        if msg := await gate(ctx, {**op, "tool": "write_file"}, policy.decide_file_write(target, ctx.root, ctx.mode)):
            return ToolResult(False, msg)
        old = target.read_bytes().decode("utf-8", errors="replace")
        content, overlap = trim_overlap(old, content)
        if overlap:
            loop_note += (f" Note: the first {overlap} characters you sent repeated the end of the file; they were "
                          "added once.")
        joined = old + ("" if not old or old.endswith("\n") or content.startswith("\n") else "\n") + content
        # A loop across appends (the same block sent again and again after the file's end) is caught on the whole.
        joined, looped2 = collapse_repeats(joined)
        if looped2 and not looped:
            loop_note = (f" Warning: the appended part repeated a block already in the file ({looped2} times); it is "
                         "kept once. Read the end of the file and continue with what is really missing.")
        target.write_text(joined, encoding="utf-8", newline="")
        rel = _rel(ctx, target)
        ctx.files_changed.append(rel)
        added = content.count("\n") + (0 if content.endswith("\n") else 1)
        diff = "@@ appended @@\n" + "\n".join("+" + line for line in content.splitlines()[:4000])
        loop_note += broken_chars_note(content)
        return ToolResult(True, f"appended {len(content)} chars to {rel} (now {len(joined)} chars).{loop_note}",
                          {"path": rel, "language": target.suffix.lstrip("."), "created": False,
                           "added": added, "removed": 0, "diff": diff[:PREVIEW_LIMIT]})
    preview = lambda: change_preview("overwrite" if existed else "new", _text_of(target) if existed else None,  # noqa: E731
                                     content, _rel(ctx, target))
    rel = _rel(ctx, target)
    if existed and _text_of(target) == content:
        # The same file again with the same content (a model re-creating what it already wrote): nothing to do.
        return ToolResult(True, f"{rel} already has exactly this content; nothing was written. Do not write it again: "
                                "continue with the next step.", {"path": rel})
    again = existed and rel in ctx.files_changed
    if msg := await gate(ctx, op, policy.decide_file_write(target, ctx.root, ctx.mode), preview):
        return ToolResult(False, msg)
    # This write's own line changes (like an edit's), so the review card can add up every operation of the task.
    try:
        change = await asyncio.to_thread(change_preview, "overwrite" if existed else "new",
                                         _text_of(target) if existed else None, content, rel)
    except Exception:
        change = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    unread_rewrite = ""
    if existed and again and len(old_again := _text_of(target) or "") > 1500:
        # A file of this task written again in full: its previous version is kept too (the guard lets a deliberate
        # shorter version through; nothing written is ever lost without a copy).
        try:
            bdir = (ctx.session_dir or ctx.root / ".aiiq") / "backups"
            bdir.mkdir(parents=True, exist_ok=True)
            (bdir / f"{rel.replace('/', '__')}.{time.strftime('%Y%m%d-%H%M%S')}").write_text(old_again, encoding="utf-8")
        except OSError:
            pass
    if existed and not again:
        old_text = _text_of(target) or ""
        was_read = any(k.split("#")[0] == str(target.resolve()) for k in getattr(ctx, "read_seen", {}))
        old_lines = old_text.count("\n") + 1
        gone = int(change.get("removed") or 0)
        if len(old_text) > 1500:
            # The earlier version of a file this task did not write is kept, so a full rewrite never loses work.
            try:
                bdir = (ctx.session_dir or ctx.root / ".aiiq") / "backups"
                bdir.mkdir(parents=True, exist_ok=True)
                bpath = bdir / f"{rel.replace('/', '__')}.{time.strftime('%Y%m%d-%H%M%S')}"
                bpath.write_text(old_text, encoding="utf-8")
            except OSError:
                bpath = None
            if not was_read and gone > old_lines * 0.5:
                unread_rewrite = (f" Note: {rel} was replaced without reading it in this task and {gone} of its "
                                  f"{old_lines} lines are gone. Check that no feature of the old version was lost "
                                  "(forms, routes, data, scripts)" + (f"; the old version is kept at {bpath}" if bpath
                                                                      else "") + ".")
    target.write_text(content, encoding="utf-8", newline="")
    ctx.files_changed.append(rel)
    note = restart_note or ((" Note: this file was already written earlier in this task - for further changes use "
                             "edit_file with the changed part only; never recreate a finished file.") if again
                            else unread_rewrite)
    if js := await js_check(target):
        note += "\n" + js
    note += await _syntax_note(target) + broken_chars_note(content)
    if not existed and TEMP_NAME.search(target.name):
        # AndroidManifest.xml.tmp, themes.xml.tmpbad, tmp2.txt were written and deleted again in one task: two extra
        # calls each, and a project with stray files when the task broke off.
        note += (f"\nNote: {rel} looks like a temporary copy. Write the real file directly (edit_file for a change) "
                 "and delete this one with delete_file when you no longer need it - never leave it in the project.")
    return ToolResult(True, f"{'updated' if existed else 'created'} {rel} ({len(content)} chars).{note}{loop_note}",
                      {"path": rel, "language": target.suffix.lstrip("."), "created": not existed,
                       **({"diff": change["diff"], "added": change["added"], "removed": change["removed"]}
                          if change.get("diff") is not None and "added" in change else {})})


@tool("edit_file", '<tool name="edit_file" path="REL/PATH">\n<<<<<<< SEARCH\nexact lines from the file\n=======\nnew lines\n'
      '>>>>>>> REPLACE\n</tool>',
      "Change part of an existing file: replace an exact snippet (copied from the file, a few lines that occur once) "
      "with new text. Much faster than rewriting the whole file; several SEARCH/REPLACE blocks may follow each other. "
      "Use write_file only for new files or complete rewrites.",
      {"path": S("File path relative to the working directory"),
       "old": S("Exact text to replace, copied from the file (a few lines that occur once)"),
       "new": S("Replacement text (empty to delete the snippet)"),
       "replace_all": {"type": "boolean", "description": "Replace every occurrence instead of exactly one"},
       "edits": S("Alternative: one or more <<<<<<< SEARCH / ======= / >>>>>>> REPLACE blocks")},
      main="edits", required=("path",))
async def edit_file(ctx, args, body):
    from .editing import EditError, apply_edit, diff, parse_blocks
    target = _path(ctx, args["path"])
    if not target.is_file():
        return ToolResult(False, f"not found: {args['path']}. Use write_file to create a new file.")
    if msg := app_placeholder(body + json.dumps(args, ensure_ascii=False), args["path"]):
        # The real text goes with the refusal: told to "read_file it", a weak model read it and still copied the
        # shortened form from its memory, three times in a row.
        return ToolResult(False, msg + _current_file_note(target.read_bytes().decode("utf-8", errors="replace"), args["path"]))
    from .editing import LIST_KEYS, NEW_KEYS, OLD_KEYS, norm_key, pick
    # old/new under any of the names and spellings models use (old_string, oldText, search/replace, find/replace...)
    old_arg = pick(args, [k for k in OLD_KEYS if k != "content"])
    listed = next((v for k, v in args.items() if norm_key(k) in LIST_KEYS and v), None)
    pairs = [(old_arg, pick(args, [k for k in NEW_KEYS if k != "content"]) or "")] if old_arg \
        else parse_blocks(body or listed or "")
    before = target.read_bytes().decode("utf-8", errors="replace")  # bytes: keep the file's own line endings
    whole = (body or args.get("content") or "").strip("\n")
    if not pairs and whole and not re.search(r"<{3,}|>{3,}|^@@ ", whole, re.M) and \
            len(whole) >= 0.3 * len(before.strip()):
        # No markers at all, just the file as it should be (a weak model's "edit" was the complete new text; it
        # looped on "No edit given"): take it as the full new content, like write_file.
        pairs = [(before.replace("\r\n", "\n"), whole + ("\n" if before.endswith(("\n", "\r\n")) else ""))]
    if not pairs:
        got = (body or "").strip()[:160]
        return ToolResult(False, "No edit found. Send old= (exact text from the file) and new=, or SEARCH/REPLACE "
                                 "blocks:\n<<<<<<< SEARCH\nexact old lines\n=======\nnew lines\n>>>>>>> REPLACE\n"
                                 "For a complete rewrite use write_file." + (f" (received: {got!r})" if got else ""))
    crlf = "\r\n" in before
    text = before.replace("\r\n", "\n")
    replace_all = str(args.get("replace_all", "")).lower() in ("true", "1", "yes")
    done = 0
    failed: list[str] = []
    for i, (old, new) in enumerate(pairs, 1):
        try:
            text, n = apply_edit(text, old.replace("\r\n", "\n"), new.replace("\r\n", "\n"), replace_all)
        except EditError as e:
            # The blocks that match are kept (all-or-nothing made weak models rewrite whole files from memory);
            # the ones that do not are reported for a retry against the file as it is now.
            failed.append(f"Edit {i} of {len(pairs)} NOT applied: {e}" if len(pairs) > 1 else str(e))
            continue
        done += n
    if failed and not done:
        current = text.replace("\n", "\r\n") if crlf else text
        return ToolResult(False, "\n".join(failed) + _current_file_note(current, args["path"]))
    after = text.replace("\n", "\r\n") if crlf else text
    from .editing import MARKER_LINE
    if len(MARKER_LINE.findall(text)) > len(MARKER_LINE.findall(before)):
        # The edit would leave SEARCH/REPLACE markers in the file (a malformed block): nothing is saved.
        return ToolResult(False, "Not saved: this edit would write SEARCH/REPLACE markers (<<<<<<< / ======= / "
                                 ">>>>>>>) into the file - a block was malformed. Each marker must be on its own line: "
                                 "<<<<<<< SEARCH, the exact old lines, =======, the new lines, >>>>>>> REPLACE."
                                 + _current_file_note(before, args["path"]))
    if after == before:
        # A weak model "fixed" an image path three times this way while the page kept showing the old one: say what
        # it means, and a repeat is a failure (the stuck guard then makes it change route).
        seen = getattr(ctx, "noop_edits", {})
        seen[args["path"]] = seen.get(args["path"], 0) + 1
        ctx.noop_edits = seen
        return ToolResult(seen[args["path"]] < 2,
                          f"{args['path']}: no change - the file already contains exactly this new text (or old and "
                          "new are the same). The fix you meant is either already there or belongs somewhere else: "
                          "read_file the file (or search_code for the wrong value) and check what really causes the "
                          "problem before editing again.", {"path": args["path"]})
    op = {"tool": "edit_file", "path": str(target), "sha": hashlib.sha256(after.encode()).hexdigest()[:16]}
    preview = lambda: change_preview("edit", before.replace("\r\n", "\n"), text, _rel(ctx, target))  # noqa: E731
    if msg := await gate(ctx, op, policy.decide_file_write(target, ctx.root, ctx.mode), preview):
        return ToolResult(False, msg)
    target.write_text(after, encoding="utf-8", newline="")
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    patch = diff(before.replace("\r\n", "\n"), text, rel)
    added = sum(1 for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in patch.splitlines() if l.startswith("-") and not l.startswith("---"))
    js = await js_check(target)
    js += await _syntax_note(target)
    if failed:
        js += ("\n" + "\n".join(failed) + "\nThe other edits WERE saved. Send only the failed ones again, copied from "
               "the file as it is now (read_file it)." + _current_file_note(text, rel))
    return ToolResult(not failed, f"edited {rel}: {done} replacement(s), +{added} -{removed} lines" + (f"\n{js}" if js else ""),
                      {"path": rel, "language": target.suffix.lstrip("."), "diff": patch,
                       "added": added, "removed": removed})


@tool("search_code", '<tool name="search_code" path="." glob="*.js,*.css" regex="false">text to find</tool>',
      "Search the project's files for text or a regular expression; returns path:line: matching line. Use it to find "
      "where something is defined or used instead of reading files one by one.",
      {"query": S("Text or regular expression to find"), "path": S("Folder or file to search, default '.'"),
       "glob": S("Only files matching these patterns, comma separated (e.g. *.py,*.js)"),
       "regex": {"type": "boolean", "description": "Treat the query as a regular expression"},
       "case_sensitive": {"type": "boolean", "description": "Match upper/lower case exactly"}},
      main="query", required=("query",))
async def search_code(ctx, args, body):
    from .editing import EditError, search
    query = body.strip() or args.get("query", "") or args.get("pattern", "")
    rx = str(args.get("regex", "")).strip()
    if not query and rx and rx.lower() not in ("true", "false", "1", "0", "yes", "no"):
        # The pattern was put into the regex switch (regex="^export (function|const)"): seen live twice in one task.
        query, args = rx, {**args, "regex": "true"}
    if not query:
        return ToolResult(False, "Empty query: put the text or pattern in query (and regex=true for a pattern).")
    base = _path(ctx, args.get("path") or ".")
    if not base.exists():
        return ToolResult(False, f"not found: {args.get('path')}")
    flag = lambda k: str(args.get(k, "")).lower() in ("true", "1", "yes")  # noqa: E731
    try:
        lines, scanned, total = await asyncio.to_thread(
            search, ctx.root.resolve(), base, query, flag("regex"), args.get("glob", ""), flag("case_sensitive"))
    except EditError as e:
        return ToolResult(False, str(e))
    if not lines:
        return ToolResult(True, f"No matches for {query!r} in {scanned} files.", {"matches": 0})
    more = f"\n... {total - len(lines)} more matches (narrow the search with path or glob)" if total > len(lines) else ""
    return ToolResult(True, f"{total} matches in {scanned} files:\n" + "\n".join(lines) + more, {"matches": total})


@tool("read_file", '<tool name="read_file" path="REL/PATH" lines="40-120"></tool>',
      "Read a text file. For big files read only the lines you need (lines=\"start-end\", e.g. from search_code).",
      {"path": S("File path"), "lines": S("Optional line range, e.g. 40-120")}, required=("path",))
async def read_file(ctx, args, body):
    target = _path(ctx, args["path"])
    if not target.is_file():
        if target.is_dir():
            return ToolResult(False, f"{args['path']} is a folder; list it with list_dir")
        # A model that "remembers" a file it never wrote (babel.config.js in an Expo project) learns what is really
        # there, so it writes the missing file or reads the right one instead of guessing again.
        here = ""
        folder = target.parent
        while folder != ctx.root.resolve().parent and not folder.is_dir():
            folder = folder.parent
        if folder.is_dir():
            try:
                names = sorted((p.name + ("/" if p.is_dir() else "") for p in folder.iterdir()
                                if p.name not in ("node_modules", ".git", "__pycache__", ".expo")), key=str.lower)[:40]
                here = (f". It does not exist (write it first if it is needed). {_rel(ctx, folder) or '.'} has: "
                        f"{', '.join(names) or '(empty)'}")
            except OSError:
                pass
        return ToolResult(False, f"not found: {args['path']}" + _did_you_mean(ctx, target.name) + here)
    from .docread import DOC_EXTS
    if target.suffix.lower() in DOC_EXTS - {".txt", ".md", ".json", ".xml", ".html", ".htm", ".log", ".csv", ".tsv"}:
        return await read_document(ctx, {"path": args["path"]}, "")  # PDF/Office/image: pages, OCR
    with open(target, "rb") as fh:
        head = fh.read(4096)
    if b"\0" in head:
        # A binary file read as text came back empty and a weak model kept reading it to see its tables.
        if head.startswith(b"SQLite format 3"):
            import sqlite3
            try:
                con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
                tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                counts = []
                for t in tables[:30]:
                    n = con.execute('SELECT COUNT(*) FROM "' + t.replace('"', '""') + '"').fetchone()[0]
                    counts.append(f"{t}: {n} rows")
                info = "; ".join(counts) or "no tables yet (the schema was never created)"
                con.close()
            except sqlite3.Error as e:
                info = f"could not open it: {e}"
            return ToolResult(True, f"{args['path']} is an SQLite database - {info}. Query it with run, e.g. "
                                    f"python -c \"import sqlite3; print(sqlite3.connect('{args['path']}').execute("
                                    "'SELECT * FROM <table> LIMIT 5').fetchall())\"", {"path": args["path"]})
        return ToolResult(False, f"{args['path']} is a binary file ({target.stat().st_size} bytes), not text: inspect it "
                                 "with the program or library for its format via run (inspect_media for media).",
                          {"path": args["path"]})
    text = target.read_text(encoding="utf-8", errors="replace")
    # Inline images (data:...;base64) are megabytes of noise for a model: shown as a short placeholder.
    text = re.sub(r"(data:[\w/+.-]+;base64,)[A-Za-z0-9+/=\s]{300,}",
                  lambda m: f"{m.group(1)}[{len(m.group(0)) * 3 // 4096} KB image data omitted]", text)
    st = target.stat()
    key = str(target.resolve())
    # Read again although unchanged: older steps are shortened in the conversation (to keep it small), so "it is
    # above" may no longer be true - the content is given again, with a note (a third identical read is a loop and
    # is stopped by the task loop).
    again = ""
    if not args.get("lines") and ctx.read_seen.get(key) == (st.st_mtime_ns, st.st_size):
        again = f"[{args['path']} is unchanged since your last read in this task.]\n"
    all_lines = text.split("\n")
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", args.get("lines") or "")
    start = max(1, int(m.group(1))) if m else 1
    end = min(len(all_lines), int(m.group(2) or len(all_lines)) if m else len(all_lines))
    if start > len(all_lines):  # "lines 100-99 of 74" came back empty and the model thought the file was empty
        return ToolResult(False, f"{args['path']} has only {len(all_lines)} lines; read lines=1-{len(all_lines)} "
                                 "(or without lines for the whole file).", {"path": args["path"]})
    if m and ctx.read_seen.get(f"{key}#{start}-{end}") == (st.st_mtime_ns, st.st_size):
        again = f"[lines {start}-{end} of {args['path']} are unchanged since your last read in this task.]\n"
    # Whole lines up to the read limit, never a cut in the middle: a model that got "...[omitted]..." read the same
    # file again and again in overlapping parts. What does not fit is named as the next range to read.
    limit, size, last = getattr(ctx, "read_limit", 20000) or 20000, 0, start - 1
    for i in range(start - 1, end):
        size += len(all_lines[i]) + 1
        if size > limit and last >= start:
            break
        last = i + 1
    part = "\n".join(all_lines[start - 1:last])
    if last - start + 1 > 0 and len(part) > limit:  # one giant line (minified file)
        part = part[:limit] + f"\n...[{len(part) - limit} more characters on this line]"
    whole = start == 1 and last == len(all_lines)
    ctx.read_seen[key if whole and not m else f"{key}#{start}-{last}"] = (st.st_mtime_ns, st.st_size)
    if whole:
        return ToolResult(True, again + part, {"path": args["path"]})
    more = (f" - the rest: read_file lines={last + 1}-{end}" if last < end else "")
    return ToolResult(True, again + f"[{args['path']} lines {start}-{last} of {len(all_lines)}{more}]\n" + part,
                      {"path": args["path"]})


@tool("read_document", '<tool name="read_document" path="docs/report.pdf" pages="3-7">optional question to find passages</tool>',
      "Read a document with page numbers: PDF (scanned pages are OCR'd), Word, Excel, PowerPoint, OpenDocument "
      "(odt/ods/odp), CSV, text, or an image (OCR). Every part is labelled (p. 3, slide 2, sheet rows, paragraphs) "
      "so answers can cite where each fact is. Long documents: give a question to get the best passages, or "
      "pages=\"a-b\". Web documents: use fetch_url with the document's URL.",
      {"path": S("Document path"), "pages": S("Optional page range, e.g. 3-7 (PDF pages)"),
       "query": S("Optional: what to look for; returns the best passages with their page numbers")},
      main="query", required=("path",))
async def read_document(ctx, args, body):
    from . import docread
    target = _path(ctx, args["path"])
    if not target.is_file():
        return ToolResult(False, f"not found: {args['path']}")
    pages = docread.parse_pages(args.get("pages"))
    try:
        doc = await asyncio.to_thread(docread.load, target, "tr" if ctx.lang == "tr" else "en", pages)
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:  # a damaged or password-protected file
        return ToolResult(False, f"could not read {args['path']}: {type(e).__name__}: {str(e)[:200]}")
    text = docread.render(doc, (body.strip() or args.get("query") or "").strip())
    return ToolResult(True, clip(text, 16000), {"path": args["path"], "parts": len(doc.parts),
                                                "ocr": sum(p.ocr for p in doc.parts)})


@tool("list_dir", '<tool name="list_dir" path="."></tool>', "List a directory tree (ignores node_modules/.git).",
      {"path": S("Directory path, default '.'")})
async def list_dir(ctx, args, body):
    from ..workspace import tree
    target = _path(ctx, args.get("path", ".") or ".")
    if not target.exists():
        return ToolResult(False, f"no such folder: {args.get('path')}" + _did_you_mean(ctx, target.name))
    if target.is_file():
        return ToolResult(True, f"{_rel(ctx, target)} is a file, not a folder (read it with read_file)")
    rel = _rel(ctx, target)
    base = "" if rel in (".", "") else rel.rstrip("/") + "/"
    # Paths are given from the working folder, so they can be passed to read_file / run as they are (a weak model
    # took "sub/x.php" under "app/" for "./sub/x.php" and looped between the two folders).
    items = tree(target, 300)
    lines = [("📁 " if i["dir"] else "   ") + base + i["path"] for i in items]
    return ToolResult(True, (f"{base or './'} (paths from the working folder)\n" + "\n".join(lines)) if lines else f"{base or './'} is empty")


@tool("delete_file", '<tool name="delete_file" path="REL/PATH"></tool>', "Delete a file (always asks the user).",
      {"path": S("File path")}, required=("path",))
async def delete_file(ctx, args, body):
    target = _path(ctx, args["path"])
    op = {"tool": "delete_file", "path": str(target)}
    preview = lambda: change_preview("delete", _text_of(target), None, _rel(ctx, target)) if target.is_file() else None  # noqa: E731
    if ".session" in target.parts:
        return ToolResult(False, "The chat's .session folder is the app's own record; it cannot be deleted.")
    try:  # a file this task itself made (a failed output, a temp file) in the working folder: its own to remove
        own = target.is_file() and target.stat().st_mtime >= ctx.started - 1 and target.resolve().is_relative_to(ctx.root.resolve())
    except OSError:
        own = False
    # 'full' (Tam erişim): never asked; 'auto': only files this task made; 'ask': always asked.
    decision = policy.Decision("allow", "write") if ctx.mode == "full" or (own and ctx.mode == "auto") else \
        policy.Decision("ask", "dangerous", ["file deletion"])
    if msg := await gate(ctx, op, decision, preview):
        return ToolResult(False, msg)
    if target.is_file():
        target.unlink()
        ctx.files_changed.append(args["path"])
        return ToolResult(True, f"deleted {args['path']}")
    return ToolResult(False, "not a file")
