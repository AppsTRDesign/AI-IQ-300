"""Browser agent tools (see browser.py): the model works in a real browser window like a person and checks every
step by reading the page again. Safety: card numbers are typed only on local development hosts (test
values); irreversible buttons on real sites ask the user first; sign-ins and CAPTCHAs are handed to the user."""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from .. import policy
from .browser import AGENT, BrowserError, _keys, host_of, is_local, is_named_test_host
from .registry import S, ToolResult, _network_gate, _path, _rel, clip, gate, tool

BROWSER_TOOLS = {"browser_navigate", "browser_snapshot", "browser_find", "browser_click", "browser_type", "browser_key",
                 "browser_form", "browser_scroll", "browser_wait", "browser_tabs", "browser_screenshot", "browser_inspect",
                 "browser_batch", "browser_handoff"}
TARGET = {"ref": S("Element ref from browser_snapshot/browser_find, e.g. e12"),
          "selector": S("Optional: CSS selector instead of a ref"),
          "text": S("Optional: visible text of the element instead of a ref")}
SNAP = {"snapshot": S("false: do not return the page after the action", enum=["true", "false"])}
AFTER_MAX = 6000  # characters of the page returned after an action


def _flag(v, default=False) -> bool:
    return default if v is None or v == "" else str(v).lower() in ("true", "1", "yes")


def _trusted(ctx, url: str) -> bool:
    """Where test sign-ins/test cards may be typed: local dev hosts, or a test host the user's request names."""
    return is_local(url) or is_named_test_host(url, ctx.goal)


