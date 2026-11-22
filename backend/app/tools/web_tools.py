"""Web and place tools: web_search, fetch_url (downloads, GitHub), research, my_location, system_info, places, browser_check, web_screenshot.

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

from . import registry
from .registry import S, ToolResult, _network_gate, _path, _rel, clip, gate, tool  # noqa: F401
from .shell_tools import _port_busy


def clean_query(args: dict, body: str) -> str:
    """The search words of a call, never pieces of the protocol: a query that ran into the next tag
    (tahmini">\\n<tool name="todo), a todo list given as the body ([{"content": ...}]) or stray quotes and '>'.
    Empty when nothing usable is left (the caller refuses the call instead of searching for garbage)."""
    for cand in (body or "", str(args.get("query") or ""), str(args.get("q") or "")):
        q = re.split(r'["\']?\s*/?>?\s*</?tools?\b', cand, maxsplit=1)[0]
        q = q.strip()
        if not q or q[:1] in "[{" and re.search(r'"\w+"\s*:', q[:200]):
            continue  # a JSON value (a todo list, the arguments object) is not a query
        q = re.sub(r"^[>\s]+|[>\s/]+$", "", q)
        if q.count('"') % 2:  # a lone quote is the tag's, "exact phrase" quotes stay
            q = q[:-1] if q.endswith('"') else q[1:] if q.startswith('"') else q.replace('"', "")
        q = re.sub(r"\s+", " ", q)[:300].strip()
        if len(q) >= 2:
            return q
    return ""


NO_QUERY = ("Not searched: the call has no search words (its value was a piece of another call or a JSON list). "
            "Call it again with only the words to search between the tags, and close every call with </tool>.")


@tool("web_search", '<tool name="web_search">query</tool>',
      "Search the web (several engines merged). Returns titles, URLs and snippets. Use research for reading sources.",
      {"query": S("Search query")}, main="query", required=("query",))
async def web_search(ctx, args, body):
    from . import web
    if not (q := clean_query(args, body)):
        return ToolResult(False, NO_QUERY)
    if msg := await registry._network_gate(ctx, {"tool": "web_search", "query": q}):
        return ToolResult(False, msg)
    results, engines = await web.search(q)
    text = "\n".join(f"- {x['title']} <{x['url']}>\n  {x['snippet']}" for x in results)
    return ToolResult(bool(results), text or "no results (all engines failed or returned nothing)",
                      {"results": [{"title": x["title"], "url": x["url"], "snippet": _card_text(x.get("snippet", ""))}
                                   for x in results[:12]], "engines": engines})


@tool("fetch_url", '<tool name="fetch_url" url="https://..." query="optional: what to look for"></tool>',
      "Read a web page as plain text (real-browser fallback for JS pages; an archived copy when the page cannot be read). "
      "Also reads online documents with page numbers: PDF (scanned pages OCR'd), Word, Excel, PowerPoint, OpenDocument, "
      "CSV. For a long document give query to get the matching passages. If the result says BLOCKED, do not retry it.",
      {"url": S("https:// URL"), "query": S("Optional: what to look for in a long document"),
       "save": S("Optional: download the file to this path in the working folder instead of reading it (zip, "
                 "installer, image, any binary). Archives and binaries are saved automatically.")}, required=("url",))
async def fetch_url(ctx, args, body):
    from . import web
    url = args.get("url") or body.strip()
    if msg := await registry._network_gate(ctx, {"tool": "fetch_url", "url": url}):
        return ToolResult(False, msg)
    save = str(args.get("save") or "").strip()
    name = re.sub(r"[?#].*", "", url).rstrip("/").rsplit("/", 1)[-1]
    if not save and DOWNLOAD_EXT.search(name):
        # A zip / installer / package read as text is useless, and a weak model then said "downloaded" and tried to
        # unzip a file that was never written. Save it and say where.
        save = name if not re.fullmatch(r"(main|master|[\w.-]*\d[\w.-]*)\.(zip|tar\.gz|tgz)", name) else \
            "-".join(p for p in re.findall(r"github\.com/[^/]+/([^/]+)", url)[:1] + [name])
    if save:
        return await _download(ctx, url, save)
    if repo := _github_repo(url):
        # A model read a repository file by file through the API / blob pages (rate limited, slow, it looped): from
        # the third read of one repository, point it at the one-step download instead.
        reads = getattr(ctx, "gh_reads", None)
        if reads is None:
            reads = ctx.gh_reads = {}
        reads[repo] = reads.get(repo, 0) + 1
        if reads[repo] >= 4:
            o, n = repo.split("/")
            return ToolResult(False, f"Stop reading {repo} file by file. Get the whole repository in one step: "
                                     f"git clone --depth 1 https://github.com/{repo}.git, or fetch_url "
                                     f"url=\"https://github.com/{repo}/archive/HEAD.zip\" save=\"{n}.zip\" and unpack it "
                                     f"(tar -xf {n}.zip); then read the files on disk with list_dir / read_file.")
    r = await web.fetch(url, 8000, str(args.get("query") or "") if args.get("url") else "")
    if not r.get("ok"):
        return ToolResult(False, r.get("error") or f"failed (HTTP {r.get('status') or '?'}, nothing readable)",
                          {"blocked": r.get("blocked", False)})
    return ToolResult(True, f"# {r.get('title') or url}\n(source: {url}, via {r['via']})\n\n{r['text']}")


DOWNLOAD_EXT = re.compile(r"\.(zip|7z|rar|tar|tgz|tar\.gz|tar\.bz2|tar\.xz|gz|bz2|xz|exe|msi|msix|dmg|pkg|deb|rpm|"
                          r"appimage|apk|jar|war|whl|nupkg|phar|iso|img|bin|so|dll)$", re.I)


def _github_repo(url: str) -> str:
    """owner/repo when the URL reads one file or folder of a GitHub repository (API contents, blob, tree, raw)."""
    m = (re.match(r"https?://api\.github\.com/repos/([\w.-]+/[\w.-]+)/(contents|git/trees|readme)", url)
         or re.match(r"https?://github\.com/([\w.-]+/[\w.-]+)/(blob|tree|raw)/", url)
         or re.match(r"https?://raw\.githubusercontent\.com/([\w.-]+/[\w.-]+)/", url))
    return m.group(1) if m else ""


BINARY_SAVE = re.compile(r"\.(pdf|zip|7z|rar|gz|tgz|tar|exe|msi|dmg|apk|whl|jar|png|jpe?g|gif|webp|mp[34]|wav|"
                         r"ogg|webm|mov|docx|xlsx|pptx|onnx|gguf|bin|safetensors|ttf|otf|woff2?)$", re.I)


async def _download(ctx, url: str, save: str) -> ToolResult:
    """fetch_url save=...: the file at the URL into the working folder (streamed, 500 MB at most)."""
    import httpx
    target = _path(ctx, save)
    if msg := await gate(ctx, {"tool": "write_file", "path": str(target), "sha": hashlib.sha256(url.encode()).hexdigest()[:16]},
                         policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    size = 0
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=120),
                                     headers={"User-Agent": "Mozilla/5.0 (AI IQ 300 downloader)"}) as c:
            async with c.stream("GET", url) as r:
                if r.status_code >= 400:
                    return ToolResult(False, f"download failed: HTTP {r.status_code} for {url}")
                ctype = r.headers.get("content-type", "").lower()
                if (ctype.startswith(("text/html", "application/json")) and BINARY_SAVE.search(target.name)):
                    # a sign-in / error page saved under a .pdf / .zip name would replace a good file with junk
                    head = (await r.aread())[:400].decode("utf-8", "replace")
                    return ToolResult(False, f"download failed: {url} answered a web page ({ctype.split(';')[0]}), not "
                                             f"the {target.suffix} file - nothing was saved. Start of the answer: {head}")
                with open(tmp, "wb") as f:
                    async for chunk in r.aiter_bytes(1 << 16):
                        size += len(chunk)
                        if size > 500 * 1024 * 1024:
                            raise ValueError("larger than 500 MB")
                        if ctx.cancel.is_set():
                            raise ValueError("stopped")
                        f.write(chunk)
        tmp.replace(target)
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return ToolResult(False, f"download failed: {type(e).__name__}: {str(e)[:200]}")
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    hint = ""
    if re.search(r"\.zip$", rel, re.I):
        hint = (f" Unpack: PowerShell `Expand-Archive -Path '{rel}' -DestinationPath . -Force`, or `tar -xf {rel}` "
                "(Windows 10+, macOS, Linux). A GitHub ZIP unpacks into <repo>-<branch>/.")
    elif re.search(r"\.(tar\.gz|tgz|tar\.\w+|tar)$", rel, re.I):
        hint = f" Unpack: `tar -xf {rel}`."
    return ToolResult(True, f"downloaded {url} -> {rel} ({size:,} bytes; a file on disk, not text).{hint}",
                      {"path": rel, "created": True})


@tool("research", '<tool name="research">question or topic</tool>',
      "Web research: searches several engines and reads the best sources in parallel. Returns excerpts with URLs. "
      "Prefer this for factual or current questions; cite the URLs in your answer.",
      {"query": S("What to research")}, main="query", required=("query",))
async def research(ctx, args, body):
    from . import web
    if not (q := clean_query(args, body)):
        return ToolResult(False, NO_QUERY)
    if msg := await registry._network_gate(ctx, {"tool": "research", "query": q}):
        return ToolResult(False, msg)
    r = await web.research(q)
    parts = [f"Engines: {', '.join(r['engines']) or 'none'}"]
    parts += [f"## {p['title']}\nURL: {p['url']}\n{p['excerpt']}" for p in r["pages"]]
    if r["blocked"]:
        parts.append("Blocked by site protection (not readable): " + ", ".join(r["blocked"]))
    if len(r["pages"]) < 2 and r["results"]:  # few readable sources: the other results' snippets help too
        read = {p["url"] for p in r["pages"]}
        parts.append(("No source could be read. " if not r["pages"] else "") + "Search snippets:\n" +
                     "\n".join(f"- {x['title']} <{x['url']}>: {x['snippet']}" for x in r["results"] if x["url"] not in read))
    # the result cards of the step (title, site, a short excerpt; the sources it read first)
    read_urls = {p["url"] for p in r["pages"]}
    cards = [{"title": p["title"], "url": p["url"], "snippet": _card_text(p["excerpt"]), "read": True} for p in r["pages"]]
    cards += [{"title": x["title"], "url": x["url"], "snippet": _card_text(x.get("snippet", ""))}
              for x in r["results"] if x["url"] not in read_urls]
    return ToolResult(bool(r["pages"] or r["results"]), clip("\n\n".join(parts), 14000),
                      {"sources": [p["url"] for p in r["pages"]], "results": cards[:12], "engines": r["engines"]})


def _card_text(text: str) -> str:
    """A result card's excerpt: the first readable sentences, no Markdown / structured-data lines."""
    lines = [ln.strip() for ln in str(text or "").split("\n")
             if ln.strip() and not re.match(r"^(\[Structured data\]|[A-Z][A-Za-z]+:\s|#+\s*$|URL:)", ln.strip())]
    return re.sub(r"\s+", " ", re.sub(r"[#*`>|]+", " ", " ".join(lines)))[:260].strip()


