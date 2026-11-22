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
    return _parse_text(path.read_text(encoding="utf-8"), path.stem)


def _parse_text(text: str, stem: str = "") -> dict:
    nm = re.search(r"^name:\s*([\w.-]+)", text, re.M)
    stem = stem or (nm.group(1) if nm else "")
    meta: dict = {"name": stem, "title": stem, "description": ""}
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n?(.*)", text, re.S)
    if m:
        in_tools = False
        lines = m.group(1).splitlines()
        for i, line in enumerate(lines):
            k, _, v = line.partition(":")
            if re.fullmatch(r"\s*[>|][+-]?\s*", v) and not line[:1].isspace():
                # a YAML block value (description: >-, then indented lines; google/skills writes them so): the
                # indented lines are the value
                block = []
                for nxt in lines[i + 1:]:
                    if nxt.strip() and not nxt[:1].isspace():
                        break
                    block.append(nxt.strip())
                lines[i] = f"{k}: " + (" " if v.strip()[0] == ">" else " ").join(b for b in block if b)
        for line in lines:
            if in_tools and (item := re.match(r"\s*-\s*['\"]?([\w-]+)['\"]?\s*$", line)):
                meta["tools"].append(item.group(1))  # YAML list form: "tools:" then "  - name" lines
                continue
            in_tools = False
            k, _, v = line.partition(":")
            if re.fullmatch(r"(title|description)(_[a-z]{2,3})?", k.strip()):
                meta[k.strip()] = v.strip().strip('"')
            elif k.strip() == "source":  # where an imported skill came from (owner/repo/path/SKILL.md)
                meta["source"] = v.strip()
            elif k.strip() == "triggers":  # optional: a regex; a request that matches it is pointed at this skill
                try:
                    meta["triggers"] = re.compile(v.strip().strip("'\""), re.I)
                except re.error:
                    pass
            elif k.strip() == "tools":  # optional: only these tools are offered while this agent/skill is in use
                meta["tools"] = [t.strip("'\"") for t in re.split(r"[,\s]+", v.strip().strip("[]")) if t]
                in_tools = not meta["tools"]
        text = m.group(2)
    meta["prompt"] = text.strip()
    return meta


def _load(d: Path) -> dict[str, dict]:
    return {m["name"]: m for m in map(_parse, sorted(d.glob("*.md")))}


def matching_skills(request: str, skip=()) -> list[str]:
    """Skills whose `triggers` regex matches the request (at most two), for a "load this skill first" hint."""
    if not request:
        return []
    return [k for k, v in skills().items() if k not in skip and v.get("triggers") and v["triggers"].search(request)][:2]


def agents() -> dict[str, dict]:
    return _load(AGENTS_DIR)


def skills() -> dict[str, dict]:
    return _load(SKILLS_DIR)


def public(items: dict[str, dict], kind: str = "") -> list[dict]:
    return [{**{k: v for k, v in i.items() if k not in ("prompt", "triggers")},
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


def validate(kind: str, content: str) -> dict:
    """Checks a generated agent/skill file: frontmatter with name, title, description and a real instruction body."""
    m = FRONT.match(content.replace("\r\n", "\n"))
    if not m:
        raise AppError("invalid_item", "The file must start with a --- frontmatter --- block")
    tmp = _parse_text(content)
    missing = [k for k in ("name", "title", "description") if not re.search(rf"^{k}:\s*\S", m.group(1), re.M)]
    if missing:
        raise AppError("invalid_item", "Missing frontmatter fields: " + ", ".join(missing))
    if not NAME_RE.fullmatch(tmp["name"]):
        raise AppError("invalid_item_name", "name may contain only lowercase letters, digits, - and _")
    if len(tmp["prompt"]) < 120:
        raise AppError("invalid_item", "The instructions under the frontmatter are too short (min 120 characters)")
    from ..tools.registry import TOOLS
    if unknown := [t for t in tmp.get("tools") or [] if t not in TOOLS]:
        raise AppError("invalid_item", f"Unknown tools: {', '.join(unknown)}. Valid: {', '.join(sorted(TOOLS))}")
    return {k: v for k, v in tmp.items() if k != "triggers"}  # the compiled regex is not JSON


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


# "npx skills add google/skills", "npx -y skills add owner/repo --skill gcloud", "owner/repo",
# "https://github.com/owner/repo/tree/main/skills/cloud": a skills installer command or a repository of SKILL.md
# folders. Pasted into the MCP form it failed ("installs something and exits"): it is skills, not a server.
REPO_SPEC = re.compile(
    r"^\s*(?:(?:npx|bunx|pnpm\s+dlx|yarn\s+dlx)\s+(?:-y\s+|--yes\s+)?skills(?:@[\w.-]+)?\s+(?:add|install)\s+)?"
    r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^/\s]+)(?:/([^\s]*))?)?/?"
    r"((?:\s+--?[\w-]+(?:[ =](?!-)\S+)?)*)\s*$", re.I)


