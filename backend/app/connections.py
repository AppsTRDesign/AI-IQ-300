"""Settings > Connections: one-click sign-in to GitHub, Google and Microsoft. Each connection sets up the service's MCP
server by itself (the user no longer types URLs and tokens into Settings > MCP), and GitHub also imports repositories as
projects and keeps them up to date (like Codex).

- GitHub: the token comes from what the computer already has - the GitHub CLI (`gh auth token`) or Git Credential
  Manager (`git credential fill`, which opens GitHub's own browser sign-in when nothing is stored yet). A personal access
  token pasted by the user is the fallback. The token goes to the official remote MCP server
  https://api.githubcopilot.com/mcp/ and is used for clone / fetch / pull of imported repositories.
- Google: Google's official Workspace MCP servers (Gmail, Drive, Docs, Sheets, Slides, Calendar, Chat, People, search)
  need an OAuth client of the user's own Google Cloud project (no dynamic registration). After the client ID / secret
  are saved once, "Connect" is one browser sign-in; the token (refreshed automatically) goes to every chosen server.
- Microsoft 365: the open-source @softeria/ms-365-mcp-server (Outlook mail and calendar, OneDrive, Excel, OneNote, To Do,
  Teams with org mode) signs in with Microsoft's device code: the app shows the code and opens the page.
Tokens live only in secrets.json; the model never sees them."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .config import get_secret, load_settings, save_settings, set_secret


class ConnError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load(name: str) -> dict:
    try:
        v = json.loads(get_secret(f"conn_{name}") or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


def _store(name: str, data: dict | None) -> None:
    set_secret(f"conn_{name}", json.dumps(data) if data else None)


async def _set_mcp(sid: str, cfg: dict, headers: dict | None = None, oauth: dict | None = None) -> None:
    """Adds or replaces a server in Settings > MCP, marked as managed by a connection."""
    from . import mcp_client
    save_settings({"mcp_servers": {sid: None}})
    save_settings({"mcp_servers": {sid: {"enabled": True, "cwd": "", "args": [], "command": "", "url": "", **cfg}}})
    sec = mcp_client.secret_parts(sid)
    if headers is not None:
        sec["headers"] = headers
    set_secret(f"mcp_{sid}", json.dumps(sec) if (sec.get("env") or sec.get("headers")) else None)
    if oauth is not None:
        mcp_client._oauth_save(sid, oauth)
    try:
        await mcp_client.restart(sid)
    except Exception:  # noqa: BLE001 - shown on the MCP card; the connection itself is saved
        pass


async def _drop_mcp(sids: list[str]) -> None:
    from . import mcp_client
    for sid in sids:
        save_settings({"mcp_servers": {sid: None}})
        set_secret(f"mcp_{sid}", None)
        set_secret(f"mcp_oauth_{sid}", None)
    await mcp_client.ensure()


def _managed(kind: str) -> list[str]:
    return [k for k, v in (load_settings().get("mcp_servers") or {}).items() if (v or {}).get("managed") == kind]


async def _proc(*argv: str, stdin: str | None = None, timeout: float = 30, cwd: str | None = None,
                env: dict | None = None) -> tuple[int, str, str]:
    import os
    p = await asyncio.create_subprocess_exec(*argv, cwd=cwd, env={**os.environ, **(env or {})},
                                             stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(p.communicate(stdin.encode() if stdin is not None else None), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return -1, "", "timeout"
    return p.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


# ---------------------------------------------------------------------------------------------------------- GitHub
GITHUB_MCP = "https://api.githubcopilot.com/mcp/"
GITHUB_TOKEN_PAGE = ("https://github.com/settings/tokens/new?scopes=repo,read:org,workflow,gist"
                     "&description=AI%20IQ%20300")


async def _github_user(token: str) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}",
                                                                 "Accept": "application/vnd.github+json"})
    if r.status_code == 401:
        raise ConnError("github_bad_token", "GitHub did not accept this token (expired or wrong).")
    if r.status_code >= 400:
        raise ConnError("github_error", f"GitHub answered HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def _github_token_from_computer() -> tuple[str, str]:
    """(token, method) from the GitHub CLI or Git Credential Manager; ('', '') when neither has one."""
    if gh := shutil.which("gh"):
        code, out, _ = await _proc(gh, "auth", "token", timeout=15)
        if code == 0 and out.strip():
            return out.strip(), "gh"
    if git := shutil.which("git"):
        # Git Credential Manager (part of Git for Windows) answers from its store, or opens GitHub's browser sign-in.
        code, out, _ = await _proc(git, "credential", "fill", stdin="protocol=https\nhost=github.com\n\n", timeout=300,
                                   env={"GIT_TERMINAL_PROMPT": "0"})
        m = re.search(r"^password=(.+)$", out, re.M)
        if code == 0 and m:
            return m.group(1).strip(), "git"
    return "", ""


async def github_connect(token: str | None = None) -> dict:
    method = "token"
    if not (token or "").strip():
        token, method = await _github_token_from_computer()
        if not token:
            raise ConnError("github_no_token", "No GitHub sign-in was found on this computer (GitHub CLI or Git "
                                               "Credential Manager). Create a token on the opened page and paste it.")
    token = token.strip()
    user = await _github_user(token)
    _store("github", {"token": token, "login": user.get("login"), "name": user.get("name"), "method": method,
                      "avatar": user.get("avatar_url"), "at": time.time()})
    await _set_mcp("github", {"name": "GitHub", "transport": "http", "url": GITHUB_MCP, "managed": "github"},
                   headers={"Authorization": f"Bearer {token}"})
    return github_status()


def github_status() -> dict:
    d = _load("github")
    return {"connected": bool(d.get("token")), "login": d.get("login"), "name": d.get("name"),
            "method": d.get("method"), "avatar": d.get("avatar"), "token_page": GITHUB_TOKEN_PAGE,
            "git": bool(shutil.which("git")), "gh": bool(shutil.which("gh"))}


async def github_disconnect() -> None:
    _store("github", None)
    await _drop_mcp(_managed("github"))


def _token() -> str:
    tok = _load("github").get("token")
    if not tok:
        raise ConnError("github_not_connected", "Connect GitHub first (Settings > Connections).")
    return tok


async def github_repos(query: str = "") -> list[dict]:
    import httpx
    tok, out = _token(), []
    async with httpx.AsyncClient(timeout=30) as c:
        for page in range(1, 6):
            r = await c.get("https://api.github.com/user/repos", params={
                "per_page": 100, "page": page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
                headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
            if r.status_code >= 400:
                raise ConnError("github_error", f"GitHub answered HTTP {r.status_code}")
            items = r.json()
            out += items
            if len(items) < 100:
                break
    have = {_slug(p.get("remote") or ""): p["id"] for p in _github_projects()}
    q = query.strip().lower()
    return [{"full_name": x["full_name"], "private": x["private"], "description": x.get("description") or "",
             "default_branch": x.get("default_branch") or "main", "updated": x.get("pushed_at"),
             "language": x.get("language"), "project_id": have.get(x["full_name"].lower())}
            for x in out if not q or q in x["full_name"].lower() or q in (x.get("description") or "").lower()]


def _auth_args(token: str) -> list[str]:
    """git -c options that send the token for github.com only, without writing it into the repository's config."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", "credential.helper=", "-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]


