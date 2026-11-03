"""Loads agent roles (agents/*.md) and skills (skills/*.md). Drop in a new .md file to extend;
the UI can also create, edit, delete and import them (file upload or GitHub URL)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from ..config import ROOT, SKILLS_DIR
from ..errors import AppError

AGENTS_DIR = ROOT / "agents"
DIRS = {"agents": AGENTS_DIR, "skills": SKILLS_DIR}
CORE_AGENTS = {"assistant", "planner", "coder", "debugger", "tester"}  # the orchestrator depends on these
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
MAX_SIZE = 200_000


def _parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta: dict = {"name": path.stem, "title": path.stem, "description": ""}
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n?(.*)", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            if re.fullmatch(r"(title|description)(_[a-z]{2,3})?", k.strip()):
                meta[k.strip()] = v.strip().strip('"')
        text = m.group(2)
    meta["prompt"] = text.strip()
    return meta


def _load(d: Path) -> dict[str, dict]:
    return {m["name"]: m for m in map(_parse, sorted(d.glob("*.md")))}


def agents() -> dict[str, dict]:
    return _load(AGENTS_DIR)


def skills() -> dict[str, dict]:
    return _load(SKILLS_DIR)


def public(items: dict[str, dict], kind: str = "") -> list[dict]:
    return [{**{k: v for k, v in i.items() if k != "prompt"},
             "core": kind == "agents" and i["name"] in CORE_AGENTS} for i in items.values()]


def _path(kind: str, name: str) -> Path:
    if kind not in DIRS:
        raise ValueError("kind must be agents or skills")
    if not NAME_RE.fullmatch(name):
        raise AppError("invalid_item_name", "Names may contain only lowercase letters, digits, - and _")
    return DIRS[kind] / f"{name}.md"


def read(kind: str, name: str) -> str:
    p = _path(kind, name)
    if not p.is_file():
        raise FileNotFoundError(name)
    return p.read_text(encoding="utf-8")


def template(kind: str, name: str) -> str:
    role = "agent" if kind == "agents" else "skill"
    return (f"---\nname: {name}\ntitle: {name.title()}\ndescription: Short description of this {role}.\n---\n"
            f"Instructions for the {role}.\n")


def write(kind: str, name: str, content: str) -> None:
    if len(content) > MAX_SIZE:
        raise AppError("too_large", "File is too large")
    p = _path(kind, name)
    p.write_text(content.replace("\r\n", "\n"), encoding="utf-8")


def delete(kind: str, name: str) -> None:
    if kind == "agents" and name in CORE_AGENTS:
        raise AppError("core_agent", "Core agents cannot be deleted (they can be edited)")
    p = _path(kind, name)
    if p.is_file():
        p.unlink()


FRONT = re.compile(r"---\r?\n(.*?)\r?\n---\r?\n?(.*)", re.S)


def set_meta(path: Path, updates: dict[str, str | None]) -> None:
    """Add/replace/remove frontmatter fields (value None removes), keeping the body and other fields."""
    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    head, body = (m.group(1).splitlines(), m.group(2)) if m else ([f"name: {path.stem}"], text)
    keys = {line.partition(":")[0].strip(): i for i, line in enumerate(head)}
    for k, v in updates.items():
        line = f"{k}: {' '.join(str(v).split())}" if v is not None else None
        if k in keys:
            head[keys[k]] = line
        elif line:
            head.append(line)
    head = [h for h in head if h is not None]
    path.write_text("---\n" + "\n".join(head) + "\n---\n" + body, encoding="utf-8")


def localize(langs: list[str], only: list[Path] | None = None) -> int:
    """Fill title_<lang>/description_<lang> for every agent/skill (or only the given files) that lacks them.
    Source: the English fields when present, otherwise the generic ones with language auto-detection."""
    from ..i18n import translate_all
    files = only or [p for d in DIRS.values() for p in sorted(d.glob("*.md"))]
    done = 0
    for lang in langs:
        todo = []
        for p in files:
            meta = _parse(p)
            for field in ("title", "description"):
                if meta.get(field) and not meta.get(f"{field}_{lang}"):
                    src = meta.get(f"{field}_en") or meta[field]
                    todo.append((p, field, src, "en" if meta.get(f"{field}_en") else "auto"))
        for source in ("en", "auto"):
            batch = [t for t in todo if t[3] == source]
            if not batch:
                continue
            texts = translate_all([t[2] for t in batch], lang, source=source)
            per_file: dict[Path, dict] = {}
            for (p, field, _, _), tr in zip(batch, texts):
                per_file.setdefault(p, {})[f"{field}_{lang}"] = tr
            for p, upd in per_file.items():
                set_meta(p, upd)
                done += len(upd)
    return done


def drop_language(lang: str) -> None:
    for d in DIRS.values():
        for p in d.glob("*.md"):
            meta = _parse(p)
            if f"title_{lang}" in meta or f"description_{lang}" in meta:
                set_meta(p, {f"title_{lang}": None, f"description_{lang}": None})


def name_from(content: str, fallback: str) -> str:
    m = re.search(r"^name:\s*([\w.-]+)", content, re.M)
    raw = (m.group(1) if m else fallback).lower()
    return re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")[:64] or "imported"


def github_raw(url: str) -> str:
    """github.com/<o>/<r>/blob/<ref>/<path> -> raw.githubusercontent.com/<o>/<r>/<ref>/<path>.
    A folder URL (tree/...) is mapped to its SKILL.md."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/(blob|tree)/([^/]+)/(.+)", url)
    if not m:
        return url
    owner, repo, typ, ref, path = m.groups()
    if typ == "tree" and not path.endswith(".md"):
        path = path.rstrip("/") + "/SKILL.md"
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"


async def import_url(kind: str, url: str) -> str:
    if not url.startswith("https://"):
        raise AppError("https_only", "Only https URLs are supported")
    raw = github_raw(url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.get(raw)
    if r.status_code >= 400:
        raise AppError("download_failed", f"Download failed ({r.status_code}): {raw}")
    content = r.text
    if len(content) > MAX_SIZE or "\x00" in content:
        raise AppError("invalid_file", "Invalid or too large file")
    stem = Path(raw.split("?")[0]).stem
    name = name_from(content, Path(raw).parent.name if stem.upper() == "SKILL" else stem)
    write(kind, name, content)
    return name