def _own_site(ctx, url: str) -> bool:
    """Full access (Tam erişim) on a site the user's own request names ("sign me up on mysite.com"): the user asked
    the agent to act there, so sign-up/sign-in passwords and form buttons go through without approval cards.
    Card and bank details stay out (real payments are never typed by the agent)."""
    if getattr(ctx, "mode", "") != "full":
        return False
    host = host_of(url)
    if not host:
        return False
    goal = (getattr(ctx, "goal", "") or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    return bare in goal


def _may_sign_in(ctx, url: str) -> bool:
    return _trusted(ctx, url) or _own_site(ctx, url)


# A CAPTCHA is gone or answered: no widget/challenge left, or its response token is filled in.
CAPTCHA_STATE_JS = """() => {
  const frames = [...document.querySelectorAll('iframe')].map((f) => f.src || '').join(' ');
  const challenge = !!document.querySelector('#challenge-form, #cf-challenge-running, #challenge-stage');
  const widget = /recaptcha|hcaptcha|challenges\\.cloudflare\\.com|turnstile|arkoselabs|funcaptcha/i.test(frames)
    || !!document.querySelector('.cf-turnstile, .g-recaptcha, .h-captcha');
  const token = [...document.querySelectorAll('[name=g-recaptcha-response],[name=h-captcha-response],[name=cf-turnstile-response]')]
    .some((e) => (e.value || '').length > 20);
  return {present: challenge || widget, solved: !challenge && (!widget || token)};
}"""


async def _captcha_state() -> dict:
    try:
        return await AGENT.page.evaluate(CAPTCHA_STATE_JS)
    except Exception:  # navigating (the challenge page is replaced by the site): read again next time
        return {"present": True, "solved": False}


async def _ask(ctx, op: dict, reason: str) -> None:
    if msg := await gate(ctx, op, policy.Decision("ask", "browser", [reason])):
        raise BrowserError(msg)


async def _guard_click(ctx, info: dict, dialog: str) -> None:
    """
    url = AGENT.page.url
    name = info.get("name") or ""
    risky = bool(RISKY.search(name)) or dialog == "accept" or \
        (info.get("submit") and (info.get("formPassword") or info.get("formCard")))
    if not risky:
        return
    if (_trusted(ctx, url) and ctx.mode != "ask") or (_own_site(ctx, url) and not info.get("formCard")):
        return  # testing the user's own app on a dev host / full access on the site the user named
    await _ask(ctx, {"tool": "browser_click", "url": url, "element": name[:100]},
               f"'{name[:60]}' on {host_of(url) or url} may not be undoable (send, delete, buy, publish...)")
    """
    pass    


def _guard_type(ctx, info: dict, args: dict, key: str = "text") -> None:
    """
    url = AGENT.page.url
    if info.get("password") or info.get("card"):
        args[key] = "***"  # never shown in the trace
        allowed = _may_sign_in(ctx, url) if info.get("password") and not info.get("card") else _trusted(ctx, url)
        if not allowed:
            what = "Passwords" if info.get("password") else "Card and bank details"
            where = ("" if info.get("card") else " (in Full access mode they are typed on a site the user's request "
                     "names, e.g. 'sign me up on mysite.com')")
            raise BrowserError(f"{what} on real sites are never typed by the agent{where}. Call browser_handoff so the "
                               "user signs in / enters them in the browser window (the profile keeps the sign-in).")
    """
    pass    


async def _navigate(ctx, args):
    url = (args.get("url") or "").strip()
    if not url:
        raise BrowserError("Give url (or back, forward, reload).")
    page = AGENT.page if AGENT.pages else None
    if url in ("back", "forward", "reload"):
        if not page:
            raise BrowserError("No page is open yet.")
        await {"back": page.go_back, "forward": page.go_forward, "reload": page.reload}[url](wait_until="domcontentloaded")
        await AGENT.settle(page)
        return f"{url}: {page.url}", {"url": page.url}
    from .registry import local_page_instead
    url, local_note = local_page_instead(ctx, url if re.match(r"https?://", url, re.I) else (
        "http://" + url if re.match(r"(localhost|127\.|\[::1\])", url) else url))
    args["_local_note"] = local_note
    if url.lower().startswith("file:") or not re.match(r"[a-z][a-z0-9+.-]*:", url, re.I):
        if re.match(r"(localhost|127\.|\[::1\])", url):
            url = "http://" + url
        else:
            if url.lower().startswith("file:"):  # file:///C:/My%20Folder/x.html -> C:\My Folder\x.html
                from urllib.parse import urlparse
                from urllib.request import url2pathname
                local = _path(ctx, url2pathname(urlparse(url).path))
            else:
                local = _path(ctx, url)
            if not local.is_file():
                raise BrowserError(f"Not a URL or a file in the working folder: {url}")
            url = local.resolve().as_uri()
    elif url.lower() == "about:blank":  # an empty tab (models use it to reset a stuck page)
        if page:
            await page.goto("about:blank")
        return "opened an empty tab", {"url": "about:blank"}
    elif not url.lower().startswith(("http://", "https://")):
        raise BrowserError("Only http(s) addresses and pages of the working folder can be opened.")
    if AGENT.crashed_host(url):
        raise BrowserError(f"{url} crashed the browser twice in this session; do not open it here again. Read it "
                           "with fetch_url (text) or web_screenshot (image).")
    if not is_local(url):
        if msg := await _network_gate(ctx, {"tool": "browser_navigate", "url": url}):
            raise BrowserError(msg)
    if _flag(args.get("new_tab")) or not page:
        page = await AGENT.context.new_page()
        AGENT._on_page(page)
    resp = await AGENT.goto(page, url)
    status = f" (HTTP {resp.status})" if resp is not None and resp.status >= 400 else ""
    if is_local(url) and not status:
        await _rendered(page)
    await AGENT.dismiss_popups(page)  # cookie banner (rejected) and pop-ups covering the page
    note = AGENT.popup_note()
    return args.pop("_local_note", "") + f"opened {page.url}{status}" + (f"\n{note}" if note else ""), \
        {"url": page.url, "status": resp.status if resp is not None else None}


async def _rendered(page, limit: float = 20.0) -> None:
    """A local single-page app (Expo web, Vite, React) is an empty page until its bundle ran: the model got
    '(no readable elements)' and then waited minutes with browser_wait. Up to `limit` s for text to appear, ending at
    once when the page reports an error (the page check after the step lists it)."""
    tid = AGENT.tab_id(page)
    errs0, bad0 = len(AGENT.console.get(tid, [])), len(AGENT.bad.get(tid, []))
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        try:
            if await page.evaluate("(document.body && document.body.innerText || '').trim().length"):
                return
        except Exception:  # noqa: BLE001 - navigating
            pass
        if any(m["type"] == "error" for m in list(AGENT.console.get(tid, []))[errs0:]) or \
                len(AGENT.bad.get(tid, [])) > bad0:
            return
        await asyncio.sleep(0.5)


async def _snapshot(ctx, args):
    text = await AGENT.snapshot(_flag(args.get("interactive")), str(args.get("ref") or ""),
                                int(args.get("max_chars") or 12000))
    return text, {"url": AGENT.page.url}


async def _find(ctx, args):
    q = (args.get("query") or "").strip()
    if not q:
        raise BrowserError("Give query: the text, label or role to look for.")
    hits = await AGENT.find(q)
    return (f"{len(hits)} match(es) for '{q}':\n" + "\n".join(hits)) if hits else \
        f"Nothing matches '{q}' on {AGENT.page.url}. Take browser_snapshot to see the page.", {}


async def _click(ctx, args):
    page = AGENT.page
    before = len(AGENT.pages)
    dialog = str(args.get("dialog") or "")
    if args.get("x") not in (None, "") and args.get("y") not in (None, ""):
        await page.mouse.click(float(args["x"]), float(args["y"]))
        what = f"({args['x']},{args['y']})"
    else:
        loc, what, info = await AGENT.target(str(args.get("ref") or ""), str(args.get("selector") or ""),
                                             str(args.get("text") or ""))
        AGENT.acted = True
        if info.get("tag") == "option":
            # "click 2 Kişi": an option of a select box cannot be clicked like a button (it is not on screen until the
            # list opens) - it is selected in its select, as a person choosing it would.
            label = await loc.evaluate("(o) => o.textContent.trim()")
            sel = loc.locator("xpath=ancestor::select[1]")
            await sel.select_option(label=label, timeout=5000)
            await AGENT.settle(AGENT.page)
            return f"selected {label!r} in its list -> {AGENT.page.url}", {"url": AGENT.page.url}
        hover = _flag(args.get("hover"))
        if not hover:
            await _guard_click(ctx, info, dialog)
        # confirm() dialogs: on the user's own local site (the app under test: "Delete? OK") they are accepted unless
        # dialog=dismiss; elsewhere only with dialog=accept. Dismissed by default, a delete button never deleted and
        # the model waited 15 s for a row that stayed.
        local_site = is_local(AGENT.page.url)
        AGENT.dialog_choice = "accept" if dialog == "accept" or (local_site and dialog != "dismiss") else "dismiss"
        mods = [k for k in _keys(str(args.get("modifiers") or "").replace("+", " ")) if k]
        try:
            if hover:
                await loc.hover(timeout=5000)
            else:
                await loc.click(timeout=5000, button=str(args.get("button") or "left"),
                                click_count=2 if _flag(args.get("double")) else 1, modifiers=mods or None)
        except Exception as e:
            err = str(e).splitlines()[0][:220]
            if hover or "disabled" in str(e) or not await loc.count():
                raise BrowserError(f"click on {what} failed: {err}. Take browser_snapshot: the element may be "
                                   "disabled or gone.") from e
            # Covered by another layer (a sticky header, an animation still running): a script click still
            # reaches the element; the trace says so, so a real overlap bug is not hidden.
            try:
                await loc.evaluate("(e) => { e.scrollIntoView({block: 'center'}); e.click(); }")
                info["note"] = (info.get("note") or "") + " (a normal click was blocked - something covers it or it " \
                                                          "is still moving - so it was clicked by script)"
            except Exception:
                raise BrowserError(f"click on {what} failed: {err}. Take browser_snapshot: the element may be "
                                   "covered or disabled.") from e
        what = f"{what} \"{(info.get('name') or '')[:60]}\"{info.get('note') or ''}"
    await asyncio.sleep(0.2)
    await AGENT.settle(AGENT.page)
    AGENT.dialog_choice = "dismiss"
    note = f" (opened new tab {AGENT.tab_id()})" if len(AGENT.pages) > before else ""
    return f"{'hovered' if _flag(args.get('hover')) else 'clicked'} {what}{note} -> {AGENT.page.url}", {"url": AGENT.page.url}


FIELD_NEAR_JS = r"""(e) => {
  document.querySelectorAll('[data-aiiq-pick]').forEach((x) => x.removeAttribute('data-aiiq-pick'));
  const F = 'input:not([type=hidden]),textarea,select,[contenteditable=true]';
  let f = e.control || e.querySelector(F);
  for (let s = e.nextElementSibling, i = 0; !f && s && i < 3; s = s.nextElementSibling, i++)
    f = s.matches(F) ? s : s.querySelector(F);
  for (let p = e.parentElement, i = 0; !f && p && i < 2; p = p.parentElement, i++) {
    const all = [...p.querySelectorAll(F)];
    if (all.length === 1) f = all[0];
  }
  if (!f) return false;
  f.setAttribute('data-aiiq-pick', '1');
  return true;
}"""


async def _type(ctx, args):
    loc, what, info = await AGENT.target(str(args.get("ref") or ""), str(args.get("selector") or ""),
                                         str(args.get("target") or args.get("field") or args.get("label") or ""))
    AGENT.acted = True
    if not info.get("editable") and info.get("tag") not in ("input", "textarea", "select"):
        # The text matched a label / caption, not the field (a <label> without for=): the field next to it
        found = await loc.evaluate(FIELD_NEAR_JS)
        if found:
            loc = AGENT.page.locator('[data-aiiq-pick="1"]').first
            info = await AGENT.element(loc, what)
    text = str(args.get("text") if args.get("text") is not None else args.get("value") or "")
    _guard_type(ctx, info, args)
    try:
        if _flag(args.get("slowly")):
            if _flag(args.get("clear"), True):
                await loc.fill("", timeout=8000)
            await loc.press_sequentially(text, delay=35, timeout=30000)
        elif _flag(args.get("clear"), True):
            await loc.fill(text, timeout=8000)
        else:
            await loc.press_sequentially(text, timeout=30000)
    except Exception as e:
        raise BrowserError(f"typing into {what} failed: {str(e).splitlines()[0][:220]}") from e
    shown = "***" if info.get("password") or info.get("card") else f'"{text[:60]}"'
    msg = f"typed {shown} into {what}{info.get('note') or ''}"
    if _flag(args.get("submit")):
        if info.get("formPassword") or info.get("formCard"):
            await _guard_click(ctx, {**info, "submit": True, "name": info.get("name") or "submit"}, "")
        await loc.press("Enter")
        await asyncio.sleep(0.2)
        await AGENT.settle(AGENT.page)
        msg += f" and pressed Enter -> {AGENT.page.url}"
    return msg, {}


async def _key(ctx, args):
    keys = _keys(str(args.get("keys") or args.get("text") or ""))
    if not keys:
        raise BrowserError("Give keys, e.g. Enter, Escape, ctrl+a, Tab.")
    page = AGENT.page
    if "Enter" in keys and not _may_sign_in(ctx, page.url):
        focus = await page.evaluate("() => { const e = document.activeElement; const f = e && (e.form || e.closest('form'));"
                                    " return !!(f && f.querySelector('input[type=password],[autocomplete^=\"cc-\"]')); }")
        if focus:
            await _guard_click(ctx, {"name": "submit (Enter)", "submit": True, "formPassword": True}, "")
    AGENT.acted = True
    for _ in range(max(1, min(int(args.get("repeat") or 1), 50))):
        for k in keys:
            await page.keyboard.press(k)
    await asyncio.sleep(0.15)
    await AGENT.settle(AGENT.page, 1000)
    return f"pressed {' '.join(keys)}" + (f" x{args.get('repeat')}" if str(args.get("repeat") or "1") != "1" else ""), {}


async def _form(ctx, args):
    fields = next((args.get(k) for k in ("fields", "values", "inputs", "data", "form") if args.get(k)), None)
    if isinstance(fields, str):
        try:
            fields = json.loads(fields or "[]")
        except json.JSONDecodeError as e:
            raise BrowserError("fields must be a JSON list: [{\"ref\": \"e3\", \"value\": \"...\"}]") from e
    if isinstance(fields, dict):  # {"e9": "Ay", "E-posta": "a@b.c"}: ref or label -> value
        fields = [{("ref" if re.fullmatch(r"\[?e?\d+\]?", str(k)) else "label"): k, "value": v} for k, v in fields.items()]
    if not isinstance(fields, list) or not fields:
        raise BrowserError("Give fields: [{\"ref\": \"e3\", \"value\": \"Ali\"}, {\"ref\": \"e5\", \"value\": true}].")
    done = []
    for f in fields[:40]:
        if not isinstance(f, dict):
            continue
        loc, what, info = await AGENT.target(str(f.get("ref") or ""), str(f.get("selector") or ""),
                                             str(f.get("text") or f.get("label") or ""))
        AGENT.acted = True
        if not info.get("editable") and info.get("tag") not in ("input", "textarea", "select"):
            if await loc.evaluate(FIELD_NEAR_JS):  # a label matched: the field next to it
                loc = AGENT.page.locator('[data-aiiq-pick="1"]').first
                info = await AGENT.element(loc, what)
        value = f.get("value")
        try:
            if info["tag"] == "select":
                # the option by its text or value, exact first, then ignoring case / a partial match; a value that
                # matches nothing is answered at once with the real options (it used to wait 2 x 5 s)
                opts = await loc.evaluate("(s) => [...s.options].map((o) => [o.value, o.text.trim()])")
                want = str(value).strip().casefold()
                pick = (next((v for v, t in opts if want in (v.casefold(), t.casefold())), None)
                        or next((v for v, t in opts if want and (want in t.casefold() or t.casefold() in want) and t), None))
                if pick is None:
                    raise BrowserError(f"{what}: no option {value!r}. Options: "
                                       + ", ".join(f"{t!r}" for _, t in opts[:30]))
                await loc.select_option(value=pick, timeout=5000)
                done.append(f"{what}={value}")
            elif info["type"] in ("checkbox", "radio"):
                await loc.set_checked(_flag(value, True), timeout=5000)
                done.append(f"{what}={'on' if _flag(value, True) else 'off'}")
            elif info["type"] == "file":
                files = [value] if isinstance(value, str) else list(value or [])
                paths = [_path(ctx, p) for p in files]
                missing = [str(p) for p in paths if not p.is_file()]
                if missing:
                    raise BrowserError(f"file not found in the working folder: {', '.join(missing)}")
                await loc.set_input_files([str(p) for p in paths], timeout=8000)
                done.append(f"{what}=<{', '.join(p.name for p in paths)}>")
            else:
                _guard_type(ctx, info, f, "value")
                await loc.fill(str(value if value is not None else ""), timeout=8000)
                done.append(f"{what}={'***' if info.get('password') or info.get('card') else str(value)[:40]}")
        except BrowserError:
            raise
        except Exception as e:
            raise BrowserError(f"{what}: {str(e).splitlines()[0][:200]} (filled so far: {', '.join(done) or 'none'})") from e
    args["fields"] = fields  # masked values stay in the trace
    return "filled " + ", ".join(done), {}


async def _scroll(ctx, args):
    page = AGENT.page
    if args.get("ref") or args.get("selector") or args.get("text"):
        loc, what = AGENT.locator(str(args.get("ref") or ""), str(args.get("selector") or ""), str(args.get("text") or ""))
        await loc.scroll_into_view_if_needed(timeout=8000)
        return f"scrolled {what} into view", {}
    d = str(args.get("direction") or "down")
    n = max(1, min(int(args.get("amount") or 3), 20)) * 300
    dx, dy = {"down": (0, n), "up": (0, -n), "right": (n, 0), "left": (-n, 0)}.get(d, (0, n))
    await page.mouse.wheel(dx, dy)
    await asyncio.sleep(0.4)
    pos = await page.evaluate("() => [Math.round(scrollY), document.documentElement.scrollHeight - innerHeight]")
    return f"scrolled {d}: now at {pos[0]}px of {max(pos[1], 0)}px", {}


WAIT_MAX = 60  # seconds: a page that shows nothing after a minute is broken, not slow


async def _wait(ctx, args):
    """Waits in one-second slices and watches the page meanwhile: a page that stays blank while its console or its
    requests fail (an Expo / SPA bundle answering 500) ends the wait at once with those errors. Waiting the full
    120-150 s on a blank page was most of a live test's browser time."""
    page = AGENT.page
    timeout = max(1.0, min(float(args.get("timeout") or 15), WAIT_MAX))
    tid = AGENT.tab_id()
    errs0, bad0 = len(AGENT.console.get(tid, [])), len(AGENT.bad.get(tid, []))
    t0 = time.monotonic()
    blank_since = None

    async def met() -> str:
        try:
            if args.get("text"):
                await page.get_by_text(str(args["text"])).first.wait_for(state="visible", timeout=1000)
                return f"'{args['text']}' is on the page"
            if args.get("gone"):
                await page.get_by_text(str(args["gone"])).first.wait_for(state="hidden", timeout=1000)
                return f"'{args['gone']}' is gone"
            if args.get("url"):
                await page.wait_for_url(re.compile(re.escape(str(args["url"]))), timeout=1000)
                return f"address now {page.url}"
        except Exception:  # noqa: BLE001 - not yet
            return ""
        return ""

    if args.get("text") or args.get("gone") or args.get("url"):
        while True:
            if done := await met():
                return done, {}
            now = time.monotonic()
            new_err = [m for m in list(AGENT.console.get(tid, []))[errs0:] if m["type"] == "error"]
            new_bad = list(AGENT.bad.get(tid, []))[bad0:]
            try:
                blank = not (await page.evaluate("(document.body && document.body.innerText || '').trim().length"))
            except Exception:  # noqa: BLE001 - navigating
                blank = False
            blank_since = (blank_since or now) if blank else None
            if (new_err or new_bad) and blank_since and now - blank_since >= 5:
                raise BrowserError(
                    f"stopped waiting after {now - t0:.0f}s: the page {page.url} is still blank and it has errors - fix "
                    "them first (waiting longer will not help):\n"
                    + "\n".join(f"[console] {m['text'][:300]}" + (f" <- {m['url'][:160]}" if m.get('url') else "")
                                for m in new_err[-6:])
                    + ("\nFailed requests: " + "; ".join(new_bad[-6:]) if new_bad else ""))
            if now - t0 >= timeout:
                state = "blank" if blank else "showing other content"
                raise BrowserError(f"waited {timeout:.0f}s: not found (the page is {state}; browser_snapshot shows "
                                   "what is there, browser_inspect console / network shows errors)")
    ms = max(0, min(int(float(args.get("ms") or 1000)), 15000))
    await asyncio.sleep(ms / 1000)
    return f"waited {ms} ms", {}


async def _tabs(ctx, args):
    action = str(args.get("action") or "list")
    if action == "new":
        page = await AGENT.context.new_page()
        AGENT._on_page(page)
        if args.get("url"):
            await _navigate(ctx, {"url": args["url"]})
    elif action in ("select", "close"):
        tid = str(args.get("tab") or "")
        page = next((p for p, t in AGENT.ids.items() if t == tid and p in AGENT.pages), None)
        if not page:
            raise BrowserError(f"No tab {tid}. Open tabs: " + ", ".join(AGENT.ids[p] for p in AGENT.pages))
        if action == "select":
            AGENT.active = page
            await page.bring_to_front()
        else:
            await page.close()
    elif action == "close_browser":
        await AGENT.close()
        return "browser closed (sign-ins stay in the profile)", {}
    lines = [f"{'*' if p is AGENT.active else ' '} {AGENT.ids[p]} {p.url}" for p in AGENT.pages]
    return "tabs (* = active):\n" + "\n".join(lines), {}


async def _screenshot(ctx, args):
    from PIL import Image

    from . import shot
    page = AGENT.page
    if page.url in ("", "about:blank"):
        # Nothing is open yet: a blank picture (and a vision model describing white) helps nobody.
        raise BrowserError("No page is open in the browser. Open it first with browser_navigate url=..., or use "
                           "web_screenshot url=... for a page that needs no sign-in.")
    rel = (args.get("path") or "").strip() or shot.default_name(page.url, "png").replace("screenshots/", "screenshots/browser-", 1)
    if Path(rel).suffix.lower() not in (".png", ".jpg", ".jpeg"):
        rel += ".png"
    target = _path(ctx, rel)
    if msg := await gate(ctx, {"tool": "browser_screenshot", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        raise BrowserError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.get("ref") or args.get("selector"):
        loc, _ = AGENT.locator(str(args.get("ref") or ""), str(args.get("selector") or ""))
        await loc.screenshot(path=str(target), timeout=10000)
    else:
        await page.screenshot(path=str(target), full_page=_flag(args.get("full_page")), timeout=20000)
    size = list(Image.open(target).size)
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    from .visual import describe_for
    seen = await describe_for(ctx.model, target, ctx.goal)
    return (f"saved {out} ({size[0]}x{size[1]}px) of {page.url}. The image is shown to the user in the chat."
            + (f"\nThe vision model {seen[0]} looked at it:\n{seen[1]}" if seen else ""),
            {"path": out, "screenshot": out, "url": page.url, "title": await page.title(), "size": size})


async def _inspect(ctx, args):
    what = str(args.get("what") or "console")
    tid = AGENT.tab_id()
    limit = max(1, min(int(args.get("limit") or 40), 200))
    pattern = str(args.get("pattern") or "").lower()
    if what == "console":
        items = [m for m in AGENT.console.get(tid, []) if (not _flag(args.get("only_errors")) or m["type"] in ("error", "warning"))
                 and (not pattern or pattern in m["text"].lower())][-limit:]
        AGENT.seen_console[tid] = len(AGENT.console.get(tid, []))
        # "Failed to load resource: 500" says nothing about WHICH request: its URL goes with it (the model guessed for
        # minutes in a live test), and the failed requests themselves are listed under it.
        lines = [f"[{m['type']}] {m['text'][:400]}" + (f"  <- {m['url'][:200]}" if m.get("url") and m["url"] not in m["text"] else "")
                 for m in items]
        failed = [b for b in AGENT.bad.get(tid, [])][-10:]
        if failed and any("Failed to load resource" in m["text"] for m in items):
            lines.append("Failed requests (status type url): " + "; ".join(failed))
        return (f"{len(items)} console message(s):\n" + "\n".join(lines) if items else "no console messages"), {}
    if what == "network":
        if rid := str(args.get("request_id") or ""):
            resp = AGENT.responses.get(rid)
            if not resp:
                raise BrowserError(f"no stored response {rid} (only xhr/fetch/document bodies are kept)")
            try:
                body = await resp.text()
            except Exception as e:
                raise BrowserError(f"body not available: {str(e)[:150]}") from e
            return f"{resp.status} {resp.url}\n{clip(body, 6000)}", {}
        failed_only = _flag(args.get("failed_only"))
        items = [r for r in AGENT.network.get(tid, []) if (not pattern or pattern in r["url"].lower())
                 and (not failed_only or r["failure"] or (r["status"] or 0) >= 400)
                 and (r["type"] in ("document", "xhr", "fetch", "script", "stylesheet") or r["failure"] or (r["status"] or 0) >= 400)][-limit:]
        return (f"{len(items)} request(s):\n" + "\n".join(
            f"{r['id']} {r['method']} {r['status'] or r['failure']} {r['type']} {r['url'][:200]}" for r in items)
            if items else "no matching requests"), {}
    if what == "storage":  # names only: cookie values never reach the model
        cookies = await AGENT.context.cookies(AGENT.page.url)
        host = host_of(AGENT.page.url)
        return (f"{len(cookies)} cookie(s) for {host}: " + ", ".join(sorted({c['name'] for c in cookies}))[:1500]
                if cookies else f"no cookies for {host} (not signed in here)"), {}
    if what == "js":
        code = str(args.get("code") or "").strip()
        if not code:
            raise BrowserError("Give code: a JavaScript expression, e.g. document.querySelectorAll('tr').length")
        if ctx.mode == "ask":
            await _ask(ctx, {"tool": "browser_inspect", "code": code[:500]}, "runs JavaScript in the page")
        try:
            val = await AGENT.page.evaluate(code if re.match(r"\s*(\(|async\b|function\b)", code) else f"() => ({code})")
        except Exception as e:
            raise BrowserError(f"JavaScript error: {str(e).splitlines()[0][:300]}") from e
        return clip(json.dumps(val, ensure_ascii=False, default=str), 6000), {}
    raise BrowserError("what is console, network, storage or js")


async def _handoff(ctx, args):
    page = AGENT.page
    reason = str(args.get("reason") or "sign in").strip()[:300]
    if AGENT.headless:
        # The user needs a real window: reopen the same page in a visible browser (same profile, so sign-ins stay).
        url = page.url
        AGENT.force_visible = True
        await AGENT.close()
        await AGENT.ensure()
        if AGENT.headless:
            raise BrowserError("No visible window can be opened here (no display): the user cannot act in the "
                               "browser. Ask the user in your answer instead.")
        if url and url != "about:blank":
            await _navigate(ctx, {"url": url})
        page = AGENT.page
    try:
        await page.bring_to_front()
    except Exception:
        pass
    captcha = (await _captcha_state()).get("present")
    approval = asyncio.ensure_future(gate(ctx, {"tool": "browser_handoff", "url": page.url, "reason": reason},
                                          policy.Decision("ask", "browser_handoff", [reason])))
    try:
        if captcha:
            # The user solves it in the window; the agent sees it is done and continues by itself (no "done" click).
            solved_in_row = 0
            while not approval.done():
                await asyncio.sleep(1.5)
                solved_in_row = solved_in_row + 1 if (await _captcha_state()).get("solved") else 0
                if solved_in_row >= 2:
                    approval.cancel()
                    await AGENT.settle(AGENT.page)
                    return ("The CAPTCHA/bot check was completed by the user in the browser window. Continue from "
                            "the page as it is now (re-read it with browser_snapshot)."), {}
        denied = await approval
    except asyncio.CancelledError:
        approval.cancel()
        raise
    if denied:
        raise BrowserError("The user did not finish it (or declined). Do not retry: tell the user what is needed.")
    await AGENT.settle(AGENT.page)
    return f"The user finished: {reason}. Continue from the page as it is now.", {}


OPS = {"navigate": _navigate, "snapshot": _snapshot, "find": _find, "click": _click, "type": _type, "key": _key,
       "form": _form, "scroll": _scroll, "wait": _wait, "tabs": _tabs, "screenshot": _screenshot, "inspect": _inspect,
       "handoff": _handoff}
NO_PAGE_AFTER = {"snapshot", "find", "tabs", "screenshot", "inspect", "scroll", "wait"}


async def act(ctx, action: str, args: dict) -> ToolResult:
    async with AGENT.lock:
        try:
            await AGENT.ensure()
            AGENT.download_dir = ctx.root / "downloads"
            text, data = await OPS[action](ctx, _target_keys(args, action))
            if action not in NO_PAGE_AFTER and _flag(args.get("snapshot"), True) and AGENT.pages:
                text += "\n\n" + await AGENT.snapshot(max_chars=AFTER_MAX)
            elif action in ("scroll", "wait") and AGENT.pages and (news := AGENT.news()):
                text += "\n" + news
            AGENT.last = time.monotonic()
            return ToolResult(True, text, data)
        except BrowserError as e:
            return ToolResult(False, str(e))
        except Exception as e:  # a closed window, a crashed page: report, the next call starts again
            if "crash" in str(e).lower():  # renderer crash: a fresh tab, and no endless retries of the same page
                url = str(args.get("url") or "") or (AGENT.active.url if AGENT.active else "")
                return ToolResult(False, await AGENT.recover_crash(url))
            if "closed" in str(e).lower():
                await AGENT.close()
                return ToolResult(False, "The browser window was closed; call the tool again to reopen it.")
            return ToolResult(False, f"{type(e).__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}")


def label(name: str, args: dict, body: str) -> str:
    """The trace line of a browser step: what was done to which element."""
    a = name.removeprefix("browser_")
    target = args.get("ref") or args.get("selector") or args.get("text") or ""
    if a == "navigate":
        return str(args.get("url") or body)[:140]
    if a == "type":
        return f"{target} ← {str(args.get('text', ''))[:50]}"
    if a == "key":
        return str(args.get("keys") or body)
    if a in ("find", "inspect"):
        return str(args.get("query") or args.get("what") or body)[:120]
    if a == "batch":
        try:
            steps = json.loads(args.get("actions") or body or "[]")
            return " → ".join(str(s.get("action", "?")) for s in steps if isinstance(s, dict))[:140]
        except (json.JSONDecodeError, AttributeError):
            return "batch"
    if a == "handoff":
        return str(args.get("reason") or body)[:120]
    return str(target or args.get("action") or args.get("direction") or a)[:120]


# ---------- tool definitions ----------
@tool("browser_navigate", '<tool name="browser_navigate" url="http://localhost:5173"></tool>',
      "Open a page in the real browser window (it keeps the user's sign-ins in its own profile). url can be "
      "http(s), a .html file of the working folder, or back / forward / reload. Returns the page as an accessibility "
      "tree with refs ([e12]) to use with the other browser_ tools.",
      {"url": S("Address, or back, forward, reload"), "new_tab": S("true: open in a new tab", enum=["true", "false"]),
       **SNAP}, main="url", required=("url",))
async def browser_navigate(ctx, args, body):
    if body and not args.get("url"):
        args["url"] = body.strip()
    return await act(ctx, "navigate", args)


@tool("browser_snapshot", '<tool name="browser_snapshot" interactive="false"></tool>',
      "Read the current page as an accessibility tree: roles, names, values and states with refs ([e12]). "
      "interactive=true lists only clickable/typable elements; ref=e5 reads one part of the page. Read the page "
      "again after every action that changes it.",
      {"interactive": S("true: only interactive elements", enum=["true", "false"]),
       "ref": S("Optional: only this element and its children"),
       "max_chars": {"type": "integer", "description": "Max characters (default 12000)"}})
async def browser_snapshot(ctx, args, body):
    return await act(ctx, "snapshot", args)


@tool("browser_find", '<tool name="browser_find">Sign in</tool>',
      "Find elements on the current page whose role, name or text contains the query (case-insensitive); returns "
      "their lines with refs. Faster than a whole snapshot on big pages.",
      {"query": S("Text, label or role to look for")}, main="query", required=("query",))
async def browser_find(ctx, args, body):
    args.setdefault("query", body.strip())
    return await act(ctx, "find", args)


@tool("browser_click", '<tool name="browser_click" ref="e12"></tool>',
      "Click an element (by ref, or selector/text) like a person; or x,y for a canvas. double=true double-clicks, "
      "button=right opens context menus, hover=true only moves the mouse over it (menus, tooltips). confirm()/prompt() "
      "dialogs are dismissed unless dialog=accept. Returns the page after the click.",
      {**TARGET, "x": S("Optional: x pixel"), "y": S("Optional: y pixel"),
       "double": S("true: double click", enum=["true", "false"]), "button": S("left or right", enum=["left", "right", "middle"]),
       "hover": S("true: hover only", enum=["true", "false"]), "modifiers": S("Optional: ctrl, shift, alt"),
       "dialog": S("accept: confirm the confirm() dialog this click opens", enum=["accept", "dismiss"]), **SNAP})
async def browser_click(ctx, args, body):
    if body and not any(args.get(k) for k in ("ref", "selector", "text", "x")):
        args["ref" if re.fullmatch(r"\[?(ref[=_])?e?\d+\]?", body.strip()) else "text"] = body.strip()
    return await act(ctx, "click", args)


@tool("browser_type", '<tool name="browser_type" ref="e7" submit="false">text to type</tool>',
      "Type text into a field (by ref or selector). Replaces the field's text unless clear=false; slowly=true types "
      "key by key (for fields that react to each key); submit=true presses Enter afterwards. Passwords: on local "
      "development sites, and in Full access mode on the site the user's request names; card numbers only on local "
      "development sites (test values); otherwise use browser_handoff.",
      {"ref": TARGET["ref"], "selector": TARGET["selector"],
       "label": S("Optional: the field's label or placeholder instead of a ref (a field that just appeared)"),
       "text": S("The text to type"),
       "clear": S("false: append instead of replacing", enum=["true", "false"]),
       "slowly": S("true: key by key", enum=["true", "false"]), "submit": S("true: press Enter after", enum=["true", "false"]),
       **SNAP}, main="text", required=("text",))
async def browser_type(ctx, args, body):
    if body and args.get("text") is None:
        args["text"] = body
    return await act(ctx, "type", args)


@tool("browser_key", '<tool name="browser_key">Enter</tool>',
      "Press keys in the browser: one or more space-separated keys or combos (Enter, Escape, Tab, ArrowDown, "
      "ctrl+a, shift+Tab...). repeat presses them several times.",
      {"keys": S("Keys, space separated"), "repeat": {"type": "integer", "description": "Times (default 1)"}, **SNAP},
      main="keys", required=("keys",))
async def browser_key(ctx, args, body):
    args.setdefault("keys", body.strip())
    return await act(ctx, "key", args)


@tool("browser_form", '<tool name="browser_form">[{"ref": "e3", "value": "Ali"}, {"ref": "e5", "value": true}]</tool>',
      "Fill several form fields at once: text fields, select boxes (option text), checkboxes/radios (true/false) and "
      "file inputs (path of a file in the working folder). Does not submit: click the submit button afterwards.",
      {"fields": {"type": "array", "items": {"type": "object"}, "description": "[{ref, value}] (or selector instead of ref)"},
       **SNAP}, main="fields", required=("fields",))
async def browser_form(ctx, args, body):
    if body and not args.get("fields"):
        args["fields"] = body
    return await act(ctx, "form", args)


@tool("browser_scroll", '<tool name="browser_scroll" direction="down" amount="3"></tool>',
      "Scroll the page (direction up/down/left/right, amount in steps of 300px) or bring an element (ref) into view.",
      {"direction": S("Direction", enum=["down", "up", "left", "right"]),
       "amount": {"type": "integer", "description": "Steps of 300px (default 3)"}, "ref": TARGET["ref"]})
async def browser_scroll(ctx, args, body):
    return await act(ctx, "scroll", args)


@tool("browser_wait", '<tool name="browser_wait" text="Saved"></tool>',
      "Wait until a text appears (text), disappears (gone) or the address contains url; else wait ms milliseconds. "
      "timeout in seconds (default 15, max 60); a page that stays blank with errors ends the wait at once.",
      {"text": S("Text to wait for"), "gone": S("Text to wait to disappear"), "url": S("Part of the address to wait for"),
       "ms": {"type": "integer", "description": "Plain wait in ms (max 15000)"},
       "timeout": {"type": "integer", "description": "Seconds"}})
async def browser_wait(ctx, args, body):
    return await act(ctx, "wait", args)


@tool("browser_tabs", '<tool name="browser_tabs" action="list"></tool>',
      "Browser tabs: list, new (optional url), select tab=t2, close tab=t2, or close_browser (sign-ins stay).",
      {"action": S("What to do", enum=["list", "new", "select", "close", "close_browser"]), "tab": S("Tab id, e.g. t2"),
       "url": S("For new: address to open")})
async def browser_tabs(ctx, args, body):
    return await act(ctx, "tabs", args)


@tool("browser_screenshot", '<tool name="browser_screenshot" full_page="false"></tool>',
      "Screenshot of the browser tab as it is now (after logins and clicks), shown in the chat; ref/selector "
      "captures one element. Saved under screenshots/ unless path is given.",
      {"full_page": S("true: whole page", enum=["true", "false"]), "ref": TARGET["ref"], "selector": TARGET["selector"],
       "path": S("Optional output .png path")})
async def browser_screenshot(ctx, args, body):
    return await act(ctx, "screenshot", args)


@tool("browser_inspect", '<tool name="browser_inspect" what="console" only_errors="true"></tool>',
      "Developer tools of the current tab: what=console (messages, only_errors), network (requests with status; "
      "failed_only, pattern; request_id=r12 returns that response body), storage (cookie names: is the user signed "
      "in?), js (code: a JavaScript expression evaluated in the page, for reading values).",
      {"what": S("console, network, storage or js", enum=["console", "network", "storage", "js"]),
       "only_errors": S("console: errors and warnings only", enum=["true", "false"]),
       "failed_only": S("network: failed or 4xx/5xx only", enum=["true", "false"]),
       "pattern": S("Filter text"), "request_id": S("network: return this response body"),
       "code": S("js: expression or function"), "limit": {"type": "integer", "description": "Max entries"}},
      required=("what",))
async def browser_inspect(ctx, args, body):
    if body and not args.get("code"):
        args["code"] = body
    return await act(ctx, "inspect", args)


@tool("browser_handoff", '<tool name="browser_handoff">Sign in to example.com in the browser window</tool>',
      "Hand the browser window to the user for what only they may do: signing in on a real site, a CAPTCHA or bot "
      "check, card or bank details, a 2FA code. Waits until the user says it is done, then continue.",
      {"reason": S("What the user should do")}, main="reason", required=("reason",))
async def browser_handoff(ctx, args, body):
    args.setdefault("reason", body.strip())
    return await act(ctx, "handoff", args)


BATCH_ALIASES = {"js": "inspect", "eval": "inspect", "evaluate": "inspect", "script": "inspect",
                 "fill": "type", "input": "type", "press": "key", "keypress": "key", "goto": "navigate",
                 "open": "navigate", "visit": "navigate", "hover": "click", "dblclick": "click", "tap": "click",
                 "select": "form", "check": "form", "uncheck": "form", "expect": "wait", "assert": "wait",
                 "wait_for": "wait", "sleep": "wait", "shot": "screenshot", "console": "inspect"}


def _batch_step(step) -> dict:
    """One batch step in the shape the action takes: other names models use (js, fill, press, select, hover...)."""
    step = dict(step) if isinstance(step, dict) else {"action": str(step or "")}
    action = str(step.get("action") or step.get("type_") or step.get("op") or "").strip().lower()
    real = BATCH_ALIASES.get(action, action)
    if real == "inspect" and action != "inspect":
        step.setdefault("what", "console" if action == "console" else "js")
        step.setdefault("code", step.get("script") or step.get("expression") or step.get("js") or step.get("text") or "")
    elif action in ("hover", "dblclick"):
        step["hover" if action == "hover" else "double"] = "true"
    elif real == "form" and action != "form" and not step.get("fields"):
        value = step.get("value", step.get("option", step.get("text")))
        if action in ("check", "uncheck"):
            value = action == "check"
        step["fields"] = [{k: step[k] for k in ("ref", "selector", "label") if step.get(k)} | {"value": value}]
    elif real == "wait" and action in ("sleep",) and step.get("ms") is None:
        step["ms"] = step.get("seconds", 1) * 1000 if isinstance(step.get("seconds"), (int, float)) else 1000
    elif real == "type" and step.get("text") is None and step.get("value") is not None:
        step["text"] = step["value"]
    step["action"] = real
    return _target_keys(step, real)


TARGET_KEYS = ("element", "target", "locator", "element_ref", "elementRef", "ref_id", "uid", "id", "on", "field")


def _target_keys(args: dict, action: str) -> dict:
    """The element under another key name (element="e3", target="#save", field="E-posta"): as ref / selector /
    text or label, so a step is not stopped with "say which element"."""
    if action not in ("click", "type", "scroll", "screenshot") or any(args.get(k) for k in ("ref", "selector", "label")):
        return args
    if action == "click" and (args.get("text") or (args.get("x") not in (None, "") and args.get("y") not in (None, ""))):
        return args
    value = next((str(args[k]) for k in TARGET_KEYS if args.get(k) not in (None, "")), "")
    if not value:
        return args
    if re.fullmatch(r"\[?(ref[=_])?e?\d+\]?", value.strip()):
        args["ref"] = value
    elif re.search(r"[#.\[\]=>:]", value):
        args["selector"] = value
    else:
        args["label" if action == "type" else "text"] = value
    return args


@tool("browser_batch", '<tool name="browser_batch">[{"action": "type", "ref": "e3", "text": "demo@test.local"}, '
      '{"action": "click", "ref": "e9"}, {"action": "wait", "text": "Dashboard"}]</tool>',
      "Several browser steps in one call, in order (navigate, click, type, key, form, select, scroll, wait, find, "
      "screenshot, snapshot, js); stops at the first failure and returns each step's result and the page. Plan "
      "first: read the page once (browser_snapshot interactive=true), then run a whole flow in one batch. Elements "
      "that only appear later (a form a click opens) have no ref yet: target them by their visible text, label or "
      "placeholder ({\"action\": \"type\", \"text\": \"Demo\", \"label\": \"Başlık\"}, {\"action\": \"click\", "
      "\"text\": \"Kaydet\"}), never by a guessed ref or CSS. Refs from before a page change are found again by name.",
      {"actions": {"type": "array", "items": {"type": "object"}, "description": "[{action, ...that tool's arguments}]"}},
      main="actions", required=("actions",))
async def browser_batch(ctx, args, body):
    raw = args.get("actions") or body
    try:
        steps = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return ToolResult(False, "actions must be a JSON list: [{\"action\": \"click\", \"ref\": \"e3\"}, ...]")
    if not isinstance(steps, list) or not steps:
        return ToolResult(False, "actions is empty.")
    lines, data = [], {}
    async with AGENT.lock:
        try:
            await AGENT.ensure()
            AGENT.download_dir = ctx.root / "downloads"
            for i, step in enumerate(steps[:25], 1):
                step = _batch_step(step)
                action = step.get("action") or ""
                if action not in OPS or action in ("batch", "handoff"):
                    raise BrowserError(f"step {i}: unknown action '{action}'. Actions: navigate, click, type, key, "
                                       "form, select, scroll, wait, find, snapshot, screenshot, js")
                text, d = await OPS[action](ctx, step)
                data.update({k: v for k, v in d.items() if k in ("screenshot", "path", "size", "title", "url")})
                lines.append(f"{i}. {action}: {text if action in ('find', 'snapshot', 'inspect') else text.splitlines()[0]}")
            out = "\n".join(lines) + "\n\n" + await AGENT.snapshot(max_chars=AFTER_MAX)
            return ToolResult(True, out, data)
        except BrowserError as e:
            lines.append(f"stopped: {e}")
            page = ""
            try:
                page = "\n\n" + await AGENT.snapshot(max_chars=3000) if AGENT.pages else ""
            except BrowserError:
                pass
            return ToolResult(False, "\n".join(lines) + page, data)
        except Exception as e:
            if "crash" in str(e).lower():
                url = AGENT.active.url if AGENT.active else ""
                return ToolResult(False, "\n".join(lines) + "\nstopped: " + await AGENT.recover_crash(url))
            return ToolResult(False, "\n".join(lines) + f"\nstopped: {type(e).__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}")
        finally:
            AGENT.last = time.monotonic()