def repo_spec(spec: str) -> dict | None:
    """{owner, repo, ref, sub, only} of a skills repository spec, None when the text is something else."""
    m = REPO_SPEC.match(spec or "")
    if not m or m.group(1).lower() in ("http:", "https:", "www.github.com"):
        return None
    if not re.search(r"skills\s+(add|install)|github\.com/", spec, re.I) and spec.strip().count("/") != 1:
        return None
    only = re.findall(r"--?(?:skill|s)[ =]([\w.,-]+)", m.group(5) or "")
    return {"owner": m.group(1), "repo": m.group(2), "ref": m.group(3) or "", "sub": (m.group(4) or "").strip("/"),
            "only": [x for o in only for x in o.split(",") if x]}


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "AI-IQ-300"}
    try:
        from .. import connections
        if tok := connections._token():
            h["Authorization"] = f"Bearer {tok}"  # the connected account: 5000 requests an hour instead of 60
    except Exception:  # noqa: BLE001 - public repositories work without it
        pass
    return h


async def _repo_tree(spec: dict) -> tuple[str, list[dict]]:
    base = f"https://api.github.com/repos/{spec['owner']}/{spec['repo']}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_gh_headers()) as c:
        ref = spec["ref"]
        if not ref:
            r = await c.get(base)
            if r.status_code >= 400:
                raise AppError("repo_not_found", f"GitHub repository {spec['owner']}/{spec['repo']} was not found "
                                                 f"({r.status_code}).")
            ref = r.json().get("default_branch") or "main"
        r = await c.get(f"{base}/git/trees/{ref}", params={"recursive": "1"})
    if r.status_code >= 400:
        raise AppError("repo_not_found", f"Could not read {spec['owner']}/{spec['repo']}@{ref} ({r.status_code}).")
    return ref, [t for t in r.json().get("tree") or [] if t.get("type") == "blob"]


# Other tools' own skill commands. They take a name from their own catalog, not a GitHub repository:
#   hf skills add [name]        -> the Hugging Face marketplace (bucket huggingface/skills, marketplace.json);
#                                  no name = hf-cli, as the hf command does
#   gradio skills add [space]   -> no Space: the general gradio skill from the gradio repository; a Space id
#                                  (user/space): a skill generated from that Space's API, as gradio does
HF_CMD = re.compile(r"^\s*(?:hf|huggingface-cli)\s+skills\s+(?:add|install)\b(.*)$", re.I)
GRADIO_CMD = re.compile(r"^\s*(?:python\s+-m\s+)?gradio\s+skills\s+(?:add|install)\b(.*)$", re.I)
HF_BUCKET = "huggingface/skills"
HF_RESOLVE = f"https://huggingface.co/buckets/{HF_BUCKET}/resolve/"
GRADIO_RAW = "https://raw.githubusercontent.com/gradio-app/gradio/main/.agents/skills/gradio/"
SPACE_ID = re.compile(r"[\w.-]+/[\w.-]+")
TOO_MANY = 60


def _positional(rest: str) -> list[str]:
    """The arguments of a skills command that are not flags (--global, -g, --force, --cursor, --dest x...)."""
    out, skip = [], False
    for tok in (rest or "").split():
        if skip:
            skip = False
        elif tok in ("--dest", "-d"):
            skip = True
        elif not tok.startswith("-"):
            out.append(tok.strip("'\""))
    return out


