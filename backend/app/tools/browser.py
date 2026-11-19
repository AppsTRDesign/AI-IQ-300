"""Browser agent: a real Chromium window with its own lasting profile (data/browser-profile), driven like a person.
Pages are read as an accessibility tree whose elements carry refs (e12); tools click, type, fill forms, press keys,
scroll, wait, take screenshots and read the console and network requests by those refs.

Sign-ins the user makes in that window stay in the profile (cookies, local storage), so later tasks find them.
Separate from web.py's headless reading browser, which never keeps cookies. Nothing here solves bot checks or
CAPTCHAs: they are reported and handed to the user."""
from __future__ import annotations

import asyncio
import itertools
import os
import re
import shutil
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

from ..config import DATA_DIR, load_settings

PROFILE_DIR = DATA_DIR / "browser-profile"
IDLE = 900  # seconds without use before the window closes (the profile stays)
# Hidden window: no GPU compositing (the usual cause of renderer crashes without a screen), shared memory off.
HIDDEN_ARGS = ["--disable-gpu", "--disable-dev-shm-usage", "--disable-software-rasterizer"]
_UA_CACHE: dict[str, str] = {}  # channel -> the browser's user agent without the headless marker
SNAPSHOT_LINES = 700
# Development hosts: test sign-ins and test card numbers are typed only here (or on a test host the user named).
LOCAL_HOST = re.compile(r"^(localhost|127(\.\d{1,3}){3}|\[?::1\]?|0\.0\.0\.0|[\w.-]+\.localhost|[\w.-]+\.test)$", re.I)
TEST_LABEL = re.compile(r"(^|[.-])(staging|stage|dev|test|qa|sandbox|preview|uat)(\d*)([.-])", re.I)
# Buttons whose effect cannot be undone (send, delete, publish, buy...): asked before clicking on real sites.
RISKY = re.compile(r"(^|\W)(sil|silin|kaldır|gönder|yayınla|yayımla|paylaş|satın\s*al|öde|ödeme|sipariş|onayla|"
                   r"hesab\w*\s+kapat|aboneli\w*\s+(iptal|bitir)|para\s+(gönder|transfer)|havale|eft|kaydol|üye\s+ol|"
                   r"delete|remove|send|submit|publish|post|share|tweet|buy|purchase|pay|place\s+order|order\s+now|"
                   r"checkout|confirm|unsubscribe|transfer|deactivate|close\s+account|sign\s*up|register|reply)(\W|$)",
                   re.I)
CAPTCHA_TEXT = re.compile(r"verify you are (a )?human|i'?m not a robot|ben robot değilim|robot olmadığ|"
                          r"checking (if the site connection is secure|your browser)|güvenlik doğrulaması|"
                          r"unusual traffic|olağan dışı trafik", re.I)