def _slug(remote: str) -> str:
    m = re.search(r"github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?/?$", remote or "", re.I)
    return m.group(1).lower() if m else ""


async def _git(cwd: str, *args: str, timeout: float = 120, auth: bool = True) -> tuple[int, str]:
    git = shutil.which("git")
    if not git:
        raise ConnError("git_missing", "Git is not installed: winget install --id Git.Git -e (macOS: xcode-select "
                                       "--install; Linux: apt install git).")
    tok = _load("github").get("token") if auth else None
    code, out, err = await _proc(git, *(_auth_args(tok) if tok else []), *args, cwd=cwd, timeout=timeout,
                                 env={"GIT_TERMINAL_PROMPT": "0"})
    text = (out + ("\n" + err if err.strip() else "")).strip()
    if tok:
        text = text.replace(tok, "***")
    return code, text


async def github_import(full_name: str, branch: str = "") -> dict:
    from . import workspace
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", full_name or ""):
        raise ConnError("github_bad_repo", "Repository must be owner/name.")
    _token()
    for p in _github_projects():
        if _slug(p.get("remote") or "") == full_name.lower():
            return {**p, "existing": True}
    name = full_name.split("/")[1]
    target = workspace.PROJECTS_DIR / f"{workspace.slugify(name)}-{secrets.token_hex(2)}"
    target.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--quiet", *(["--branch", branch] if branch else []), f"https://github.com/{full_name}.git", str(target)]
    code, out = await _git(str(target.parent), *args, timeout=900)
    if code != 0:
        from .config import rmtree_long
        if target.exists():
            rmtree_long(target)
        raise ConnError("github_clone_failed", out[-400:] or "git clone failed")
    proj = workspace.create_project(name, str(target))
    return {**proj, "remote": f"https://github.com/{full_name}.git", "existing": False}