@tool("my_location", '<tool name="my_location"></tool>',
      "The user's current location (this device's Wi-Fi/GPS through the app, else approximate from the internet "
      "address) with its street address and accuracy. Use it when the user says near me / here / around me / "
      "yakınımda / buralarda, then search places around it (places near=\"me\" does this by itself).",
      {"fresh": {"type": "boolean", "description": "Ask again instead of the location of the last minutes"}})
async def my_location(ctx, args, body):
    from .. import location
    if msg := await registry._network_gate(ctx, {"tool": "my_location"}):
        return ToolResult(False, msg)
    loc = await location.current("tr" if ctx.lang == "tr" else "en", str(args.get("fresh", "")).lower() in ("true", "1"))
    return ToolResult("error" not in loc, location.describe(loc), {k: loc.get(k) for k in ("lat", "lon", "accuracy_m", "source")})


@tool("system_info", '<tool name="system_info" part="all"></tool>',
      "This computer and this app in one call. part=hardware: CPU, cores, RAM modules, GPU and VRAM, board, BIOS, "
      "disks and free space, network, monitors, OS. part=software: the working folder of this chat and the "
      "dependency files in it, shells, CLI tools on PATH (node, npm, git, gh, php, java...), the app Python and every "
      "package installed in it, global npm packages, connected MCP servers and their tools, active web search engines, "
      "usable stock-photo / image services, how to find and download a GitHub project, skills, agents and commands, "
      "providers. Every answer starts with now: today's date, time, weekday and time zone of this computer "
      "(part=now returns only that). part=all (default): both. Use it for any 'my PC specs / donanım / sistem / what is installed' "
      "request and before installing something, instead of systeminfo/wmic/findstr/pip list commands.",
      {"part": {"type": "string", "description": "all (default) | hardware | software | now (date and time only)"}})