# The page as an accessibility tree. Every interactive element (and headings) gets a lasting data-aiiq-ref
# attribute, so a ref stays valid across snapshots until the element leaves the page.
SNAPSHOT_JS = r"""(opts) => {
  const MAX = opts.max || 700, onlyInt = !!opts.interactive;
  let n = window.__aiiqN || 0;
  const out = [];
  const INTER = new Set(['link','button','textbox','searchbox','spinbutton','checkbox','radio','combobox','listbox',
    'option','menuitem','menuitemcheckbox','menuitemradio','tab','switch','slider','treeitem','clickable']);
  const LEAF = new Set(['link','button','textbox','searchbox','spinbutton','checkbox','radio','combobox','listbox',
    'option','slider','switch','heading','img']);
  const GROUP_TAG = {NAV:'navigation', MAIN:'main', HEADER:'banner', FOOTER:'contentinfo', ASIDE:'complementary',
    FORM:'form', DIALOG:'dialog', TABLE:'table', FIELDSET:'group'};
  const GROUP_ROLE = new Set(['navigation','main','banner','contentinfo','complementary','form','dialog','alertdialog',
    'alert','status','table','grid','tablist','menu','menubar','toolbar','search','region','group','tabpanel']);
  const clean = (t, k) => (t || '').replace(/\s+/g, ' ').trim().slice(0, k || 100);
  const hidden = (el) => {
    if (el.hidden || el.getAttribute('aria-hidden') === 'true') return true;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse') return true;
    if (el.tagName === 'DIALOG' && !el.open) return true;
    return false;
  };
  const roleOf = (el) => {
    const r = el.getAttribute('role');
    if (r) return r.split(' ')[0];
    const tag = el.tagName;
    if (tag === 'A' && el.hasAttribute('href')) return 'link';
    if (tag === 'BUTTON' || tag === 'SUMMARY') return 'button';
    if (tag === 'INPUT') {
      const t = (el.type || 'text').toLowerCase();
      if (t === 'hidden') return null;
      if (['button','submit','reset','image','file'].includes(t)) return 'button';
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      if (t === 'range') return 'slider';
      if (t === 'search') return 'searchbox';
      if (t === 'number') return 'spinbutton';
      return 'textbox';
    }
    if (tag === 'TEXTAREA') return 'textbox';
    if (tag === 'SELECT') return el.multiple ? 'listbox' : 'combobox';
    if (/^H[1-6]$/.test(tag)) return 'heading';
    if (tag === 'IMG') return el.alt ? 'img' : null;
    if (GROUP_TAG[tag]) return GROUP_TAG[tag];
    if (el.isContentEditable && !(el.parentElement && el.parentElement.isContentEditable)) return 'textbox';
    if (el.hasAttribute('onclick') || (el.hasAttribute('tabindex') && el.tabIndex >= 0)) return 'clickable';
    return null;
  };
  const nameOf = (el, role) => {
    let v = el.getAttribute('aria-label');
    if (!v && el.getAttribute('aria-labelledby'))
      v = el.getAttribute('aria-labelledby').split(/\s+/).map((id) => (document.getElementById(id) || {}).innerText || '').join(' ');
    if (!v && el.labels && el.labels.length) v = [...el.labels].map((l) => l.innerText).join(' ');
    if (!v && el.tagName === 'INPUT') {
      const t = el.type;
      if (['button','submit','reset'].includes(t)) v = el.value || t;
      else if (t === 'image') v = el.alt;
      else if (t === 'file') v = 'file chooser';
    }
    if (!v && ['textbox','searchbox','spinbutton','combobox','listbox'].includes(role))
      v = el.getAttribute('placeholder') || el.getAttribute('name') || el.title;
    if (!v && el.tagName === 'IMG') v = el.alt;
    if (!v && !['textbox','searchbox','spinbutton','combobox','listbox','table','form','main','navigation','banner',
                 'contentinfo','complementary','region','group','tabpanel','grid'].includes(role))
      v = el.innerText || el.textContent;
    if (!v) {
      const img = el.querySelector && el.querySelector('img[alt],svg[aria-label],[title]');
      if (img) v = img.getAttribute('alt') || img.getAttribute('aria-label') || img.getAttribute('title');
    }
    return clean(v || el.title, 100);
  };
  const ref = (el) => {
    let r = el.getAttribute('data-aiiq-ref');
    if (!r) { r = 'e' + (++n); el.setAttribute('data-aiiq-ref', r); }
    return r;
  };
  const extras = (el, role) => {
    const x = [];
    if (role === 'heading') x.push('level=' + (el.getAttribute('aria-level') || (el.tagName[1] || '')));
    const tag = el.tagName, type = (el.type || '').toLowerCase();
    if (tag === 'INPUT' && type === 'password') x.push('password');
    else if (tag === 'INPUT' && ['email','tel','url','date','time','datetime-local','month','week','color'].includes(type)) x.push('type=' + type);
    if (tag === 'INPUT' && type === 'file') x.push('type=file');
    if (['textbox','searchbox','spinbutton'].includes(role)) {
      const val = el.isContentEditable ? el.innerText : el.value;
      if (val) x.push('value="' + (type === 'password' ? '***' : clean(val, 60)) + '"');
      const ac = el.getAttribute('autocomplete') || '';
      if (/^cc-/.test(ac)) x.push('card-field');
    }
    if (tag === 'SELECT') {
      const opts = [...el.options];
      x.push('value="' + clean((el.selectedOptions[0] || {}).text || '', 40) + '"');
      x.push('options=' + JSON.stringify(opts.slice(0, 12).map((o) => clean(o.text, 30))) + (opts.length > 12 ? '+' + (opts.length - 12) : ''));
    }
    if (el.checked || el.getAttribute('aria-checked') === 'true') x.push('checked');
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') x.push('disabled');
    if (el.required) x.push('required');
    if (el.getAttribute('aria-invalid') === 'true') x.push('invalid');
    const exp = el.getAttribute('aria-expanded');
    if (exp) x.push('expanded=' + exp);
    if (el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-current')) x.push('current');
    if (role === 'link') {
      const h = el.getAttribute('href') || '';
      if (h && !/^javascript:/i.test(h)) x.push('href=' + h.slice(0, 90));
    }
    return x.length ? ' ' + x.join(' ') : '';
  };
  const ownText = (el) => {
    let t = '';
    for (const c of el.childNodes) if (c.nodeType === 3) t += c.textContent;
    return clean(t, 180);
  };
  let truncated = false;
  const walk = (root, depth) => {
    for (const el of root.children) {
      if (out.length >= MAX) { truncated = true; return; }
      const tag = el.tagName;
      if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','LINK','META'].includes(tag) || tag.toLowerCase() === 'svg') continue;
      if (hidden(el)) continue;
      const role = roleOf(el);
      const pad = '  '.repeat(depth);
      if (tag === 'IFRAME') {
        out.push(pad + '- iframe' + (el.title ? ' "' + clean(el.title, 60) + '"' : '') + ' src=' + clean(el.src, 90) + ' [' + ref(el) + ']');
        continue;
      }
      if (role && (INTER.has(role) || role === 'heading' || role === 'img')) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0 && role !== 'heading') { if (!LEAF.has(role)) walk(el, depth); continue; }
        if (!onlyInt || role !== 'img') {
          const name = nameOf(el, role);
          out.push(pad + '- ' + role + (name ? ' "' + name.replace(/"/g, "'") + '"' : '') + extras(el, role) + ' [' + ref(el) + ']');
        }
        if (!LEAF.has(role)) walk(el, depth + 1);
      } else if (role && GROUP_ROLE.has(role)) {
        const name = ['alert','status','dialog','alertdialog'].includes(role) ? nameOf(el, 'x') : clean(el.getAttribute('aria-label'), 60);
        if (!onlyInt || ['dialog','alertdialog','alert','form'].includes(role))
          out.push(pad + '- ' + role + (name ? ' "' + name.replace(/"/g, "'") + '"' : '') + ':');
        walk(el, depth + 1);
      } else {
        if (!onlyInt) {
          const t = ownText(el);
          if (t.length > 1) out.push(pad + '- text "' + t.replace(/"/g, "'") + '"');
        }
        walk(el, depth);
      }
      if (el.shadowRoot) walk(el.shadowRoot, depth);
    }
  };
  let start = document.body;
  if (opts.ref) start = document.querySelector('[data-aiiq-ref="' + opts.ref + '"]');
  if (!start) return {error: 'ref ' + opts.ref + ' is not on the page any more'};
  if (opts.ref) {
    const role = roleOf(start);
    out.push('- ' + (role || start.tagName.toLowerCase()) + ' [' + ref(start) + ']');
    walk(start, 1);
  } else walk(start, 0);
  window.__aiiqN = n;
  const frames = [...document.querySelectorAll('iframe')].map((f) => f.src || '').join(' ');
  const captcha = /recaptcha|hcaptcha|challenges\.cloudflare\.com|turnstile|arkoselabs|funcaptcha/i.test(frames)
    || !!document.querySelector('#challenge-form, #cf-challenge-running, .cf-turnstile, .g-recaptcha, .h-captcha');
  return {lines: out, truncated, title: document.title, url: location.href, captcha,
          bodyText: (document.body.innerText || '').slice(0, 1500)};
}"""