def _github_projects() -> list[dict]:
    """Projects whose folder is a git repository with a github.com origin (imported here or added from disk)."""
    from . import db
    out = []
    for p in db.query("SELECT id, name, path FROM projects"):
        cfg = Path(p["path"]) / ".git" / "config"
        try:
            text = cfg.read_text(encoding="utf-8", errors="replace") if cfg.is_file() else ""
        except OSError:
            text = ""
        m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text)
        if m and "github.com" in m.group(1).lower():
            out.append({"id": p["id"], "name": p["name"], "path": p["path"], "remote": m.group(1)})
    return out


async def project_git(pid: str, fetch: bool = True) -> dict:
    """Branch, commits behind / ahead of the remote and local changes of a project's repository."""
    from . import workspace
    proj = workspace.get_project(pid)
    if not proj or not (Path(proj["path"]) / ".git").exists():
        raise ConnError("not_a_repo", "This project is not a git repository.")
    cwd = proj["path"]
    if fetch:
        code, out = await _git(cwd, "fetch", "--quiet", "origin", timeout=120)
        if code != 0:
            return {"ok": False, "error": out[-300:]}
    _, branch = await _git(cwd, "rev-parse", "--abbrev-ref", "HEAD", auth=False)
    code, counts = await _git(cwd, "rev-list", "--left-right", "--count", "HEAD...@{u}", auth=False)
    ahead, behind = (int(x) for x in counts.split()[:2]) if code == 0 and len(counts.split()) >= 2 else (0, 0)
    _, dirty = await _git(cwd, "status", "--porcelain", auth=False)
    _, last = await _git(cwd, "log", "-1", "--format=%h %s (%cr)", "@{u}" if code == 0 else "HEAD", auth=False)
    return {"ok": True, "branch": branch.strip(), "ahead": ahead, "behind": behind, "has_upstream": code == 0,
            "dirty": len([ln for ln in dirty.splitlines() if ln.strip()]), "remote_last": last.strip()[:200]}


async def project_pull(pid: str, stash: bool = False) -> dict:
    """Brings the project up to date with its remote (fast-forward only: local commits are never rewritten). Local
    changes stop it unless stash=True (they are set aside, the update comes in, they are put back)."""
    from . import workspace
    st = await project_git(pid)
    if not st.get("ok"):
        raise ConnError("git_fetch_failed", st.get("error") or "fetch failed")
    cwd = workspace.get_project(pid)["path"]
    if not st["behind"]:
        return {**st, "updated": 0}
    if st["dirty"] and not stash:
        raise ConnError("git_dirty", f"{st['dirty']} local change(s) in the project: update with 'keep my changes' "
                                     "to set them aside and put them back after the update.")
    if st["dirty"]:
        code, out = await _git(cwd, "stash", "push", "--include-untracked", "-m", "AI IQ 300 update", auth=False)
        if code != 0:
            raise ConnError("git_stash_failed", out[-300:])
    code, out = await _git(cwd, "merge", "--ff-only", "@{u}", auth=False)
    if code != 0:
        if st["dirty"]:
            await _git(cwd, "stash", "pop", auth=False)
        raise ConnError("git_diverged", "The project has its own commits that the remote does not have: it cannot be "
                                        "updated by fast-forward. " + out[-200:])
    note = ""
    if st["dirty"]:
        c2, o2 = await _git(cwd, "stash", "pop", auth=False)
        if c2 != 0:
            note = "Your changes conflict with the update; they are kept in git stash. " + o2[-200:]
    return {**(await project_git(pid, fetch=False)), "updated": st["behind"], "note": note}