def skill_source(text: str) -> dict | None:
    """Where a skills command / spec points: {"kind": "github"|"hf"|"gradio", ...}; None for anything else."""
    if m := HF_CMD.match(text or ""):
        pos = _positional(m.group(1))
        return {"kind": "hf", "label": f"Hugging Face ({HF_BUCKET})", "only": pos[:1] or ["hf-cli"]}
    if m := GRADIO_CMD.match(text or ""):
        pos = _positional(m.group(1))
        if pos and not SPACE_ID.fullmatch(pos[0]):
            raise AppError("bad_space", f"'{pos[0]}' is not a Hugging Face Space id (user/space).")
        return {"kind": "gradio", "label": f"Gradio Space {pos[0]}" if pos else "Gradio", "space": pos[0] if pos else ""}
    if spec := repo_spec(text):
        return {"kind": "github", "label": f"{spec['owner']}/{spec['repo']}", **spec}
    return None


def _source_or_fail(text: str) -> dict:
    src = skill_source(text)
    if not src:
        raise AppError("not_a_repo", "Give a skills source: owner/repo, its GitHub URL, 'npx skills add owner/repo', "
                                     "'hf skills add [name]' or 'gradio skills add [user/space]'.")
    return src


def _save_skill(text: str, name_hint: str, src: str, owner: str, links: list[tuple[str, str]], have: dict) -> str:
    """Writes one downloaded SKILL.md as a skill: name kept unless a built-in or another source's skill has it (then
    owner-name), `source:` and a title added, the files next to it listed as links the model can fetch."""
    name = name_from(text, name_hint)
    if name in have and have[name].get("source") != src:
        # a built-in or another source's skill of the same name (our own google.md): kept, this one gets the
        # owner in front
        name = re.sub(r"[^a-z0-9_-]+", "-", f"{owner}-{name}".lower()).strip("-")[:64]
    content = text.replace("\r\n", "\n")
    if not FRONT.match(content):
        content = f"---\nname: {name}\ndescription: {name_hint}\n---\n{content}"
    content = re.sub(r"^name:\s*.*$", f"name: {name}", content, count=1, flags=re.M)
    m = FRONT.match(content)
    extra = {"source": src}
    if not re.search(r"^title:", m.group(1), re.M):
        extra["title"] = name_hint.replace("-", " ").replace("_", " ").title() or name
    lines = m.group(1).splitlines() + [f"{k}: {' '.join(str(v).split())}" for k, v in extra.items()
                                       if not re.search(rf"^{k}:", m.group(1), re.M)]
    body = m.group(2)
    if links:
        body = (body.rstrip() + "\n\n## Files of this skill (fetch_url when the steps above point to one)\n"
                + "\n".join(f"- {label}: {url}" for label, url in links[:40]) + "\n")
    write("skills", name, "---\n" + "\n".join(lines) + "\n---\n" + body)
    have[name] = {"source": src}
    return name


def _check_picks(paths: list[str]) -> None:
    if not paths:
        raise AppError("nothing_picked", "Pick at least one skill.")
    if len(paths) > TOO_MANY:
        raise AppError("too_many", f"At most {TOO_MANY} skills at once: every skill is listed in the model's prompt.")


async def repo_skills(text: str) -> dict:
    """The skills a source offers, for the user to pick from."""
    src = _source_or_fail(text)
    have = skills()
    if src["kind"] == "hf":
        plugins = await _hf_marketplace()
        out = [{"path": p["name"], "name": p["name"].lower(), "group": HF_BUCKET, "description": p["description"],
                "installed": have.get(p["name"].lower(), {}).get("source") == f"hf:{HF_BUCKET}/{p['source']}",
                "picked": p["name"].lower() in [o.lower() for o in src["only"]]} for p in plugins]
        return {"repo": src["label"], "ref": "", "skills": out, "tokens_each": 40}
    if src["kind"] == "gradio":
        sid = src["space"]
        item = ({"path": f"space:{sid}", "name": re.sub(r"[^a-z0-9_-]+", "-", sid.replace("/", "-").lower()),
                 "group": "Hugging Face Spaces", "description": f"Use the {sid} Gradio Space through its API "
                 "(generated from the Space's API description)"} if sid else
                {"path": "gradio", "name": "gradio", "group": "gradio-app/gradio",
                 "description": "Build Gradio web UIs and demos in Python (gradio's own skill)"})
        item.update(installed=bool(have.get(item["name"], {}).get("source", "").startswith(("gradio", "space:"))),
                    picked=True)
        return {"repo": src["label"], "ref": "", "skills": [item], "tokens_each": 40}
    ref, tree = await _repo_tree(src)
    out = []
    for t in tree:
        p = t["path"]
        if not p.endswith("SKILL.md") or (src["sub"] and not p.startswith(src["sub"] + "/")):
            continue
        folder = p.rsplit("/", 1)[0] if "/" in p else src["repo"]
        name = re.sub(r"[^a-z0-9_-]+", "-", folder.rsplit("/", 1)[-1].lower()).strip("-")[:64] or "skill"
        group = folder.rsplit("/", 1)[0] if "/" in folder else ""
        out.append({"path": p, "name": name, "group": group, "size": t.get("size") or 0,
                    "installed": have.get(name, {}).get("source") == f"{src['owner']}/{src['repo']}/{p}",
                    "picked": name in src["only"]})
    # the same skill copied into several plugins (finding-google-skills, 2x): listed once
    seen, uniq = set(), []
    for s in sorted(out, key=lambda x: (x["path"].count("/"), x["path"])):
        if s["name"] not in seen:
            seen.add(s["name"]); uniq.append(s)
    uniq.sort(key=lambda x: (x["group"], x["name"]))
    return {"repo": src["label"], "ref": ref, "skills": uniq, "tokens_each": 40}