# What an element is, before acting on it: risky buttons, password/card fields, the form it belongs to.
ELEMENT_JS = r"""(el) => {
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 100);
  const type = (el.type || '').toLowerCase();
  const form = el.form || el.closest('form');
  const ac = (el.getAttribute('autocomplete') || '') + ' ' + (el.name || '') + ' ' + (el.id || '');
  const card = /cc-|card.?number|cardnumber|cvv|cvc|kart.?no|iban/i.test(ac);
  const formCard = !!(form && form.querySelector('[autocomplete^="cc-"],[name*="card" i],[name*="cvv" i],[name*="cvc" i]'));
  return {tag: el.tagName.toLowerCase(), type,
          name: clean(el.getAttribute('aria-label') || el.innerText || el.value || el.title || el.getAttribute('placeholder')),
          password: type === 'password', card,
          formPassword: !!(form && form.querySelector('input[type=password]')), formCard,
          submit: (el.tagName === 'BUTTON' && (!el.type || el.type === 'submit')) || ['submit','image'].includes(type),
          editable: ['INPUT','TEXTAREA'].includes(el.tagName) || el.isContentEditable,
          visible: (() => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; })()};
}"""

# A ref as the snapshot prints it ("- button "Kaydet" [e22]"): its role and name find the element again when the page
# re-rendered and the old ref is gone.
REF_LINE = re.compile(r'^\s*-\s+([a-z]+)(?:\s+"((?:[^"\\]|\\.)*)")?[^\n]*\[(e\d+)\]', re.M)
ARIA_ROLES = {"button", "link", "textbox", "combobox", "checkbox", "radio", "heading", "tab", "menuitem", "option",
              "listbox", "searchbox", "switch", "slider", "spinbutton", "img", "row", "cell", "listitem", "dialog"}


class BrowserError(Exception):
    pass


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


# Finds ONE thing blocking the page and marks the button that closes it with data-aiiq-dismiss="1":
# a cookie banner's reject button, or the close button of a modal that covers the middle of the screen.
DISMISS_JS = r"""(opts) => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const label = (e) => ((e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || '') + ' '
    + (e.innerText || e.value || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  const heading = (m) => ((m.querySelector('h1,h2,h3,h4,[class*=title i]') || {}).innerText || '').trim().slice(0, 70);
  document.querySelectorAll('[data-aiiq-dismiss]').forEach((e) => e.removeAttribute('data-aiiq-dismiss'));
  // 1) cookie / consent banner: only ever the reject / necessary-only choice
  const REJECT = /^(tümünü reddet|hepsini reddet|reddet|tüm çerezleri reddet|reject all|reject all cookies|reject|decline all|decline|refuse all|deny all|deny|only necessary|necessary only|use necessary cookies only|sadece gerekli( olanlar| çerezler)?|yalnızca (gerekli|zorunlu)( çerezler| olanlar)?|zorunlu olanlar|alle ablehnen|ablehnen|tout refuser|rechazar todo|rifiuta tutto)$/i;
  const COOKIE = /cookie|çerez|tanımlama|consent|gdpr|kvkk|privacy|gizlilik|datenschutz/i;
  for (const b of document.querySelectorAll('button,[role=button],a,input[type=button],input[type=submit]')) {
    if (!vis(b)) continue;
    const t = label(b);
    if (t.length > 40 || !REJECT.test(t)) continue;
    let p = b;
    for (let i = 0; i < 8 && p; i++, p = p.parentElement) {
      if (COOKIE.test((p.innerText || '').slice(0, 3000))) {
        b.setAttribute('data-aiiq-dismiss', '1');
        return {kind: 'cookie', title: '', button: t};
      }
    }
  }
  if (opts && opts.cookieOnly) return null;
  // 2) a modal over the content
  const W = innerWidth, H = innerHeight;
  const cands = [...document.querySelectorAll('[role=dialog],[role=alertdialog],[aria-modal=true],dialog[open],'
    + '[class*=modal i],[class*=popup i],[class*=pop-up i],[class*=lightbox i],[id*=modal i],[id*=popup i]')].filter(vis);
  let el = document.elementFromPoint(W / 2, H / 2);
  for (let i = 0; el && i < 20; i++, el = el.parentElement) {
    const s = getComputedStyle(el);
    if ((s.position === 'fixed' || s.position === 'absolute') && (+s.zIndex || 0) >= 10) { cands.push(el); }
  }
  const CLOSE_TEXT = /^(×|✕|✖|╳|x|kapat|close|dismiss|hayır,? teşekkürler|no,? thanks|şimdi değil|not now|vazgeç|atla|skip|daha sonra|later|maybe later)$/i;
  const CLOSE_ATTR = /(^|[\s_-])(close|kapat|dismiss|btn-close|modal-close|popup-close)([\s_-]|$)/i;
  for (const m of cands) {
    const r = m.getBoundingClientRect();
    if (r.width < 200 || r.height < 100) continue;                    // toasts and small bars stay
    if (m.querySelector('input[type=password],[autocomplete^=cc-],input[name*=card i]')) continue;  // sign-in/payment
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), W - 1), cy = Math.min(Math.max(r.top + r.height / 2, 1), H - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (!hit || !(m.contains(hit) || hit.contains(m))) continue;     // not in front
    const closers = [...m.querySelectorAll('button,[role=button],a,span,i,div,svg,img')].filter(vis).filter((b) => {
      const br = b.getBoundingClientRect();
      const attr = (b.getAttribute('class') || '') + ' ' + (b.id || '') + ' ' + (b.getAttribute('data-testid') || '');
      // a close icon often sits in a wide wrapper (div.modal-close spanning the box): its class still says close
      if (br.height > 90 || (br.width > 260 && !CLOSE_ATTR.test(attr))) return false;
      const t = label(b);
      return CLOSE_TEXT.test(t) || CLOSE_ATTR.test(attr) || /close|kapat|dismiss/i.test(b.getAttribute('aria-label') || '');
    });
    // the most specific closer: smallest element, preferring real buttons
    closers.sort((a, b) => ((b.tagName === 'BUTTON') - (a.tagName === 'BUTTON'))
      || (a.getBoundingClientRect().width * a.getBoundingClientRect().height) - (b.getBoundingClientRect().width * b.getBoundingClientRect().height));
    let c = closers[0];
    if (c) {
      const clickable = c.closest('button,[role=button],a') || c;
      clickable.setAttribute('data-aiiq-dismiss', '1');
      return {kind: 'modal', title: heading(m), button: label(clickable).slice(0, 30) || 'x'};
    }
    // no close button: a real dialog, or a fixed layer covering most of the screen (any modal), gets one Escape
    const covers = getComputedStyle(m).position === 'fixed' && r.width * r.height > W * H * 0.5;
    if (m.matches('[role=dialog],[role=alertdialog],[aria-modal=true],dialog[open]') || covers)
      return {kind: 'modal', title: heading(m), escape: true};
  }
  return null;
}"""