# ---------------------------------------------------------------------------------------------------------- Google
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_D = "https://www.googleapis.com/auth/"
GOOGLE_SERVICES = {  # Google Workspace remote MCP servers (developers.google.com/workspace/guides/configure-mcp-servers)
    "gmail": ("Gmail", "https://gmailmcp.googleapis.com/mcp/v1", ["gmail.readonly", "gmail.compose", "gmail.modify"]),
    "drive": ("Google Drive", "https://drivemcp.googleapis.com/mcp/v1", ["drive.readonly", "drive.file"]),
    "docs": ("Google Docs", "https://docsmcp.googleapis.com/mcp/v1",
             ["drive.readonly", "drive.file", "documents.readonly", "documents"]),
    "sheets": ("Google Sheets", "https://sheetsmcp.googleapis.com/mcp/v1",
               ["drive.readonly", "drive.file", "spreadsheets.readonly", "spreadsheets"]),
    "slides": ("Google Slides", "https://slidesmcp.googleapis.com/mcp/v1",
               ["drive.readonly", "drive.file", "presentations.readonly", "presentations"]),
    "calendar": ("Google Calendar", "https://calendarmcp.googleapis.com/mcp/v1",
                 ["calendar.calendarlist.readonly", "calendar.events.freebusy", "calendar.events.readonly",
                  "calendar.events"]),
    "chat": ("Google Chat", "https://chatmcp.googleapis.com/mcp/v1",
             ["chat.spaces.readonly", "chat.memberships.readonly", "chat.messages.readonly", "chat.messages.create"]),
    "people": ("Google Contacts", "https://people.googleapis.com/mcp/v1",
               ["userinfo.profile", "contacts.readonly", "directory.readonly"]),
    "search": ("Google Workspace search", "https://workspacemcp.googleapis.com/mcp/v1",
               ["gmail.readonly", "drive.readonly", "calendar.readonly", "chat.messages.readonly",
                "chat.spaces.readonly", "chat.memberships.readonly"]),
}
GOOGLE_DEFAULT = ["gmail", "drive", "docs", "sheets", "calendar"]
# The product API each MCP server works through; the MCP service itself (gmailmcp.googleapis.com...) must be enabled
# too. Neither is on in a new Cloud project: the servers listed tools but every call answered "Calendar MCP API has
# not been used in project N before or it is disabled".
GOOGLE_BASE_API = {"gmail": "gmail.googleapis.com", "drive": "drive.googleapis.com", "docs": "docs.googleapis.com",
                   "sheets": "sheets.googleapis.com", "slides": "slides.googleapis.com",
                   "calendar": "calendar-json.googleapis.com", "chat": "chat.googleapis.com",
                   "people": "people.googleapis.com"}
_GOOGLE_PENDING: dict[str, dict] = {}


def google_apis(services: list[str]) -> list[str]:
    out = []
    for s in services:
        if s not in GOOGLE_SERVICES:
            continue
        mcp_host = urlsplit(GOOGLE_SERVICES[s][1]).hostname or ""
        out += [a for a in (GOOGLE_BASE_API.get(s), mcp_host) if a]
    return list(dict.fromkeys(out))


def google_enable_url(client_id: str, services: list[str]) -> str:
    """One Cloud console page that enables every API the chosen services need, in the OAuth client's own project
    (its number is the client id's prefix)."""
    project = (client_id or "").split("-", 1)[0]
    apis = google_apis(services)
    if not project.isdigit() or not apis:
        return ""
    return f"https://console.cloud.google.com/flows/enableapi?apiid={','.join(apis)}&project={project}"


