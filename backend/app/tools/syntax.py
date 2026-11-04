"""Tree-sitter syntax trees: exact definitions (functions, classes, methods) and real references (identifiers in
code, never in comments or strings), and the impact of a change: which files use what a file or symbol defines.

Grammars come from tree-sitter-language-pack (downloaded once on first use, then cached). Without the package or
a grammar (offline) callers fall back to the regex symbol rules in symbols.py.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .editing import _walk

LANG = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "tsx", ".php": "php", ".java": "java", ".go": "go", ".rs": "rust",
        ".rb": "ruby", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cs": "csharp",
        ".kt": "kotlin", ".swift": "swift", ".lua": "lua", ".sh": "bash"}
MAX_BYTES = 400_000
MAX_FILES = 4000

# node type -> kind; methods are classes' functions
DEF_KINDS = {
    "function_definition": "def", "function_declaration": "function", "generator_function_declaration": "function",
    "method_definition": "method", "method_declaration": "method", "function_item": "fn", "method": "def",
    "singleton_method": "def", "constructor_declaration": "method", "function_signature_item": "fn",
    "class_definition": "class", "class_declaration": "class", "class_specifier": "class", "class": "class",
    "interface_declaration": "interface", "trait_declaration": "trait", "trait_item": "trait", "enum_declaration": "enum",
    "enum_item": "enum", "struct_item": "struct", "struct_specifier": "struct", "type_alias_declaration": "type",
    "type_spec": "type", "module": "module", "object_declaration": "object", "protocol_declaration": "protocol",
    "record_declaration": "class", "abstract_class_declaration": "class",
}
# Node kinds that never contain definitions worth listing (saves walking every expression in Python).
SKIP_INTO = ("expression", "call", "argument", "string", "comment", "literal", "parameters", "return", "binary",
             "assignment", "condition", "subscript", "attribute", "member", "arguments")
CLASSY = {"class", "interface", "trait", "struct", "object", "protocol", "enum", "module"}
IDENT = {"identifier", "property_identifier", "type_identifier", "field_identifier", "shorthand_property_identifier",
         "name", "constant", "simple_identifier", "word"}

_parsers: dict[str, object] = {}
_failed: set[str] = set()
_loading: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def _load(lang: str) -> None:
    try:
        from tree_sitter_language_pack import get_parser
        _parsers[lang] = get_parser(lang)
    except Exception:  # package missing, grammar not downloadable (offline)...
        _failed.add(lang)
    finally:
        _loading.pop(lang, None)


def parser(ext: str, wait: float = 0):
    """The parser for a file extension, or None. A grammar that is not loaded yet loads in the background (the
    first use downloads it): wait=0 never blocks (prompt building), tools wait a little for it."""
    lang = LANG.get(ext.lower())
    if not lang or lang in _failed:
        return None
    if lang in _parsers:
        return _parsers[lang]
    with _lock:
        t = _loading.get(lang)
        if t is None and lang not in _parsers:
            t = _loading[lang] = threading.Thread(target=_load, args=(lang,), daemon=True)
            t.start()
    if wait and t is not None:
        t.join(wait)
    return _parsers.get(lang)


def warm(exts=(".py", ".js", ".ts", ".tsx", ".php")) -> None:
    for e in exts:
        parser(e)


def available() -> bool:
    try:
        import tree_sitter_language_pack  # noqa: F401
        return True
    except ImportError:
        return False


def _read(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _name(node, src: bytes) -> str | None:
    n = node.child_by_field_name("name")
    if n is None and node.type == "type_spec":
        n = node.child_by_field_name("name")
    if n is None:  # C/C++ functions: declarator -> function_declarator -> declarator
        d = node.child_by_field_name("declarator")
        while d is not None and d.child_by_field_name("declarator") is not None and d.type != "identifier":
            d = d.child_by_field_name("declarator")
        n = d
    if n is None:
        return None
    text = src[n.start_byte:n.end_byte].decode(errors="replace")
    return text if len(text) <= 120 and "\n" not in text else None


_DEFS: dict[str, tuple[tuple[int, int], list]] = {}  # path -> ((mtime_ns, size), definitions)


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def read_many(paths: list[Path]) -> list[bytes | None]:
    """File contents read in parallel: on Windows opening a file costs milliseconds (antivirus scan on open),
    which overlaps across threads; parsing stays on one thread (parsers are not thread-safe)."""
    if len(paths) < 8:
        return [_read(p) for p in paths]
    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(_read, paths))


def prefetch(paths: list[Path]) -> None:
    """Fill the definitions cache for files whose cached version is stale (one parallel read)."""
    stale = [p for p in paths if p.suffix.lower() in LANG and parser(p.suffix) is not None
             and not ((hit := _DEFS.get(str(p))) and hit[0] == _stamp(p))]
    for p, src in zip(stale, read_many(stale)):
        if src is not None:
            definitions(p, src=src)


def definitions(path: Path, wait: float = 0, src: bytes | None = None) -> list[tuple[int, int, str, str]] | None:
    """[(start line, end line, kind, name)] or None when the file has no (loaded) tree-sitter grammar.
    Cached per file version (mtime + size), so unchanged files are never parsed twice."""
    p = parser(path.suffix, wait)
    if p is None:
        return None
    key, stamp = str(path), _stamp(path)
    if stamp and (hit := _DEFS.get(key)) and hit[0] == stamp:
        return hit[1]
    src = src if src is not None else _read(path)
    if src is None:
        return []
    out: list[tuple[int, int, str, str]] = []

    def walk(node, in_class: bool, depth: int):
        if depth > 60:
            return
        for ch in node.children:
            kind = DEF_KINDS.get(ch.type)
            if ch.type == "variable_declarator":  # const f = () => {} / function expressions
                val = ch.child_by_field_name("value")
                if val is not None and val.type in ("arrow_function", "function_expression", "function"):
                    kind = "function"
            if kind:
                name = _name(ch, src)
                if name:
                    k = "method" if in_class and kind in ("def", "function", "fn") else kind
                    out.append((ch.start_point[0] + 1, ch.end_point[0] + 1, k, name))
                if kind in CLASSY:  # functions' bodies are not walked: the map lists top-level and class members
                    walk(ch, True, depth + 1)
            elif not any(k in ch.type for k in SKIP_INTO):
                walk(ch, in_class or ch.type in ("impl_item", "class_body", "declaration_list"), depth + 1)

    walk(p.parse(src).root_node, False, 0)
    if stamp:
        if len(_DEFS) > 20_000:
            _DEFS.clear()
        _DEFS[key] = (stamp, out)
    return out


NON_CODE = ("comment", "string", "template", "heredoc", "char_literal", "regex")


def _idents(root, src: bytes, name: bytes, out: list[int]) -> None:
    """Lines where `name` occurs as an identifier: only the byte offsets where the text occurs are looked up in
    the tree (descendant_for_byte_range), and an occurrence inside a comment or string is skipped."""
    start = 0
    while (i := src.find(name, start)) >= 0:
        start = i + len(name)
        node = root.descendant_for_byte_range(i, i + len(name))
        if node is None or node.start_byte != i or node.end_byte != i + len(name) or node.type not in IDENT:
            continue
        n, code = node.parent, True
        while n is not None:
            if any(k in n.type for k in NON_CODE):
                code = False
                break
            n = n.parent
        if code:
            out.append(node.start_point[0] + 1)


def references(root: Path, name: str, skip: Path | None = None) -> dict[str, list[int]]:
    """{relative path: [lines]} where `name` is used as an identifier in code."""
    needle = name.encode()
    hits: dict[str, list[int]] = {}
    paths = []
    for i, path in enumerate(_walk(root)):
        if i > MAX_FILES:
            break
        if path.suffix.lower() in LANG and not (skip and path == skip):
            paths.append(path)
    for path, src in zip(paths, read_many(paths)):
        if not src or needle not in src:  # cheap pre-filter: parse only files that contain the text
            continue
        p = parser(path.suffix, 15)
        if p is None:
            continue
        lines: list[int] = []
        _idents(p.parse(src).root_node, src, needle, lines)
        if lines:
            hits[path.relative_to(root).as_posix()] = sorted(set(lines))
    return hits


def impact(root: Path, target: str) -> str:
    """What a change would touch. target: a file (its definitions -> files using them) or a symbol name."""
    f = (root / target)
    if f.is_file():
        defs = definitions(f, 15)
        if defs is None:
            return f"No syntax grammar for {target}; use search_code instead."
        names = sorted({n for _, _, k, n in defs if len(n) > 2 and k != "method"} | {n for _, _, k, n in defs if k == "method" and len(n) > 3})
        if not names:
            return f"{target} defines nothing other files could use."
        users: dict[str, set[str]] = {}
        for n in names[:60]:
            for rel, _ in references(root, n, skip=f).items():
                users.setdefault(rel, set()).add(n)
        head = f"{target} defines {len(names)} symbols: {', '.join(names[:40])}"
        if not users:
            return head + "\nNo other file uses them: a change here affects only this file."
        body = "\n".join(f"- {rel}: uses {', '.join(sorted(ns)[:12])}" for rel, ns in sorted(users.items(), key=lambda kv: -len(kv[1]))[:80])
        return f"{head}\nAffected files ({len(users)}), check them after changing {target}:\n{body}"
    defs_at = []
    for i, path in enumerate(_walk(root)):
        if i > MAX_FILES:
            break
        if path.suffix.lower() in LANG and (src := _read(path)) and target.encode() in src:
            for s, e, k, n in definitions(path, 15) or []:
                if n == target:
                    defs_at.append(f"{path.relative_to(root).as_posix()}:{s}-{e} ({k})")
    refs = references(root, target)
    if not defs_at and not refs:
        return f"'{target}' is neither a file nor a symbol used in the project's code."
    lines = [f"Defined at: {', '.join(defs_at) or 'not found (external or dynamic)'}",
             f"Used in {len(refs)} files ({sum(map(len, refs.values()))} places):"]
    lines += [f"- {rel}: lines {', '.join(map(str, ls[:20]))}{' ...' if len(ls) > 20 else ''}" for rel, ls in list(refs.items())[:80]]
    return "\n".join(lines)