def is_local(url: str) -> bool:
    """A local development address (or a page of the working folder): test sign-ins are allowed here."""
    if url.startswith("file:") or url in ("", "about:blank"):
        return True
    return bool(LOCAL_HOST.match(host_of(url)))


def is_named_test_host(url: str, request_text: str) -> bool:
    """A hosted test environment (staging.example.com...) that the user's own request names."""
    host = host_of(url)
    return bool(host and TEST_LABEL.search(host + ".") and host in (request_text or "").lower())


def _keys(text: str) -> list[str]:
    """'ctrl+a Backspace Enter' -> Playwright key names."""
    names = {"ctrl": "Control", "control": "Control", "cmd": "Meta", "meta": "Meta", "win": "Meta", "alt": "Alt",
             "option": "Alt", "shift": "Shift", "enter": "Enter", "return": "Enter", "esc": "Escape", "escape": "Escape",
             "tab": "Tab", "space": "Space", "backspace": "Backspace", "delete": "Delete", "del": "Delete",
             "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight", "home": "Home",
             "end": "End", "pageup": "PageUp", "pagedown": "PageDown"}
    out = []
    for combo in text.split():
        parts = [names.get(p.lower(), p) for p in combo.split("+")]
        out.append("+".join(parts))
    return out


class BrowserAgent:
    """One visible browser shared by the app's tasks (one action at a time), started on first use."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.pw = self.context = None
        self.pages: list = []
        self.ids: dict = {}  # page -> "t1"
        self.active = None
        self.counter = itertools.count(1)
        self.req_counter = itertools.count(1)
        self.console: dict = {}  # tab id -> deque of console lines
        self.network: dict = {}  # tab id -> deque of requests
        self.responses: dict = {}  # request id -> response (bodies on demand)
        self._status: dict = {}  # id(request) -> HTTP status from the response event
        self.dialogs: deque = deque(maxlen=20)
        self.dialog_choice = "dismiss"  # for confirm/prompt dialogs of the next action
        self.downloads: list[str] = []
        self.download_dir: Path | None = None
        self.seen_console: dict = {}  # tab id -> console count already reported
        self.bad: dict = {}  # tab id -> failed requests not reported yet (4xx / 5xx, failed loads)
        self.last = 0.0
        self.reaper: asyncio.Task | None = None
        self.headless = False
        self.fast = False
        self.channel = ""
        self.crashes: dict[str, int] = {}  # host -> renderer crashes in this browser session

    # ---------- lifecycle ----------
    async def recover_crash(self, url: str) -> str:
        """A tab's renderer crashed (a heavy page): drop the dead tab and open a fresh one, so the next call works.
        Returns the advice for the model; a site that crashed twice is not opened again in this session."""
        host = host_of(url) if url.startswith("http") else ""
        self.crashes[host] = self.crashes.get(host, 0) + 1
        for p in [p for p in self.pages if p.is_closed() or p is self.active]:
            try:
                await p.close()
            except Exception:
                pass
            self._page_closed(p)
        if self.context is not None and not self.pages:
            try:
                await self._new_page()
            except Exception:
                await self.close()  # the whole browser is gone: the next call starts it again
        if self.crashes[host] >= 2:
            return (f"The page {url} crashed the browser again (it is too heavy for the browser agent). Do NOT open it "
                    "in the browser again: read it with fetch_url (text) or web_screenshot (image) instead.")
        return (f"The page {url} crashed the browser tab (a heavy page). A fresh tab is open. Retry once with "
                "browser_navigate; avoid large browser_inspect js queries. If it crashes again, use fetch_url instead.")

    async def _normal_ua(self, channel: str) -> str:
        """The installed browser's real user agent without the "HeadlessChrome" marker (read once, cached)."""
        if channel in _UA_CACHE:
            return _UA_CACHE[channel]
        ua = ""
        try:
            b = await self.pw.chromium.launch(headless=True, args=HIDDEN_ARGS, **({"channel": channel} if channel else {}))
            try:
                ctx = await b.new_context()
                page = await ctx.new_page()
                ua = await page.evaluate("navigator.userAgent")
            finally:
                await b.close()
        except Exception:
            ua = ""
        _UA_CACHE[channel] = ua.replace("HeadlessChrome", "Chrome")
        return _UA_CACHE[channel]

    def crashed_host(self, url: str) -> bool:
        return self.crashes.get(host_of(url) if url.startswith("http") else "", 0) >= 2
    def running(self) -> bool:
        return self.context is not None

    def status(self) -> dict:
        size = 0
        if PROFILE_DIR.exists():
            for p in PROFILE_DIR.rglob("*"):
                try:
                    size += p.stat().st_size if p.is_file() else 0
                except OSError:
                    pass
        return {"running": self.running(), "headless": self.headless, "channel": self.channel,
                "tabs": [{"id": self.ids.get(p), "url": p.url, "active": p is self.active} for p in self.pages],
                "profile": PROFILE_DIR.exists(), "profile_bytes": size}

    async def ensure(self):
        if self.context is not None:
            self.last = time.monotonic()
            if not self.pages:
                await self._new_page()
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise BrowserError("Playwright is not installed (run install.bat / install.sh).") from e
        cfg = load_settings().get("browser") or {}
        no_display = sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        self.channel = str(cfg.get("channel") or "")
        # "fast": the quick reader - always hidden, no images/media/fonts loaded (pages open and read much faster).
        # force_visible: a CAPTCHA/sign-in was handed to the user, who needs a real window (and images) to do it.
        force = getattr(self, "force_visible", False) and not no_display
        self.fast = self.channel == "fast" and not force
        self.headless = not force and (self.fast or os.environ.get("AIIQ_BROWSER_HEADLESS") == "1"
                                       or not cfg.get("visible", True) or no_display)
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self.pw = await async_playwright().start()
        lang = "tr-TR" if (load_settings().get("language") or "tr") == "tr" else "en-US"
        kw = dict(user_data_dir=str(PROFILE_DIR), headless=self.headless, locale=lang, accept_downloads=True)
        channel = self.channel if self.channel in ("chrome", "msedge") else ("chromium" if self.headless else "")
        accept_lang = "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7" if lang == "tr-TR" else "en-US,en;q=0.9,tr;q=0.6"
        kw["extra_http_headers"] = {"Accept-Language": accept_lang}
        if self.headless:
            # A full background profile: the old headless shell crashed on heavy pages ("Target crashed" in a loop),
            # so hidden windows use the full Chromium in its new headless mode without GPU compositing, with a
            # desktop-sized screen, the user's language, the system time zone and the browser's own user agent
            # with the "Headless" marker removed (sites send such clients a different, often broken page). Nothing
            # here hides automation from bot checks: those are still reported and handed to the user.
            kw.update(viewport={"width": 1366, "height": 900}, screen={"width": 1920, "height": 1080},
                      device_scale_factor=1, color_scheme="light", args=HIDDEN_ARGS)
            if ua := await self._normal_ua(channel):
                kw["user_agent"] = ua
        else:
            kw.update(no_viewport=True, args=["--window-size=1320,900"])
        try:
            try:
                self.context = await self.pw.chromium.launch_persistent_context(**kw, **({"channel": channel} if channel else {}))
            except Exception:
                if not channel:
                    raise
                self.channel = "fast" if self.fast else ""  # Chrome/Edge not installed: the bundled Chromium
                self.context = await self.pw.chromium.launch_persistent_context(**kw)
        except Exception as e:
            await self.pw.stop()
            self.pw = None
            text = str(e)
            if "Executable doesn't exist" in text:
                raise BrowserError("Chromium for Playwright is missing: run `python -m playwright install chromium`.") from e
            if "ProcessSingleton" in text or "already in use" in text or "lock" in text.lower():
                raise BrowserError("The browser profile is in use by another window of this app; close it and retry.") from e
            raise BrowserError(f"The browser could not start: {text.splitlines()[0][:300]}") from e
        if self.fast:
            await self.context.route("**/*", lambda route: route.abort()
                                     if route.request.resource_type in ("image", "media", "font") else route.continue_())
        self.context.on("page", self._on_page)
        self.context.on("close", lambda *_: self._closed())
        for p in list(self.context.pages):
            self._on_page(p)
        if not self.pages:
            await self._new_page()
        self.last = time.monotonic()
        if not self.reaper or self.reaper.done():
            self.reaper = asyncio.create_task(self._reap())

    def _closed(self):
        self.context = None
        self.pages, self.ids, self.active = [], {}, None

    async def _reap(self):
        while self.context is not None:
            await asyncio.sleep(30)
            if time.monotonic() - self.last > (300 if self.headless else IDLE) and not self.lock.locked():
                await self.close()
                return

    async def close(self):
        ctx, pw = self.context, self.pw
        self._closed()
        self.pw = None
        try:
            if ctx:
                await ctx.close()
            if pw:
                await pw.stop()
        except Exception:
            pass

    async def reset_profile(self) -> bool:
        """Forget every sign-in: close the window and delete the profile folder."""
        await self.close()
        await asyncio.sleep(0.3)
        if PROFILE_DIR.exists():
            await asyncio.to_thread(shutil.rmtree, PROFILE_DIR, True)
        return not PROFILE_DIR.exists()

    def _on_page(self, page):
        if page in self.ids:
            return
        tid = f"t{next(self.counter)}"
        self.ids[page] = tid
        self.pages.append(page)
        self.active = page
        self.console[tid] = deque(maxlen=300)
        self.network[tid] = deque(maxlen=400)
        page.on("console", lambda m, t=tid: None if self.fast and "Failed to load resource" in m.text else self.console[t].append(
            {"type": m.type, "text": m.text[:1000], "url": (m.location or {}).get("url", ""), "ts": time.time()}))
        page.on("pageerror", lambda e, t=tid: self.console[t].append(
            {"type": "error", "text": f"Uncaught {str(e)[:1000]}", "url": "", "ts": time.time()}))
        # The status straight from the response event: request.response() came back empty for 404 / 500 answers, so
        # failed requests were listed without a status and never reported as failed.
        page.on("response", lambda r, t=tid: self._on_response(t, r))
        page.on("requestfinished", lambda r, t=tid: asyncio.ensure_future(self._finished(t, r)))
        page.on("requestfailed", lambda r, t=tid: None if self.fast and r.resource_type in ("image", "media", "font")
                else self._failed_req(t, r))  # fast mode skips those on purpose
        page.on("dialog", lambda d: asyncio.ensure_future(self._dialog(d)))
        page.on("download", lambda d: asyncio.ensure_future(self._download(d)))
        page.on("close", lambda p: self._page_closed(p))

    def _page_closed(self, page):
        if page in self.pages:
            self.pages.remove(page)
        if self.active is page:
            self.active = self.pages[-1] if self.pages else None

    def _on_response(self, tid, resp):
        """Sync with the page: a 4xx / 5xx is noted at once for the next page check (the request log fills later)."""
        self._status[id(resp.request)] = resp.status
        if resp.status >= 400 and "favicon" not in resp.url:
            self.bad.setdefault(tid, deque(maxlen=50)).append(f"{resp.status} {resp.request.resource_type} {resp.url[-120:]}")

    def _failed_req(self, tid, req):
        failure = req.failure or "failed"
        if not failure.endswith("ERR_ABORTED"):
            self.bad.setdefault(tid, deque(maxlen=50)).append(f"{failure} {req.resource_type} {req.url[-120:]}")
        self._record(tid, req, None, failure)

    async def _finished(self, tid, req):
        try:
            resp = await req.response()
        except Exception:
            resp = None
        self._record(tid, req, resp, None)

    def _record(self, tid, req, resp, failure):
        rid = f"r{next(self.req_counter)}"
        self.network.setdefault(tid, deque(maxlen=400)).append(
            {"id": rid, "method": req.method, "url": req.url, "type": req.resource_type,
             "status": resp.status if resp else self._status.pop(id(req), None), "failure": failure, "ts": time.time()})
        if len(self._status) > 2000:
            self._status.clear()
        if resp is not None and req.resource_type in ("xhr", "fetch", "document"):
            self.responses[rid] = resp
            if len(self.responses) > 200:
                self.responses.pop(next(iter(self.responses)))

    async def _dialog(self, dialog):
        kind = dialog.type
        accept = kind in ("alert", "beforeunload") or self.dialog_choice == "accept"
        self.dialogs.append({"type": kind, "message": dialog.message[:300], "answer": "accepted" if accept else "dismissed",
                             "ts": time.time()})
        try:
            await (dialog.accept() if accept else dialog.dismiss())
        except Exception:
            pass

    async def _download(self, download):
        name = re.sub(r"[^\w.\- ]+", "_", download.suggested_filename or "download")[:120]
        folder = self.download_dir or (DATA_DIR / "downloads")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        try:
            await download.save_as(str(target))
            self.downloads.append(str(target))
        except Exception:
            pass

    async def _new_page(self, url: str = ""):
        page = await self.context.new_page()
        self._on_page(page)
        if url:
            await self.goto(page, url)
        return page

    # ---------- helpers ----------
    @property
    def page(self):
        if not self.active:
            raise BrowserError("No browser tab is open: use browser_navigate first.")
        return self.active

    def tab_id(self, page=None) -> str:
        return self.ids.get(page or self.active, "?")

    async def goto(self, page, url: str):
        self.acted = False  # a fresh page: pop-ups now are the site's, not the model's
        if is_local(url) and not getattr(page, "_aiiq_nocache", False):
            # A dev server's page after a fix: the cached bundle / error page made the model see the old errors again
            # and again. Local pages always load fresh.
            try:
                cdp = await page.context.new_cdp_session(page)
                await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                page._aiiq_nocache = True
            except Exception:  # noqa: BLE001 - not Chromium: a normal load
                pass
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            text = str(e)
            if "ERR_CONNECTION_REFUSED" in text:
                raise BrowserError(f"Nothing is running at {url} (connection refused). Start the project first "
                                   "(start tool), then open it again.") from e
            if "ERR_NAME_NOT_RESOLVED" in text:
                raise BrowserError(f"The address {url} does not exist (name not resolved).") from e
            if "Timeout" in text:
                return None  # slow page: what has loaded is still usable
            raise BrowserError(text.splitlines()[0][:300]) from e
        await self.settle(page)
        return resp

    async def settle(self, page, idle_ms: int = 1500):
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=idle_ms)
        except Exception:
            pass

    def all_matches(self, ref: str = "", selector: str = "", text: str = ""):
        """(locator of every match, label). A CSS selector or a label sent as ref is used as what it is."""
        page = self.page
        if ref:
            r = ref.strip().replace("ref=", "").replace("ref_", "e")
            if re.fullmatch(r"\[?e?\d+\]?", r):
                r = r.strip("[]")
                r = r if r.startswith("e") else f"e{r}"
                return page.locator(f'[data-aiiq-ref="{r}"]'), r
            if re.search(r"[#.\[\]=>:]", r) or re.fullmatch(r"(button|input|select|textarea|form|a|h[1-6])", r):
                selector = r  # input[id='title'], #save
            else:
                text = r  # "Kaydet"
        if selector:
            return page.locator(selector), selector
        if text:
            exact = page.get_by_role("button", name=text, exact=True).or_(page.get_by_role("link", name=text, exact=True))
            return (exact.or_(page.get_by_label(text)).or_(page.get_by_placeholder(text))
                    .or_(page.get_by_text(text, exact=False))), f'"{text}"'
        raise BrowserError("Say which element: ref (from browser_snapshot), or selector, or text.")

    def locator(self, ref: str = "", selector: str = "", text: str = ""):
        base, what = self.all_matches(ref, selector, text)
        return base.first, what

    async def element(self, loc, what: str) -> dict:
        try:
            if await loc.count() == 0:
                raise BrowserError(f"{what} is not on the page (it changed): take browser_snapshot and use a current ref.")
            return await loc.evaluate(ELEMENT_JS)
        except BrowserError:
            raise
        except Exception as e:
            raise BrowserError(f"{what}: {str(e).splitlines()[0][:200]}") from e

    async def target(self, ref: str = "", selector: str = "", text: str = "") -> tuple:
        """The element to act on, found robustly: a ref that went stale (the page re-rendered) is found again by the
        role and name it had in the last snapshot; of several matches the visible one is taken; a hidden element is
        reported at once (instead of an 8-second click timeout) with what to do."""
        base, what = self.all_matches(ref, selector, text)
        page, note = self.page, ""
        try:
            n = await base.count()
        except Exception as e:  # an invalid CSS selector
            raise BrowserError(f"{what}: {str(e).splitlines()[0][:160]}. Use a ref from browser_snapshot or text=...") from e
        if what.startswith('"') and n:
            # by text: the most specific kind first - a button / link with that name, a field with that label or
            # placeholder, an element with exactly that text - then any element containing it
            t = what[1:-1]
            for c in (page.get_by_role("button", name=t, exact=True), page.get_by_role("link", name=t, exact=True),
                      page.get_by_label(t, exact=True), page.get_by_placeholder(t, exact=True),
                      page.get_by_text(t, exact=True), page.get_by_label(t), page.get_by_placeholder(t)):
                try:
                    if k := await c.count():
                        base, n = c, k
                        break
                except Exception:
                    continue
        if n == 0 and (known := getattr(self, "ref_names", {}).get(what)):
            role, name = known
            cands = []
            if role in ARIA_ROLES and name:
                cands.append(page.get_by_role(role, name=name, exact=True))
            if name:
                cands += [page.get_by_placeholder(name, exact=True), page.get_by_label(name, exact=True),
                          page.locator(f'[name="{name}"]'), page.get_by_text(name, exact=True)]
            for c in cands:
                try:
                    if n := await c.count():
                        base, note = c, f' (ref {what} had gone stale; found {role} "{name}" again)'
                        break
                except Exception:
                    continue
        loc = base.first
        if n > 1:  # several matches: the first visible one (a hidden template copy often comes first)
            try:
                for i in range(min(n, 15)):
                    if await base.nth(i).is_visible():
                        loc = base.nth(i)
                        break
            except Exception:
                pass
        info = await self.element(loc, what)
        if not info.get("visible", True) and info.get("tag") != "option":  # an <option> is chosen through its select
            raise BrowserError(f"{what} is on the page but hidden (display:none / zero size): it is in a part that is "
                               "not shown now (another tab or section, a closed menu or modal). Open that part first "
                               "(click its tab / link / button), then use the refs of the new snapshot.")
        info["note"] = note
        return loc, what, info

    async def dismiss_popups(self, page, cookie_only: bool | None = None) -> list[str]:
        """Close what blocks the page: a cookie banner (always with its most private choice, "Reject all") and a
        modal/popup in front of the content (newsletter, "pick a gender", app ads...) via its close button, or
        Escape when it has none. Dialogs holding a password or card field are left alone (the task may need them).
        Settings > Browser agent > close pop-ups (on by default)."""
        if (load_settings().get("browser") or {}).get("dismiss_popups") is False:
            return []
        if cookie_only is None:
            # A modal that shows up after the model clicked or typed is the model's own (a "New task" form), and on
            # a local site the modals are the app under test: only cookie banners are closed there.
            cookie_only = is_local(page.url) or getattr(self, "acted", False)
        done: list[str] = []
        for _ in range(3):
            try:
                found = await page.evaluate(DISMISS_JS, {"cookieOnly": bool(cookie_only)})
            except Exception:  # navigating: nothing to close yet
                break
            if not found:
                break
            what = f"{'cookie banner' if found['kind'] == 'cookie' else 'pop-up'} \"{found.get('title') or ''}\"".replace(' ""', "")
            if found.get("escape"):
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.4)
                done.append(f"{what} (Escape)")
                break  # no close button: one Escape, never a loop
            loc = page.locator('[data-aiiq-dismiss="1"]').first
            try:
                await loc.click(timeout=2500)
            except Exception:
                try:
                    await loc.evaluate("(e) => e.click()")
                except Exception:
                    break
            await asyncio.sleep(0.45)
            done.append(f"{what} -> clicked \"{found.get('button') or 'close'}\"")
        if done:
            self.closed_popups = getattr(self, "closed_popups", []) + done
        return done

    def popup_note(self) -> str:
        done = getattr(self, "closed_popups", [])
        self.closed_popups = []
        return f"[Closed automatically: {'; '.join(done)[:400]}]" if done else ""

    async def snapshot(self, interactive: bool = False, ref: str = "", max_chars: int = 9000) -> str:
        page = self.page
        await self.dismiss_popups(page)  # pop-ups that appeared after the page loaded
        try:
            data = await page.evaluate(SNAPSHOT_JS, {"max": SNAPSHOT_LINES, "interactive": interactive, "ref": ref})
        except Exception as e:  # navigation in progress
            await self.settle(page)
            try:
                data = await page.evaluate(SNAPSHOT_JS, {"max": SNAPSHOT_LINES, "interactive": interactive, "ref": ref})
            except Exception:
                raise BrowserError(f"The page could not be read: {str(e).splitlines()[0][:200]}") from e
        if data.get("error"):
            raise BrowserError(data["error"])
        head = [f"Tab {self.tab_id()} · {data.get('title') or '(no title)'} · {data.get('url')}"]
        if len(self.pages) > 1:
            head.append("Other tabs: " + ", ".join(f"{self.ids[p]} {p.url[:80]}" for p in self.pages if p is not page))
        if data.get("captcha") or CAPTCHA_TEXT.search(data.get("bodyText") or ""):
            head.append("[BOT CHECK / CAPTCHA on this page: never try to solve or click it. Call browser_handoff now "
                        "(reason: the CAPTCHA): the window is shown to the user, and as soon as they solve it the task "
                        "continues by itself - then go on with the next step. For plain reading, another source also works.]")
        notes = self.news()
        if notes:
            head.append(notes)
        if closed := self.popup_note():
            head.append(closed)
        body = "\n".join(data.get("lines") or []) or "(no readable elements)"
        self.remember_refs(body)
        if data.get("truncated"):
            body += "\n... (more elements: use browser_find, or browser_snapshot ref=... for one part)"
        text = "\n".join(head) + "\n" + body
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (cut: use browser_find or a ref for one part of the page)"
        return text

    def remember_refs(self, text: str) -> None:
        """role + name of every ref a snapshot showed (a stale ref is found again by them)."""
        names = getattr(self, "ref_names", {})
        for role, name, ref in REF_LINE.findall(text or ""):
            names[ref] = (role, name.replace('\\"', '"'))
        if len(names) > 4000:
            names = dict(list(names.items())[-2000:])
        self.ref_names = names

    def news(self) -> str:
        """Console errors, dialogs and downloads since the last report."""
        out = []
        tid = self.tab_id()
        logs = list(self.console.get(tid, []))
        seen = self.seen_console.get(tid, 0)
        errors = [m for m in logs[seen:] if m["type"] in ("error", "warning")]
        self.seen_console[tid] = len(logs)
        # Failed requests since the last report too (a 404 script / css, a 500 API call): every page load and action
        # says at once what broke, so it is fixed before the test goes on.
        failed = list(dict.fromkeys(self.bad.get(tid, [])))
        self.bad.pop(tid, None)
        if errors:
            out.append(f"[{len(errors)} new console error/warning: " + " | ".join(m["text"][:200] for m in errors[:4]) + "]")
        if failed:
            out.append(f"[{len(failed)} failed request(s): " + " | ".join(failed[:4]) + "]")
        if errors and any(m["type"] == "error" for m in errors) or failed:
            out.append("[Page check: fix these errors in the code now, reload and check again before testing further "
                       "(details: browser_inspect what=console only_errors=true / what=network failed_only=true).]")
        while self.dialogs:
            d = self.dialogs.popleft()
            out.append(f"[Dialog ({d['type']}) \"{d['message']}\" was {d['answer']}"
                       + (". To confirm it, repeat the action with dialog=accept." if d["answer"] == "dismissed" else "") + "]")
        while self.downloads:
            out.append(f"[Downloaded: {self.downloads.pop(0)}]")
        return "\n".join(out)

    async def find(self, query: str, limit: int = 20) -> list[str]:
        page = self.page
        data = await page.evaluate(SNAPSHOT_JS, {"max": 4000, "interactive": False})
        q = query.casefold().replace("i̇", "i")
        words = [w for w in re.split(r"\s+", q) if w]
        self.remember_refs("\n".join(data.get("lines") or []))
        hits = [line.strip() for line in data.get("lines") or []
                if all(w in line.casefold().replace("i̇", "i") for w in words) and "[e" in line]
        if not hits:  # text lines without refs: show them too (the model can click by text)
            hits = [line.strip() for line in data.get("lines") or [] if all(w in line.casefold() for w in words)]
        return hits[:limit]


AGENT = BrowserAgent()