def google_status() -> dict:
    d = _load("google")
    services = d.get("services") or GOOGLE_DEFAULT
    return {"connected": bool(d.get("refresh_token")), "email": d.get("email"), "client_set": bool(d.get("client_id")),
            "client_id": (d.get("client_id") or "")[:12] + "…" if d.get("client_id") else "",
            "services": services, "at": d.get("at"),
            "enable_url": google_enable_url(d.get("client_id") or "", services),
            "all_services": [{"id": k, "name": v[0]} for k, v in GOOGLE_SERVICES.items()]}


def google_client(client_id: str, client_secret: str) -> dict:
    client_id, client_secret = (client_id or "").strip(), (client_secret or "").strip()
    if not re.fullmatch(r"[\w.-]+\.apps\.googleusercontent\.com", client_id):
        raise ConnError("google_bad_client", "The client ID ends with .apps.googleusercontent.com (Google Cloud > "
                                             "Google Auth Platform > Clients).")
    if not client_secret:
        raise ConnError("google_bad_client", "The client secret is required.")
    d = _load("google")
    if d.get("client_id") != client_id:
        d = {}  # another Google Cloud project: the old sign-in does not belong to it
    _store("google", {**d, "client_id": client_id, "client_secret": client_secret})
    return google_status()


def google_start(redirect_uri: str, services: list[str]) -> str:
    d = _load("google")
    if not d.get("client_id"):
        raise ConnError("google_no_client", "Save the OAuth client ID and secret first.")
    services = [s for s in services if s in GOOGLE_SERVICES] or GOOGLE_DEFAULT
    scopes = ["openid", "email"] + sorted({_D + s for k in services for s in GOOGLE_SERVICES[k][2]})
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(18)
    for k in [k for k, v in _GOOGLE_PENDING.items() if time.time() - v["at"] > 900]:
        _GOOGLE_PENDING.pop(k, None)
    _GOOGLE_PENDING[state] = {"verifier": verifier, "redirect_uri": redirect_uri, "services": services, "at": time.time()}
    return GOOGLE_AUTH + "?" + urlencode({
        "client_id": d["client_id"], "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(scopes),
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})


async def google_finish(state: str, code: str) -> dict:
    import httpx
    flow = _GOOGLE_PENDING.pop(state, None)
    if not flow:
        raise ConnError("google_expired", "This sign-in link expired or was already used; connect again.")
    d = _load("google")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GOOGLE_TOKEN, data={"code": code, "client_id": d["client_id"],
                                             "client_secret": d["client_secret"], "redirect_uri": flow["redirect_uri"],
                                             "grant_type": "authorization_code", "code_verifier": flow["verifier"]})
    if r.status_code >= 400:
        raise ConnError("google_token", f"Google refused the sign-in: {r.text[:300]}")
    tok = r.json()
    email = ""
    if idt := tok.get("id_token"):
        try:
            part = idt.split(".")[1]
            email = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("email", "")
        except (ValueError, IndexError):
            pass
    refresh = tok.get("refresh_token") or d.get("refresh_token")
    _store("google", {**d, "refresh_token": refresh, "email": email, "services": flow["services"], "at": time.time(),
                      "access_token": tok["access_token"],
                      "expires_at": time.time() + float(tok.get("expires_in") or 3600)})
    oauth = {"client_id": d["client_id"], "client_secret": d["client_secret"], "token_endpoint": GOOGLE_TOKEN,
             "access_token": tok["access_token"], "refresh_token": refresh,
             "expires_at": time.time() + float(tok.get("expires_in") or 3600)}
    await _drop_mcp([s for s in _managed("google") if s.removeprefix("google-") not in flow["services"]])
    for k in flow["services"]:
        name, url, _ = GOOGLE_SERVICES[k]
        await _set_mcp(f"google-{k}", {"name": name, "transport": "http", "url": url, "managed": "google"},
                       oauth=dict(oauth))
    return google_status()


