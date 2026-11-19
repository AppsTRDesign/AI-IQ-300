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

# Aider-style blocks, which most models already know:  <<<<<<< SEARCH / ======= / >>>>>>> REPLACE. Variants weak
# models write are accepted too: ORIGINAL / OLD / FIND / BEFORE ... UPDATED / NEW / AFTER, 3-9 marker characters,
# a block inside a ``` fence.
BLOCK = re.compile(r"<{3,9} ?(?:SEARCH|ORIGINAL|OLD|FIND|BEFORE)[^\n]*\n(.*?)\n?={3,9}[^\n]*\n(.*?)\n?>{3,9} ?"
                   r"(?:REPLACE|UPDATED|NEW|AFTER)", re.S | re.I)


class EditError(Exception):
    pass


def collapse_repeats(text: str) -> tuple[str, int]:
    """A generation loop inside a file (the same <script> block written thousands of times): every run of one block
    of 1-25 lines repeated back to back is kept once. Returns (text, blocks removed). Short or blank lines that may
    legitimately repeat (</div>, }, empty lines) do not count: a block must hold at least 40 characters, and a single
    line repeats at least 10 times, a larger block 6 times, and the copies hold 1,200+ characters."""
    lines = text.split("\n")
    out: list[str] = []
    removed = 0
    i, n = 0, len(lines)
    while i < n:
        best = None
        for k in range(1, 26):
            if i + 2 * k > n:
                break
            block = lines[i:i + k]
            if len("".join(x.strip() for x in block)) < 40:
                continue
            reps = 1
            while i + (reps + 1) * k <= n and lines[i + reps * k:i + (reps + 1) * k] == block:
                reps += 1
            # Only real loops: many back-to-back copies holding a lot of text (a generated table or seed list with a
            # few equal rows stays as written).
            size = len("\n".join(block)) * reps
            if reps >= (10 if k == 1 else 6) and size >= 1200 and (best is None or reps * k > best[0] * best[1]):
                best = (reps, k)
        if best:
            reps, k = best
            out.extend(lines[i:i + k])
            removed += reps - 1
            i += reps * k
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), removed


def norm_key(k: str) -> str:
    """oldText / old_text / OldString / old-str -> oldtext / oldstring ...: models spell the same argument many ways."""
    return re.sub(r"[^a-z]", "", str(k).lower())


def pick(d: dict, keys) -> str | None:
    """The first string value of d under any spelling of keys."""
    want = [norm_key(k) for k in keys]
    by = {norm_key(k): v for k, v in d.items()}
    for w in want:
        if isinstance(by.get(w), str):
            return by[w]
    return None


def parse_blocks(body) -> list[tuple[str, str]]:
    """Edits from the body: SEARCH/REPLACE blocks (and their variants), a JSON list of {old, new} (any key spelling,
    also nested under edits / changes / replacements), or a unified diff."""
    if isinstance(body, (list, dict)):
        import json
        body = json.dumps(body, ensure_ascii=False)
    body = body or ""
    pairs = [(m.group(1), m.group(2)) for m in BLOCK.finditer(body)]
    if pairs:
        return pairs
    s = body.strip()
    if s[:1] in "[{":
        import json
        try:
            data = json.loads(s)
        except ValueError:
            data = None
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict):
            nested = next((v for k, v in data.items() if norm_key(k) in LIST_KEYS and isinstance(v, list)), None)
            items = nested if nested is not None else [data]
        for it in items or []:
            if isinstance(it, dict):
                old = pick(it, [k for k in OLD_KEYS])
                new = pick(it, NEW_KEYS) or ""
                if old:
                    pairs.append((old, new))
        if pairs:
            return pairs
    if re.search(r"^@@ ", body, re.M):
        return unified_pairs(body)
    return []


OLD_KEYS = ("old", "old_string", "old_text", "old_str", "search", "find", "original", "before", "from", "target",
            "old_code", "existing")
NEW_KEYS = ("new", "new_string", "new_text", "new_str", "replace", "replacement", "updated", "after", "to", "content",
            "new_code")
LIST_KEYS = {"edits", "changes", "replacements", "patches", "diffs", "modifications", "blocks"}


def unified_pairs(patch: str) -> list[tuple[str, str]]:
    """Each @@ hunk of a unified diff as (old lines, new lines): context and '-' lines, context and '+' lines."""
    out, old, new, inside = [], [], [], False
    for line in patch.replace("\r\n", "\n").split("\n"):
        if line.startswith("@@"):
            if inside and (old or new):
                out.append(("\n".join(old), "\n".join(new)))
            old, new, inside = [], [], True
            continue
        if not inside or line.startswith(("--- ", "+++ ", "\\ No newline")):
            continue
        if line.startswith("-"):
            old.append(line[1:])
        elif line.startswith("+"):
            new.append(line[1:])
        else:
            ctx = line[1:] if line.startswith(" ") else line
            old.append(ctx)
            new.append(ctx)
    if inside and (old or new):
        out.append(("\n".join(old), "\n".join(new)))
    return [(o, n) for o, n in out if o.strip()]


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
    # Any whitespace differences, also inside a line or in a fragment ("a  =  b" vs "a = b", tabs vs spaces).
    words = old.split()
    if words:
        rx = re.compile(r"\s+".join(re.escape(w) for w in words))
        found = list(rx.finditer(text))
        if len(found) == 1 or (found and replace_all):
            for m in reversed(found if replace_all else found[:1]):
                text = text[:m.start()] + new.strip("\n") + text[m.end():]
            return text, len(found) if replace_all else 1
    # A model that retyped the snippet from memory (a quote changed, a word missing): one region that is almost the
    # same and clearly better than any other is the place. It looped on "not found" before.
    if (spot := _near_unique(text, old)) is not None:
        start, end = spot
        repl = _reindent(new.strip("\n"), old.strip("\n"), text[start:end])
        return text[:start] + repl + text[end:], 1
    raise EditError("The snippet was not found in the file." + _closest(text, old))


def _near_unique(text: str, old: str, need: float = 0.9) -> tuple[int, int] | None:
    """(start, end) of the only line window at least `need` similar to old (and 0.05 better than the next one)."""
    lines = text.split("\n")
    want = old.strip("\n").split("\n")
    n = len(want)
    if n < 2 and len(old.strip()) < 25:  # too short to place by similarity
        return None
    target = "\n".join(x.strip() for x in want)
    spans = _line_spans(text)
    scored = []
    for size in {n, max(1, n - 1), n + 1}:
        for i in range(0, max(0, len(lines) - size) + 1):
            window = "\n".join(x.strip() for x in lines[i:i + size])
            sm = difflib.SequenceMatcher(None, target, window)
            if sm.quick_ratio() < need:
                continue
            scored.append((sm.ratio(), i, size))
    if not scored:
        return None
    scored.sort(reverse=True)
    best, i, size = scored[0]
    # windows overlapping the best one are the same place, not a rival
    rivals = [r for r, j, s in scored[1:] if j + s <= i or j >= i + size]
    if best < need or (rivals and rivals[0] > best - 0.05):
        return None
    return spans[i][0], spans[i + size - 1][1]


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