async def import_repo_skills(text: str, paths: list[str]) -> list[str]:
    """Imports the chosen skills. Each gets `source:` (so a later import updates it instead of making a copy) and a
    list of the files next to it (references, scripts) as links the model can fetch."""
    src = _source_or_fail(text)
    _check_picks(paths)
    have, done = skills(), []
    if src["kind"] == "hf":
        done = await _hf_import(paths, have)
    elif src["kind"] == "gradio":
        done = await _gradio_import(src["space"], have)
    else:
        ref, tree = await _repo_tree(src)
        blobs = {t["path"] for t in tree}
        raw_base = f"https://raw.githubusercontent.com/{src['owner']}/{src['repo']}/{ref}/"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            for p in paths:
                if p not in blobs or not p.endswith("SKILL.md"):
                    continue
                r = await c.get(raw_base + p)
                if r.status_code >= 400 or len(r.text) > MAX_SIZE or "\x00" in r.text:
                    continue
                folder = p.rsplit("/", 1)[0] if "/" in p else ""
                near = sorted(b for b in blobs if folder and b.startswith(folder + "/") and b != p)
                done.append(_save_skill(r.text, folder.rsplit("/", 1)[-1] or src["repo"],
                                        f"{src['owner']}/{src['repo']}/{p}", src["owner"],
                                        [(b[len(folder) + 1:], raw_base + b) for b in near], have))
    if not done:
        raise AppError("download_failed", "None of the chosen skills could be downloaded.")
    return done