async def system_info(ctx, args, body):
    from . import sysinfo
    try:
        text = await asyncio.to_thread(sysinfo.report, str(args.get("part") or body or "all").strip(), ctx.root)
    except Exception as e:  # noqa: BLE001 - a missing source must not break the task
        return ToolResult(False, f"system_info failed: {e}")
    return ToolResult(True, text)


@tool("places", '<tool name="places" near="Kadıköy, İstanbul" radius="1500" map="true">kahve dükkanı</tool>',
      "Find places on a map (venues, shops, restaurants, hotels, pharmacies, competitors...) near a district, address "
      "or 'lat,lon': name, category, address, distance, phone, website, opening hours, and rating/review count when "
      "Google or Yandex Places is set up (else OpenStreetMap, free). map=true also writes an interactive map page "
      "(maps/<name>.html) the user can open. For comparing places or market research call it per place/area, then "
      "use research for reviews and details.",
      {"query": S("What to find (a kind of place or a name)"), "near": S("District, address, city or 'lat,lon'"),
       "radius": {"type": "integer", "description": "Search radius in metres (100-30000, default 1500)"},
       "limit": {"type": "integer", "description": "Max results (default 10)"},
       "map": {"type": "boolean", "description": "Also write an interactive map page"},
       "provider": S("Optional: google, yandex or osm", enum=["google", "yandex", "osm"])},
      main="query", required=("query",))
