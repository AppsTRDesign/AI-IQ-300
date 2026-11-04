"""Partial file edits (edit_file) and project-wide code search (search_code).

Edits replace an exact snippet instead of rewriting the whole file: on slow local models a change takes seconds,
not minutes, and the context does not fill up with full file copies. Matching is forgiving about what models get
wrong most (CRLF, trailing spaces, indentation) but never guesses between several places."""
from __future__ import annotations

import difflib
import fnmatch
import os
import re
from pathlib import Path

from ..workspace import IGNORED

# Aider-style blocks, which most models already know:  <<<<<<< SEARCH / ======= / >>>>>>> REPLACE
BLOCK = re.compile(r"<{5,9} ?SEARCH[^\n]*\n(.*?)\n?={5,9}[^\n]*\n(.*?)\n?>{5,9} ?REPLACE", re.S)


class EditError(Exception):
    pass


def parse_blocks(body: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in BLOCK.finditer(body or "")]


def _line_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of every line, end without the newline."""
    spans, pos = [], 0
    for line in text.split("\n"):
        spans.append((pos, pos + len(line)))
        pos += len(line) + 1
    return spans


def _find_lines(text: str, old: str, norm) -> list[tuple[int, int]]:
    """Places where the old snippet matches whole lines after normalising each line with norm()."""
    want = [norm(x) for x in old.strip("\n").split("\n")]
    lines = text.split("\n")
    spans = _line_spans(text)
    n = len(want)
    hits = []
    for i in range(len(lines) - n + 1):
        if all(norm(lines[i + k]) == want[k] for k in range(n)):
            hits.append((spans[i][0], spans[i + n - 1][1]))
    return hits


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _style(lines: list[str]) -> tuple[int, int, str]:
    """(base indent of the first line, indent step per level, indent char) of a block of lines."""
    body = [l for l in lines if l.strip()]
    if not body:
        return 0, 0, " "
    base = _indent(body[0])
    steps = [_indent(l) - base for l in body if _indent(l) > base]
    char = "\t" if any(l.startswith("\t") for l in body) else " "
    return base, min(steps) if steps else 0, char


def _reindent(new: str, old: str, found: str) -> str:
    """The snippet matched with a different indentation (2 vs 4 spaces, nested deeper, tabs): re-indent the
    replacement in the file's style, level by level."""
    base_o, step_o, _ = _style(old.split("\n"))
    base_f, step_f, char = _style(found.split("\n"))
    step_f = step_f or step_o or (1 if char == "\t" else 4)
    out = []
    for line in new.split("\n"):
        if not line.strip():
            out.append(line)
            continue
        rel = _indent(line) - base_o
        if rel < 0:
            out.append(line)
            continue
        levels, rest = divmod(rel, step_o) if step_o else (0, rel)
        width = base_f + levels * step_f + rest
        out.append(char * width + line.lstrip(" \t"))
    return "\n".join(out)


def apply_edit(text: str, old: str, new: str, replace_all: bool = False) -> tuple[str, int]:
    """Returns (new text, replacements). Raises EditError with a hint the model can act on."""
    if not old.strip():
        raise EditError("The text to replace is empty. Give a unique snippet copied from the file "
                        "(use write_file to create a new file).")
    count = text.count(old)
    if count:
        if count > 1 and not replace_all:
            raise EditError(f"The snippet occurs {count} times. Add surrounding lines so it is unique, "
                            "or set replace_all to change every occurrence.")
        return text.replace(old, new) if replace_all else text.replace(old, new, 1), count if replace_all else 1
    # Forgiving passes: trailing spaces, then indentation (whole lines only).
    for norm in (str.rstrip, str.strip):
        hits = _find_lines(text, old, norm)
        if hits:
            if len(hits) > 1 and not replace_all:
                raise EditError(f"The snippet matches {len(hits)} places (ignoring whitespace). Add surrounding "
                                "lines so it is unique, or set replace_all.")
            for start, end in reversed(hits if replace_all else hits[:1]):
                found = text[start:end]
                repl = _reindent(new.strip("\n"), old.strip("\n"), found) if norm is str.strip else new.strip("\n")
                text = text[:start] + repl + text[end:]
            return text, len(hits) if replace_all else 1
    raise EditError("The snippet was not found in the file." + _closest(text, old))


def _closest(text: str, old: str) -> str:
    """Point the model at the most similar lines so the retry copies the real text."""
    lines = text.split("\n")
    want = old.strip("\n").split("\n")
    n = max(1, len(want))
    target = "\n".join(x.strip() for x in want)
    best, best_i = 0.0, -1
    for i in range(0, max(1, len(lines) - n + 1)):
        r = difflib.SequenceMatcher(None, target, "\n".join(x.strip() for x in lines[i:i + n])).quick_ratio()
        if r > best:
            best, best_i = r, i
    if best_i < 0 or best < 0.5:
        return " Read the file again (read_file) and copy the exact text."
    snippet = "\n".join(lines[best_i:best_i + n])
    return (f" Most similar text (lines {best_i + 1}-{best_i + n}), copy it exactly if this is the place:\n"
            f"{snippet[:1500]}")


def diff(before: str, after: str, path: str, limit: int = 6000) -> str:
    out = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                       f"a/{path}", f"b/{path}", n=2))
    return out if len(out) <= limit else out[:limit] + "\n... (diff truncated)"


# --- search_code -----------------------------------------------------------------------------------------

SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf", ".zip", ".gz", ".7z", ".rar", ".exe",
            ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".wav", ".mov", ".db",
            ".sqlite", ".pyc", ".class", ".jar", ".lock", ".min.js", ".map", ".docx", ".xlsx", ".pptx"}
MAX_FILE = 1_000_000


def _walk(base: Path):
    """Files under base; dependency, build and hidden folders are pruned before descending (fast on big repos)."""
    if base.is_file():
        yield base
        return
    for d, dirs, files in os.walk(base):
        dirs[:] = sorted(x for x in dirs if x not in IGNORED and not x.startswith("."))
        for f in sorted(files):
            yield Path(d) / f


def search(root: Path, base: Path, query: str, regex: bool = False, glob: str = "", case: bool = False,
           limit: int = 120) -> tuple[list[str], int, int]:
    """Lines matching query under base. Returns (lines 'path:line: text', files scanned, total matches)."""
    flags = 0 if case else re.I
    try:
        pat = re.compile(query if regex else re.escape(query), flags)
    except re.error as e:
        raise EditError(f"Invalid regular expression: {e}") from e
    globs = [g.strip() for g in glob.split(",") if g.strip()]
    out: list[str] = []
    scanned = total = 0
    for p in _walk(base):
        if total > 2000 or scanned > 20000:
            break
        name = p.name.lower()
        if any(name.endswith(x) for x in SKIP_EXT):
            continue
        if globs and not any(fnmatch.fnmatch(p.name, g) or fnmatch.fnmatch(p.relative_to(base).as_posix(), g)
                             for g in globs):
            continue
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:2048]:  # binary
            continue
        scanned += 1
        text = data.decode("utf-8", errors="replace")
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = str(p)
        for i, line in enumerate(text.split("\n"), 1):
            if pat.search(line):
                total += 1
                if len(out) < limit:
                    out.append(f"{rel}:{i}: {line.strip()[:200]}")
    return out, scanned, total