async def _hf_marketplace() -> list[dict]:
    """[{name, source, description}] of the Hugging Face skills marketplace (what `hf skills list` shows)."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(HF_RESOLVE + "marketplace.json")
    if r.status_code >= 400:
        raise AppError("download_failed", f"The Hugging Face skills list could not be read ({r.status_code}).")
    try:
        plugins = r.json().get("plugins") or []
    except ValueError:
        raise AppError("download_failed", "The Hugging Face skills list is not valid JSON.")
    out = []
    for p in plugins:
        if isinstance(p, dict) and isinstance(p.get("name"), str) and isinstance(p.get("source"), str) \
                and NAME_RE.fullmatch(p["name"].lower()):
            source = p["source"].strip()
            while source.startswith("./"):
                source = source[2:]
            out.append({"name": p["name"], "source": source.strip("/"),
                        "description": str(p.get("description") or "").replace("''", "'")})
    return out


def _hf_files(prefix: str) -> list[str]:
    """Paths in the marketplace bucket under one skill's folder (references, scripts), [] when the installed
    huggingface_hub cannot list buckets: the skill itself still works."""
    try:
        from huggingface_hub import HfApi
        return [f.path for f in HfApi().list_bucket_tree(HF_BUCKET, prefix=prefix, recursive=True)
                if getattr(f, "path", "").startswith(prefix + "/")]
    except Exception:  # noqa: BLE001 - an older huggingface_hub, offline
        return []


async def _hf_import(names: list[str], have: dict) -> list[str]:
    import asyncio
    market = {p["name"].lower(): p for p in await _hf_marketplace()}
    done = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        for n in names:
            p = market.get(n.lower())
            if not p:
                continue
            r = await c.get(HF_RESOLVE + p["source"] + "/SKILL.md")
            if r.status_code >= 400 or len(r.text) > MAX_SIZE or "\x00" in r.text:
                continue
            files = await asyncio.to_thread(_hf_files, p["source"])
            links = [(f[len(p["source"]) + 1:], HF_RESOLVE + f) for f in sorted(files) if not f.endswith("/SKILL.md")]
            done.append(_save_skill(r.text, p["name"], f"hf:{HF_BUCKET}/{p['source']}", "hf", links, have))
    return done


async def _gradio_import(space: str, have: dict) -> list[str]:
    import asyncio
    if not space:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(GRADIO_RAW + "SKILL.md")
        if r.status_code >= 400:
            raise AppError("download_failed", f"The gradio skill could not be downloaded ({r.status_code}).")
        return [_save_skill(r.text, "gradio", "gradio-app/gradio/.agents/skills/gradio/SKILL.md", "gradio",
                            [("examples.md", GRADIO_RAW + "examples.md")], have)]
    text = await asyncio.to_thread(space_skill_md, space)
    name = re.sub(r"[^a-z0-9_-]+", "-", space.replace("/", "-").lower()).strip("-")[:64]
    return [_save_skill(text, name, f"space:{space}", space.split("/")[0], [], have)]


def space_skill_md(space: str) -> str:
    """A SKILL.md for a Gradio Space, from its API description (what `gradio skills add user/space` writes): every
    endpoint with its parameters and a Python call."""
    try:
        from gradio_client import Client
    except ImportError:
        raise AppError("missing_package", "gradio_client is not installed (pip install gradio_client).")
    try:
        client = Client(space, download_files=False, verbose=False)
        api = client.view_api(print_info=False, return_format="dict") or {}
    except Exception as e:  # noqa: BLE001 - a missing, private or sleeping Space
        raise AppError("space_failed", f"Could not reach the Space {space}: {str(e)[:200]}. It must exist, be public "
                                       "and be running.")
    about = ""
    try:
        from huggingface_hub import HfApi
        about = getattr(HfApi().space_info(space), "short_description", "") or ""
    except Exception:  # noqa: BLE001
        pass
    lines = ["---", f"name: {space.replace('/', '-').lower()}",
             f"description: Use the {space} Gradio Space through its API (Python gradio_client or HTTP)."
             + (f" Space: {' '.join(about.split())}" if about else ""), "---", f"# {space}", "",
             f"Call it with gradio_client (pip install gradio_client) - run the code with the run tool. Results that "
             f"are files come back as local paths. Space page: https://huggingface.co/spaces/{space}", ""]
    endpoints = api.get("named_endpoints") or {}
    unnamed = not endpoints
    for ep, info in (endpoints or api.get("unnamed_endpoints") or {}).items():
        params = info.get("parameters") or []
        lines.append(f"## `{ep}`" if not unnamed else f"## fn_index={ep}")
        for p in params:
            t = p.get("python_type")
            typ = t.get("type", "Any") if isinstance(t, dict) else str(t or "Any")
            pname = p.get("parameter_name") or p.get("label") or "input"
            dflt = f", default {p.get('parameter_default')!r}" if p.get("parameter_has_default") else " (required)"
            lines.append(f"- `{pname}` [{p.get('component', '')}]: {typ}{dflt}")
        for r_ in info.get("returns") or []:
            t = r_.get("python_type")
            lines.append(f"- returns `{r_.get('label') or 'output'}` [{r_.get('component', '')}]: "
                         f"{t.get('type', 'Any') if isinstance(t, dict) else t}")
        args = ", ".join(f"{p.get('parameter_name') or 'x'}=..." for p in params if p.get("parameter_name"))
        call = f'api_name="{ep}"' if not unnamed else f"fn_index={ep}"
        lines += ["", "```python", "from gradio_client import Client", f'client = Client("{space}")',
                  f"result = client.predict({args + ', ' if args else ''}{call})", "print(result)", "```", ""]
    if not (endpoints or api.get("unnamed_endpoints")):
        lines.append("The Space lists no API endpoints; open its page to see how it is used.")
    return "\n".join(lines) + "\n"


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