async def places(ctx, args, body):
    from . import maps
    q = (body.strip() or args.get("query", "")).strip()
    if not q:
        return ToolResult(False, "Say what to find (query) and where (near).")
    near = str(args.get("near") or "")
    if msg := await registry._network_gate(ctx, {"tool": "places", "query": q, "near": near}):
        return ToolResult(False, msg)
    from .. import location
    here = None
    if location.means_here(near):  # "near me": the user's real location (device, else approximate)
        here = await location.current("tr" if ctx.lang == "tr" else "en")
        if "error" in here:
            return ToolResult(False, location.describe(here))
        near = f"{here['lat']:.6f},{here['lon']:.6f}"
    try:
        res = await maps.find_places(q, near, int(args.get("radius") or 1500), int(args.get("limit") or 10),
                                     "tr" if ctx.lang == "tr" else "en", str(args.get("provider") or ""))
        if here and res.get("center"):
            res["center"].update(name=here.get("address") or res["center"]["name"], you=True,
                                 accuracy_m=here.get("accuracy_m"), source=here.get("source"))
    except Exception as e:  # network or provider failure: say it, the model can still use research
        return ToolResult(False, f"Map search failed: {type(e).__name__}: {str(e)[:300]}")
    text = (location.describe(here) + "\n" if here else "") + maps.format_places(res, ctx.lang)
    data = {"provider": res["provider"], "count": len(res["results"])}
    if str(args.get("map", "")).lower() in ("true", "1", "yes") and res["results"]:
        slug = re.sub(r"[^\w-]+", "-", f"{q}-{'here' if here else near}".lower(), flags=re.U).strip("-")[:60] or "map"
        target = _path(ctx, f"maps/{slug}.html")
        if msg := await gate(ctx, {"tool": "write_file", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
            return ToolResult(True, text + f"\n\n(Map page not written: {msg})", data)
        maps.write_map(target, f"{q} · {near}".strip(" ·"), res, ctx.lang)
        rel = _rel(ctx, target)
        ctx.files_changed.append(rel)
        text += f"\n\nInteractive map written: {rel} (the user can open it)."
        data["path"] = rel
    return ToolResult(bool(res["results"]), clip(text, 9000), data)


@tool("browser_check", '<tool name="browser_check" url="http://localhost:5173">what to verify</tool>',
      "Visual Tester: open the page headless (Playwright), screenshot it, and have the vision model review it.",
      {"url": S("Page URL"), "criteria": S("What to verify")}, main="criteria", required=("url",))
async def browser_check(ctx, args, body):
    from .visual import capture_and_review
    url, local_note = local_page_instead(ctx, str(args["url"]).strip())
    shot, review, console = await capture_and_review(url, body.strip(), ctx.session_dir or ctx.root)
    fix = ("\n[Page check: these console / network errors must be fixed in the code now; then check the page again "
           "before testing further.]" if console else "")
    return ToolResult(True, f"{local_note}screenshot: {shot}\nconsole + network errors: {console or 'none'}{fix}\n"
                            f"visual review:\n{review}",
                      {"screenshot": shot})


def local_page_instead(ctx, url: str) -> tuple[str, str]:
    """(url to open, note). A localhost address nothing listens on (a weak model screenshot localhost:5173 four times
    for a plain HTML site that never had a server): the page's own file in the project, when there is one."""
    m = re.match(r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::(\d+))?(/[^?#]*)?", url or "", re.I)
    if not m:
        return url, ""
    port = int(m.group(1) or 80)
    if _port_busy(port):
        return url, ""
    # A server of this chat is up on another port (Expo web on 8081 while the model looks at 19002): go there.
    chat = (ctx.owner or "").split(":")[0]
    urls = []
    for p in manager._owned(chat) if chat else []:
        for line in list(p.tail)[-80:]:
            for u in re.findall(r"https?://(?:localhost|127\.0\.0\.1):(\d+)", line):
                if int(u) != port and int(u) not in urls and _port_busy(int(u)):
                    urls.append(int(u))
    if len(urls) == 1:
        new = f"http://localhost:{urls[0]}{m.group(2) or '/'}"
        return new, (f"[Nothing is running on port {port}; this chat's server answers on port {urls[0]}, so {new} "
                     "was opened. Use the address the start output prints.]\n")
    page = (m.group(2) or "/").lstrip("/") or "index.html"
    bases = [ctx.root] + ([_path(ctx, ctx.shell_cwd)] if ctx.shell_cwd else [])
    for base in bases:
        for cand in (base / page, base / page / "index.html"):
            if cand.is_file() and cand.suffix.lower() in (".html", ".htm"):
                return cand.resolve().as_uri(), (f"[Nothing is running on port {port}, so the page's file "
                                                 f"{_rel(ctx, cand)} was opened directly. For PHP / Node / anything "
                                                 "that needs a server, start it first with start.]\n")
    return url, ""


@tool("web_screenshot", '<tool name="web_screenshot" url="https://example.com" device="desktop|laptop|tablet|mobile" full_page="true"></tool>',
      "Take a screenshot of a web page (or an .html file in the working folder) with a real browser; the image shows "
      "in the chat. Options: device, width/height, full_page (default true), selector (one element), dark, "
      "wait_ms, hide (CSS selectors to hide, e.g. cookie banners), path (.png, .jpg or .pdf).",
      {"url": S("https:// URL or a .html path in the working folder"),
       "device": S("Viewport preset", enum=["desktop", "laptop", "tablet", "mobile"]),
       "width": S("Viewport width in px (optional)"), "height": S("Viewport height in px (optional)"),
       "full_page": S("true: whole page, false: first screen", enum=["true", "false"]),
       "selector": S("CSS selector of one element to capture (optional)"),
       "dark": S("true: prefers-color-scheme dark", enum=["true", "false"]),
       "wait_ms": S("Extra wait before capture, ms (optional)"),
       "hide": S("CSS selectors to hide before capture (optional)"),
       "path": S("Output path, default screenshots/<site>-<time>.png")}, main="url", required=("url",))
async def web_screenshot(ctx, args, body):
    from . import shot
    url = (args.get("url") or body).strip()
    url, local_note = local_page_instead(ctx, url)
    if url.lower().startswith("file:"):  # file:///C:/... of a page in the working folder: check it as a path
        from urllib.parse import urlsplit
        from urllib.request import url2pathname
        url = url2pathname(urlsplit(url).path)
    if not re.match(r"https?://", url):
        local = _path(ctx, url)
        if not local.is_file():
            return ToolResult(False, f"Not a http(s) URL or a file in the working folder: {url}")
        url = local.resolve().as_uri()
    elif msg := await registry._network_gate(ctx, {"tool": "web_screenshot", "url": url}):
        return ToolResult(False, msg)
    rel = (args.get("path") or "").strip() or shot.default_name(url, "png")
    if Path(rel).suffix.lower() not in (".png", ".jpg", ".jpeg", ".pdf"):
        rel += ".png"
    target = _path(ctx, rel)
    if msg := await gate(ctx, {"tool": "web_screenshot", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    flag = lambda k, d=False: str(args.get(k, d)).lower() in ("true", "1", "yes")  # noqa: E731
    num = lambda k: int(re.sub(r"\D", "", str(args.get(k) or "")) or 0) or None  # noqa: E731
    try:
        info = await shot.capture(url, target, device=args.get("device") or "desktop", width=num("width"),
                                  height=num("height"), full_page=flag("full_page", True), selector=args.get("selector") or "",
                                  dark=flag("dark"), wait_ms=num("wait_ms") or 0, hide=args.get("hide") or "", lang=ctx.lang)
    except ImportError:
        return ToolResult(False, "Playwright is not installed (run install.bat / install.sh).")
    except Exception as e:  # navigation errors, missing browser, bad selector
        msg = str(e).splitlines()[0][:300]
        if "Executable doesn't exist" in str(e):
            msg = "Chromium for Playwright is missing: run `python -m playwright install chromium`."
        return ToolResult(False, f"screenshot failed: {msg}")
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    from .visual import describe_for
    seen = await describe_for(ctx.model, target, ctx.goal) if target.suffix.lower() != ".pdf" else None
    look = (f"The vision model {seen[0]} looked at the screenshot:\n{seen[1]}\n\n" if seen else
            "If you describe the page, use ONLY the page content below (you may not be able to see the image); never "
            "guess colors, layout or elements that are not listed.\n")
    return ToolResult(True, local_note + f"saved {out} ({info['width']}x{info['height']}px) - {info['title'] or info['final_url']}\n"
                            "The image is already shown to the user in the chat. " + look +
                            f"Headings: {' | '.join(info.get('headings') or []) or '-'}\n"
                            f"Buttons/links: {' | '.join(info.get('buttons') or []) or '-'}\n"
                            f"Images on the page: {info.get('images', 0)}; page background: {info.get('background', '?')}\n"
                            + (("Problems found while the page ran (fix them, then take the screenshot again):\n- "
                                + "\n- ".join(info["problems"]) + "\n") if info.get("problems")
                               else "The page's JavaScript ran without errors; every image loaded.\n") +
                            f"Visible text:\n{info.get('text') or '(none)'}",
                      {"path": out, "screenshot": out, "url": info["final_url"], "title": info["title"],
                       "size": [info["width"], info["height"]]})