def google_connected() -> bool:
    return bool(_load("google").get("refresh_token"))


async def google_token() -> str:
    """An access token for Google's ordinary REST APIs (Gmail, Drive, Calendar, Sheets, Docs...), refreshed from the
    stored sign-in. These work without the Workspace MCP Developer Preview, which the MCP servers need."""
    import httpx
    d = _load("google")
    if not d.get("refresh_token"):
        raise ConnError("google_not_connected", "Google is not connected: Settings > Connections > Google.")
    if d.get("access_token") and time.time() < float(d.get("expires_at") or 0) - 60:
        return d["access_token"]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GOOGLE_TOKEN, data={"client_id": d["client_id"], "client_secret": d["client_secret"],
                                             "refresh_token": d["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code >= 400:
        raise ConnError("google_token", "The Google sign-in expired or was revoked: reconnect Google in Settings > "
                                        f"Connections. ({r.text[:200]})")
    tok = r.json()
    d = _load("google")  # re-read: another call may have stored meanwhile
    _store("google", {**d, "access_token": tok["access_token"],
                      "expires_at": time.time() + float(tok.get("expires_in") or 3600)})
    return tok["access_token"]


# One cheap read per product API; "SERVICE_DISABLED" / "has not been used in project" means it is off. (The card
# showed "enable the APIs" all the time, even after they were enabled.)
GOOGLE_PROBES = {
    "gmail": "https://gmail.googleapis.com/gmail/v1/users/me/profile",
    "drive": "https://www.googleapis.com/drive/v3/about?fields=user",
    "docs": "https://docs.googleapis.com/v1/documents/aiiq-probe",
    "sheets": "https://sheets.googleapis.com/v4/spreadsheets/aiiq-probe",
    "slides": "https://slides.googleapis.com/v1/presentations/aiiq-probe",
    "calendar": "https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1",
    "chat": "https://chat.googleapis.com/v1/spaces?pageSize=1",
    "people": "https://people.googleapis.com/v1/people/me?personFields=names",
}
_API_CHECK: dict = {}


async def google_api_check(force: bool = False) -> dict:
    """Which chosen services' APIs are still disabled in the user's Cloud project (cached 10 minutes)."""
    d = _load("google")
    if not d.get("refresh_token"):
        return {"disabled": [], "enable_url": ""}
    services = [s for s in (d.get("services") or GOOGLE_DEFAULT) if s in GOOGLE_PROBES]
    key = (d.get("client_id"), tuple(services))
    if not force and _API_CHECK.get("key") == key and time.time() - _API_CHECK.get("at", 0) < 600:
        return _API_CHECK["result"]

    async def probe(s: str) -> str | None:
        try:
            status, _, body = await google_api("GET", GOOGLE_PROBES[s])
        except Exception:  # noqa: BLE001  network / sign-in: not reported as disabled
            return None
        text = body[:2000].decode("utf-8", "replace")
        return s if status == 403 and ("SERVICE_DISABLED" in text or "has not been used in project" in text) else None
    disabled = [s for s in await asyncio.gather(*(probe(s) for s in services)) if s]
    mcp_blocked = await google_mcp_check()
    result = {"disabled": disabled, "enable_url": google_enable_url(d.get("client_id") or "", disabled),
              "mcp_blocked": mcp_blocked}
    _API_CHECK.update({"key": key, "at": time.time(), "result": result})
    return result


MCP_PREVIEW_ERR = re.compile(r"enrolled in the Google Workspace Developer Preview Program", re.I)


def google_mcp_blocked() -> bool:
    """True while Google's MCP servers refuse this project (last check within a day)."""
    d = _load("google")
    return bool(d.get("mcp_blocked")) and time.time() - float(d.get("mcp_checked") or 0) < 86400


def google_mcp_seen(blocked: bool) -> None:
    d = _load("google")
    if d and (bool(d.get("mcp_blocked")) != blocked or time.time() - float(d.get("mcp_checked") or 0) > 3600):
        _store("google", {**d, "mcp_blocked": blocked, "mcp_checked": time.time()})


async def google_mcp_check() -> bool | None:
    """Calls one harmless read tool of a google-* MCP server: False = works, True = Developer Preview refusal,
    None = nothing to check."""
    from . import mcp_client
    sids = [s for s in _managed("google") if s in mcp_client.servers_cfg()]
    for sid in sorted(sids, key=lambda s: s != "google-calendar"):
        try:
            await asyncio.wait_for(mcp_client.ensure(sid), 30)
            srv = mcp_client._servers.get(sid)
            tool = next((t for t in (srv.tools if srv else []) if (t.get("annotations") or {}).get("readOnlyHint")
                         and not (t.get("inputSchema") or {}).get("required")), None)
            if not tool:
                continue
            ok, out = await mcp_client.call(sid, tool["name"], {})
        except Exception:  # noqa: BLE001
            continue
        blocked = bool(MCP_PREVIEW_ERR.search(out or ""))
        google_mcp_seen(blocked)
        return blocked
    return None


GOOGLE_API_HOST = re.compile(r"^https://[a-z0-9-]+\.googleapis\.com/", re.I)


async def google_api(method: str, url: str, params: dict | None = None, body=None, raw: bytes | None = None,
                     content_type: str = "") -> tuple[int, str, bytes]:
    """One call to a Google REST API with the user's token: (status, content type, body bytes)."""
    import httpx
    if not GOOGLE_API_HOST.match(url or ""):
        raise ConnError("google_bad_url", "Only https://<api>.googleapis.com/... addresses (e.g. "
                                          "https://gmail.googleapis.com/gmail/v1/users/me/messages).")
    headers = {"Authorization": f"Bearer {await google_token()}"}
    kw: dict = {"params": params or None}
    if raw is not None:
        kw["content"], headers["Content-Type"] = raw, content_type or "application/octet-stream"
    elif body is not None:
        kw["json"] = body
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.request(method.upper(), url, headers=headers, **kw)
    return r.status_code, r.headers.get("content-type", ""), r.content


GOOGLE_SIMPLE_MAX = 5 * 1024 * 1024  # Google's multipart upload limit; larger files go resumable


async def google_upload(method: str, url: str, params: list | dict | None, metadata: dict | None, path: Path,
                        mime: str) -> tuple[int, str, bytes]:
    """Uploads a local file to a Google upload endpoint (Drive: /upload/drive/v3/files[/<id>]) with its metadata:
    multipart up to 5 MB, resumable above (sent in 8 MB pieces, never the whole file in memory twice)."""
    import httpx
    import json as _json
    import uuid
    if not GOOGLE_API_HOST.match(url or ""):
        raise ConnError("google_bad_url", "Only https://<api>.googleapis.com/... addresses.")
    size = path.stat().st_size
    q = [(k, v) for k, v in (params.items() if isinstance(params, dict) else params or []) if k != "uploadType"]
    meta = _json.dumps(metadata or {}, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {await google_token()}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, write=600), follow_redirects=True) as c:
        if size <= GOOGLE_SIMPLE_MAX:
            b = f"aiiq{uuid.uuid4().hex}"
            data = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta
                    + f"\r\n--{b}\r\nContent-Type: {mime}\r\n\r\n".encode() + path.read_bytes()
                    + f"\r\n--{b}--\r\n".encode())
            r = await c.request(method, url, params=q + [("uploadType", "multipart")], content=data,
                                headers={**headers, "Content-Type": f"multipart/related; boundary={b}"})
            return r.status_code, r.headers.get("content-type", ""), r.content
        r = await c.request(method, url, params=q + [("uploadType", "resumable")], content=meta,
                            headers={**headers, "Content-Type": "application/json; charset=UTF-8",
                                     "X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)})
        if r.status_code >= 400 or not r.headers.get("location"):
            return r.status_code, r.headers.get("content-type", ""), r.content
        loc, sent, chunk = r.headers["location"], 0, 8 * 1024 * 1024
        with path.open("rb") as f:
            while True:
                piece = f.read(chunk)
                end = sent + len(piece) - 1
                r = await c.put(loc, content=piece, headers={
                    "Content-Range": f"bytes {sent}-{end}/{size}" if piece else f"bytes */{size}"})
                sent += len(piece)
                if r.status_code != 308:
                    return r.status_code, r.headers.get("content-type", ""), r.content


async def google_disconnect(forget_client: bool = False) -> None:
    d = _load("google")
    _store("google", {k: d[k] for k in ("client_id", "client_secret") if d.get(k)} if not forget_client else None)
    await _drop_mcp(_managed("google"))


# ---------------------------------------------------------------------------------------------------------- Microsoft
MS_PACKAGE = "@softeria/ms-365-mcp-server"
_MS: dict = {"state": "idle"}


def microsoft_status() -> dict:
    d = _load("microsoft")
    return {"connected": bool(d.get("connected")), "org": bool(d.get("org")), "node": bool(shutil.which("npx")),
            "login": {k: _MS.get(k) for k in ("state", "url", "code", "error")}}


def _ms_args(org: bool) -> list[str]:
    return ["-y", MS_PACKAGE, *(["--org-mode"] if org else [])]


async def microsoft_connect(org: bool = False) -> dict:
    """Starts Microsoft's device-code sign-in; returns as soon as the code is known (the sign-in finishes in the
    background when the user enters it on Microsoft's page)."""
    import os
    npx = shutil.which("npx")
    if not npx:
        raise ConnError("node_missing", "Node.js is needed for the Microsoft 365 connection: winget install "
                                        "OpenJS.NodeJS.LTS (macOS: brew install node).")
    if _MS.get("state") == "waiting" and _MS.get("proc") and _MS["proc"].returncode is None:
        return microsoft_status()
    p = await asyncio.create_subprocess_exec(npx, *_ms_args(org), "--login", env={**os.environ, "NO_COLOR": "1"},
                                             stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.STDOUT)
    _MS.clear()
    _MS.update({"state": "starting", "proc": p, "org": org, "out": ""})
    got = asyncio.Event()

    async def reader():
        assert p.stdout
        while line := await p.stdout.readline():
            _MS["out"] = (_MS["out"] + line.decode("utf-8", "replace"))[-4000:]
            url = re.search(r"https://\S*(?:devicelogin|/device)\S*", _MS["out"], re.I)
            code = re.search(r"\b(?:code|kod)\b\D{0,20}([A-Z0-9]{8,9})\b", _MS["out"], re.I)
            if url and code and not got.is_set():
                _MS.update({"state": "waiting", "url": url.group(0).rstrip(".,)"), "code": code.group(1)})
                got.set()
        rc = await p.wait()
        if rc == 0 and not re.search(r"\b(error|failed|expired)\b", _MS["out"][-600:], re.I):
            _store("microsoft", {"connected": True, "org": org, "at": time.time()})
            await _set_mcp("microsoft-365", {"name": "Microsoft 365", "transport": "stdio", "command": "npx",
                                             "args": _ms_args(org), "managed": "microsoft"})
            _MS.update({"state": "done"})
        else:
            _MS.update({"state": "error", "error": _MS["out"][-400:].strip() or f"exit {rc}"})
        got.set()

    _MS["task"] = asyncio.create_task(reader())
    try:
        await asyncio.wait_for(got.wait(), 180)  # the first npx run downloads the package
    except asyncio.TimeoutError:
        _MS.update({"state": "error", "error": "No sign-in code within 3 minutes: " + _MS["out"][-300:]})
    return microsoft_status()


async def microsoft_disconnect() -> None:
    import os
    d = _load("microsoft")
    if npx := shutil.which("npx"):
        p = await asyncio.create_subprocess_exec(npx, *_ms_args(bool(d.get("org"))), "--logout", env=os.environ,
                                                 stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(p.wait(), 60)
        except asyncio.TimeoutError:
            p.kill()
    _store("microsoft", None)
    _MS.clear()
    _MS["state"] = "idle"
    await _drop_mcp(_managed("microsoft"))


def status() -> dict:
    return {"github": github_status(), "google": google_status(), "microsoft": microsoft_status()}
