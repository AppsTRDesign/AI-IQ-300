"""Symbol map: functions, classes, methods and other top-level definitions per file, found with light regexes
(no parser to install). Two uses:
- a short project map in the system prompt of project chats, so the model knows where things live without reading
  files one by one;
- the `symbols` tool: definitions of a file or folder with line numbers, to jump straight to read_file lines=..."""
from __future__ import annotations

import re
from pathlib import Path

from .editing import _walk

_PY = [(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", "def"), (r"^\s*class\s+(\w+)", "class")]
_JS = [(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\(", "function"),
       (r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", "class"),
       (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>", "function"),
       (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\b", "function"),
       (r"^\s*(?:export\s+)?(?:interface|type|enum)\s+(\w+)", "type"),
       (r"^\s{2,}(?:async\s+|static\s+|get\s+|set\s+)*(?!if\b|for\b|while\b|switch\b|catch\b|return\b)(\w+)\s*\([^)]*\)\s*\{\s*$",
        "method")]
_PHP = [(r"^\s*(?:public|private|protected|static|final|abstract|\s)*function\s+(\w+)\s*\(", "function"),
        (r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait|enum)\s+(\w+)", "class")]
_GO = [(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", "func"), (r"^type\s+(\w+)\s+(?:struct|interface)", "type")]
_RS = [(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", "fn"),
       (r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)", "type")]
_JAVA = [(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(?:class|interface|enum|record)\s+(\w+)", "class"),
         (r"^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?(?:override\s+)?[\w<>\[\],\s]+\s+(\w+)\s*\(", "method")]
_RB = [(r"^\s*def\s+(?:self\.)?(\w+[?!]?)", "def"), (r"^\s*(?:class|module)\s+(\w+)", "class")]
_SQL = [(r"(?i)^\s*create\s+(?:or\s+replace\s+)?(?:table|view|function|procedure)\s+(?:if\s+not\s+exists\s+)?[`\"\[]?(\w+)", "table")]
_CSS = [(r"^\s*(?:@media[^{]*\{\s*)?([.#][\w-]+)[^{,]*\{", "selector")]
_HTML = [(r"\bid=[\"']([\w-]+)[\"']", "id")]

RULES = {".py": _PY, ".js": _JS, ".jsx": _JS, ".mjs": _JS, ".cjs": _JS, ".ts": _JS, ".tsx": _JS, ".vue": _JS,
         ".svelte": _JS, ".php": _PHP, ".go": _GO, ".rs": _RS, ".java": _JAVA, ".kt": _JAVA, ".cs": _JAVA,
         ".rb": _RB, ".sql": _SQL, ".css": _CSS, ".scss": _CSS, ".html": _HTML, ".htm": _HTML}
_COMPILED = {ext: [(re.compile(p), kind) for p, kind in rules] for ext, rules in RULES.items()}
MAX_BYTES = 400_000


def file_symbols(path: Path, wait: float = 0) -> list[tuple[int, str, str]]:
    """[(line, kind, name)] of one file: from the tree-sitter syntax tree when its grammar is loaded, else regex."""
    from .syntax import definitions
    defs = definitions(path, wait)
    if defs is not None:
        return [(start, kind, name) for start, _, kind, name in defs]
    rules = _COMPILED.get(path.suffix.lower())
    if not rules:
        return []
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out, seen = [], set()
    for i, line in enumerate(text.split("\n"), 1):
        if len(line) > 400:
            continue
        for rx, kind in rules:
            for m in rx.finditer(line) if kind == "id" else filter(None, [rx.search(line)]):
                name = m.group(1)
                if (kind, name) in seen and kind in ("selector", "id"):
                    continue
                seen.add((kind, name))
                out.append((i, kind, name))
                break
    return out


def _files(base: Path):
    for p in _walk(base):
        if p.suffix.lower() in RULES and not p.name.endswith(".min.js"):
            yield p


def detail(root: Path, base: Path, limit: int = 400) -> str:
    """Symbols with line numbers, for the `symbols` tool."""
    lines, count = [], 0
    for p in _files(base):
        syms = file_symbols(p, 15)
        if not syms:
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = str(p)
        lines.append(rel)
        for ln, kind, name in syms:
            lines.append(f"  {ln}: {kind} {name}")
            count += 1
            if count >= limit:
                lines.append(f"... more symbols (limit {limit}); ask for a sub-folder or a single file")
                return "\n".join(lines)
    return "\n".join(lines) if lines else "No functions, classes or definitions found."


def project_map(root: Path, max_chars: int = 2500) -> str:
    """Compact map for the system prompt: 'path: name, name(), Class' per file, most-defining files first."""
    from .syntax import prefetch
    rows = []
    files = []
    for i, p in enumerate(_files(root)):
        if i >= 1500:
            break
        files.append(p)
    prefetch(files)  # parallel read + one parse per changed file (later maps come from the cache)
    for p in files:
        syms = [s for s in file_symbols(p) if s[1] not in ("selector", "id")]
        if not syms:
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        names = [f"{n}()" if k in ("def", "function", "func", "fn", "method") else n for _, k, n in syms]
        rows.append((rel, names))
        if len(rows) > 400:
            break
    out, used = [], 0
    for rel, names in rows:
        line = f"{rel}: {', '.join(names[:14])}{' …' if len(names) > 14 else ''}"
        if used + len(line) > max_chars:
            out.append(f"... {len(rows) - len(out)} more files (use the symbols tool)")
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)
