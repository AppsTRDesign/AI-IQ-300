"""The evaluation tasks: what the model is asked, what is put in its folder first, and how the result is checked.

Every check looks at what really exists after the task: files on disk, tests that run, a page in a real browser,
documents opened with their own readers, the task's trace. Nothing the model says is counted as done.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"
Check = tuple[str, bool, str]


@dataclass
class Task:
    id: str
    title: dict
    prompt: dict
    check: Callable[[Path, dict], list[Check]]
    seed: str = ""  # folder under tasks/ copied into the chat folder before the task
    net_drop: bool = False  # the runner cuts the model's connection mid-task
    timeout_s: int = 1800
    tags: list[str] = field(default_factory=list)
    setup: Callable[[Path], None] | None = None  # extra files a seed in git cannot carry (.env, __pycache__)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def _run_pytest(ws: Path, tests: list[Path], timeout: int = 180) -> tuple[bool, str]:
    """Runs test files against a copy of the workspace (the checks never change the model's folder)."""
    tmp = Path(tempfile.mkdtemp(prefix="aiiq-eval-check-"))
    try:
        dst = tmp / "ws"
        shutil.copytree(ws, dst, ignore=shutil.ignore_patterns(".session", "node_modules", "__pycache__", ".pytest_cache"))
        names = []
        for t in tests:
            shutil.copy2(t, dst / t.name)
            names.append(t.name)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *names], cwd=dst,
                           capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        # pytest's own result line ("3 passed", "1 failed, 2 passed"), not a warning printed on stderr
        lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        result = next((ln for ln in reversed(lines) if re.search(r"\b(passed|failed|error)", ln)), lines[-1] if lines else "")
        if r.returncode != 0:
            first = next((ln for ln in lines if ln.startswith(("FAILED", "ERROR", "E "))), "")
            result = f"{result} | {first}" if first else result
        return r.returncode == 0, result[:240]
    except subprocess.TimeoutExpired:
        return False, "tests timed out"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------------------------------------ 1. web app
def check_web(ws: Path, run: dict) -> list[Check]:
    app = ws / "todo"
    out: list[Check] = [(f"todo/{n} exists", (app / n).is_file(), "") for n in ("index.html", "style.css", "app.js")]
    if not (app / "index.html").is_file():
        # Written in the wrong folder (evren:auto put the files in the chat folder's root): the "exists" checks fail,
        # the page is still tested where it is, so the report says whether the app itself works.
        found = sorted((p for p in ws.rglob("index.html") if ".session" not in p.parts and "node_modules" not in p.parts),
                       key=lambda p: len(p.parts))
        if not found:
            return out + [("page works in a browser", False, "no index.html")]
        app = found[0].parent
        where = app.relative_to(ws).as_posix() or "."
        out = [(n, ok, i if ok else f"found in {where}/") for n, ok, i in out]
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=app,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        from playwright.sync_api import sync_playwright
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        errors, failed = [], []
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            page = b.new_page()
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("requestfailed", lambda r: failed.append(r.url))
            page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 and not r.url.endswith("favicon.ico") else None)
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load", timeout=20000)
            page.wait_for_timeout(500)
            parts = {sel: page.locator(sel).count() > 0 for sel in ("#new-todo", "#add", "#list")}
            out.append(("input #new-todo, button #add, list #list", all(parts.values()),
                        ", ".join(k for k, v in parts.items() if not v)))
            added = kept = False
            if all(parts.values()):
                page.fill("#new-todo", "Süt al 42")
                page.click("#add")
                page.wait_for_timeout(400)
                # One list item holds the text. Not "one more item than before": an empty-state row ("Henüz görev
                # yok", which the app's design rules ask for) is replaced by the first item, so the count stays 1.
                added = page.locator("#list li", has_text="Süt al 42").count() == 1
                page.reload(wait_until="load")
                page.wait_for_timeout(500)
                kept = "Süt al 42" in page.inner_text("#list")
            out.append(("clicking Add puts the text in the list", added, ""))
            out.append(("the item is still there after a reload (localStorage)", kept, ""))
            out.append(("no console errors", not errors, "; ".join(errors[:3])[:200]))
            out.append(("no failed requests", not failed, "; ".join(failed[:3])[:200]))
            b.close()
    except Exception as e:  # noqa: BLE001
        out.append(("page works in a browser", False, f"{type(e).__name__}: {e}"[:200]))
    finally:
        srv.terminate()
    return out


# ------------------------------------------------------------------------------------------------ 2. broken Python
def check_fix(ws: Path, run: dict) -> list[Check]:
    seed = TASKS_DIR / "fix_python" / "seed"
    out: list[Check] = [("test_stats.py left unchanged", _sha(ws / "test_stats.py") == _sha(seed / "test_stats.py"), "")]
    ok, info = _run_pytest(ws, [seed / "test_stats.py"])
    out.append(("the given tests pass", ok, info))
    ok, info = _run_pytest(ws, [TASKS_DIR / "fix_python" / "hidden_test.py"])
    out.append(("hidden tests of the same spec pass", ok, info))
    return out


# ------------------------------------------------------------------------------------------------ 3. five-file change
def _names(src: str) -> set[str]:
    """Identifiers of Python source, plus names inside f-string fields (Python 3.12 tokenizes those too)."""
    import io
    import tokenize
    try:
        return {t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.NAME}
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return set(re.findall(r"\b\w+\b", re.sub(r"#[^\n]*|\"\"\".*?\"\"\"|'''.*?'''", " ", src, flags=re.S)))


def check_multi(ws: Path, run: dict) -> list[Check]:
    shop = ws / "shop"
    out: list[Check] = []
    leftovers = []
    for f in sorted(shop.glob("*.py")):
        # Python names only: "the product's price" in a docstring or comment is English, not the old field
        # (evren:auto renamed every use correctly and was failed for pricing.py's docstring).
        if "price" in _names(f.read_text(encoding="utf-8", errors="replace")):
            leftovers.append(f.name)
    out.append(("no old `price` name left in shop/*.py", not leftovers, ", ".join(leftovers)))
    seed = TASKS_DIR / "multi_file" / "seed"
    changed = [n for n in ("models.py", "inventory.py", "pricing.py", "report.py", "cli.py")
               if _sha(shop / n) != _sha(seed / "shop" / n)]
    out.append(("all five modules changed", len(changed) == 5, f"{len(changed)}/5"))
    readme = (ws / "README.md").read_text(encoding="utf-8", errors="replace") if (ws / "README.md").is_file() else ""
    out.append(("README names unit_price and low_stock", "unit_price" in readme and "low_stock" in readme, ""))
    ok, info = _run_pytest(ws, [TASKS_DIR / "multi_file" / "hidden_test.py"])
    out.append(("hidden tests pass (rename, low_stock, report, cli)", ok, info))
    return out


# ------------------------------------------------------------------------------------------------ 4. Word + PDF
_HEADS = {"tr": ("Giriş", "Güçlü Yanlar", "Sonuç"), "en": ("Introduction", "Strengths", "Conclusion")}
_RESIDUE = re.compile(r"^\s*#{1,6}\s*\S|\*\*[^*\n]+\*\*|__[^_\n]+__|^\s*```", re.M)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def check_docs(ws: Path, run: dict) -> list[Check]:
    heads = _HEADS[run.get("lang") or "tr"]
    out: list[Check] = []
    docx, pdf = ws / "docs" / "rapor.docx", ws / "docs" / "rapor.pdf"
    if run.get("lang") == "en":
        docx, pdf = ws / "docs" / "report.docx", ws / "docs" / "report.pdf"
    try:
        import docx as docx_lib
        d = docx_lib.Document(str(docx))
        styled = {_norm(p.text) for p in d.paragraphs if p.style is not None and (p.style.name or "").lower().startswith(("heading", "title", "başlık"))}
        text = "\n".join(p.text for p in d.paragraphs) + "\n" + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
        out.append((f"{docx.name} opens", True, f"{len(d.paragraphs)} paragraphs"))
        out.append((f"{docx.name}: the three sections are headings", all(_norm(h) in styled for h in heads),
                    ", ".join(h for h in heads if _norm(h) not in styled)))
        words = len(re.findall(r"\w+", text))
        out.append((f"{docx.name}: real text (>= 120 words)", words >= 120, f"{words} words"))
        out.append((f"{docx.name}: no Markdown left (#, **, ```)", not _RESIDUE.search(text),
                    (_RESIDUE.search(text).group(0) if _RESIDUE.search(text) else "")[:60]))
    except Exception as e:  # noqa: BLE001
        out.append((f"{docx.name} opens", False, f"{type(e).__name__}: {e}"[:160]))
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(pdf))
        text = "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
        out.append((f"{pdf.name} opens", len(doc) >= 1, f"{len(doc)} page(s)"))
        flat = _norm(text)
        out.append((f"{pdf.name}: the three section titles are in it", all(_norm(h) in flat for h in heads),
                    ", ".join(h for h in heads if _norm(h) not in flat)))
        out.append((f"{pdf.name}: no Markdown left (#, **, ```)", not _RESIDUE.search(text),
                    (_RESIDUE.search(text).group(0) if _RESIDUE.search(text) else "")[:60]))
    except Exception as e:  # noqa: BLE001
        out.append((f"{pdf.name} opens", False, f"{type(e).__name__}: {e}"[:160]))
    return out


# ------------------------------------------------------------------------------------------------ 5. connection drop
_PLANETS = {"tr": ("Merkür", "Venüs", "Mars", "Jüpiter"), "en": ("Mercury", "Venus", "Mars", "Jupiter")}


def check_net(ws: Path, run: dict) -> list[Check]:
    names = _PLANETS[run.get("lang") or "tr"]
    out: list[Check] = []
    for i, planet in enumerate(names):
        f = ws / "notes" / f"{'abcd'[i]}.md"
        text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
        sentences = len(re.findall(r"[.!?](\s|$)", text))
        out.append((f"notes/{f.name} about {planet} (>= 3 sentences)", planet.lower() in text.lower() and sentences >= 3,
                    f"{sentences} sentences" if text else "missing"))
    cut = run.get("net_cut") or {}
    out.append(("the connection was really cut mid-task", bool(cut.get("cut_at")), cut.get("note", "")))
    steps = [x for x in run.get("trace") or [] if x.get("type") == "step"]
    waited = any(x.get("kind") == "retry" for x in steps)
    out.append(("the app noticed the drop and waited / continued", waited, ""))
    writes: dict[str, int] = {}
    for x in steps:
        if x.get("tool") == "write_file" and x.get("status") == "done":
            p = str((x.get("args") or {}).get("path") or "").replace("\\", "/")
            writes[p] = writes.get(p, 0) + 1
    again = [p for p, n in writes.items() if n > 1]
    out.append(("no finished file written again after the drop", not again, ", ".join(again)))
    out.append(("same model kept (no switch)", not any(x.get("kind") == "fallback" for x in steps), ""))
    out.append(("task ended ok", run.get("status") == "ok", str(run.get("status"))))
    return out


# ------------------------------------------------------------------------------------------------ shared helpers
def _steps(run: dict) -> list[dict]:
    return [x for x in run.get("trace") or [] if x.get("type") == "step"]


def _skills_used(run: dict) -> set[str]:
    out = set()
    for x in _steps(run):
        if (x.get("tool") == "use_skill" or x.get("kind") == "skill") and x.get("status") == "done":
            # the step's title is the skill's name (the name in the tag body is not kept in args)
            a = x.get("args") or {}
            name = str(a.get("name") or a.get("skill") or x.get("title") or "")
            out.add(name.strip().lstrip("/").split(" ")[0].lower())
    return {s for s in out if s}


INFO = "info: "  # a check row whose name starts with this is reported, never scored


def _skill_check(run: dict, *names: str) -> Check:
    """Which skill the model loaded. Reported, not scored: the app leaves the choice to the model on purpose, and
    nemotron-3-ultra did every skill task right without loading one (all content checks passed)."""
    used = _skills_used(run)
    return (f"{INFO}loaded the {' / '.join(names)} skill (use_skill in the trace)", bool(used & set(names)),
            ", ".join(sorted(used)) or "no skill loaded")


def _chunks(text: str) -> list[str]:
    """Lines, blank-line paragraphs and Markdown sections: a finding is one table row, one bullet, one paragraph or
    one heading with its body ("### 1. Kritik — SQL Enjeksiyonu" over "Konum: app/db.py:6" was scored as unrated)."""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections = [s for s in re.split(r"\n(?=#{1,6}\s)", text) if s.strip()]
    return [ln for ln in text.splitlines() if ln.strip()] + paras + sections


# ------------------------------------------------------------------------------------------------ 6. web research
_URL = re.compile(r"https?://[^\s<>()\[\]\"'`|]+")
_FACTS = [  # (name, pattern on lowercased text) - stable facts that need several sources
    ("Python 3.13.0 release date (2024-10-07)",
     r"2024-10-07|\b7\.? (ekim|october),? 2024|october 7,? 2024|\b0?7[./]10[./]2024"),
    ("PEP that makes the GIL optional (PEP 703)", r"pep[\s\-]*0?703"),
    ("Rust 1.0 release date (2015-05-15)", r"2015-05-15|\b15\.? (mayıs|may),? 2015|may 15,? 2015|\b15[./]0?5[./]2015"),
    ("SQLite's licence (public domain)", r"public[\s-]domain|kamu mal|kamuya açık"),
]


def _url_alive(url: str) -> tuple[bool, str]:
    import httpx
    try:
        r = httpx.get(url, follow_redirects=True, timeout=20,
                      headers={"User-Agent": "Mozilla/5.0 (AI IQ 300 eval link check)"})
        # 401/403/429: the page exists and refuses robots; only a missing page or a dead site is an invented source
        return r.status_code < 400 or r.status_code in (401, 403, 429), str(r.status_code)
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def check_research(ws: Path, run: dict) -> list[Check]:
    f = ws / "research" / "report.md"
    text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
    out: list[Check] = [("research/report.md exists", bool(text), "")]
    low = text.lower()
    chunks = _chunks(text)
    cited = 0
    for name, pat in _FACTS:
        hit = re.search(pat, low)
        out.append((name, bool(hit), ""))
        if hit and any(re.search(pat, c.lower()) and (_URL.search(c) or re.search(r"\[\d+\]", c)) for c in chunks):
            cited += 1
    days = [int(n.replace(".", "").replace(",", "")) for n in re.findall(r"\b\d{1,2}[.,]?\d{3}\b", text)]
    out.append(("days between the two releases computed (3433)", any(3432 <= d <= 3434 for d in days), ""))
    out.append(("every fact has its source next to it", cited == len(_FACTS), f"{cited}/{len(_FACTS)}"))
    urls = list(dict.fromkeys(u.rstrip(".,;:") for u in _URL.findall(text)))
    domains = {re.sub(r"^www\.", "", u.split("/")[2].lower()) for u in urls}
    out.append((">= 4 sources from >= 3 sites", len(urls) >= 4 and len(domains) >= 3, f"{len(urls)} URLs, {len(domains)} sites"))
    dead = []
    for u in urls[:8]:
        ok, why = _url_alive(u)
        if not ok:
            dead.append(f"{u} ({why})")
    out.append(("the cited pages really exist (no 404 / dead site)", bool(urls) and not dead, "; ".join(dead)[:200]))
    web = [x for x in _steps(run) if x.get("tool") in ("research", "web_search", "fetch_url", "browser_open", "browser_navigate")]
    out.append(("searched the web (>= 2 web tool calls)", len(web) >= 2, f"{len(web)} calls"))
    return out


# ------------------------------------------------------------------------------------------------ 7. skill: code review
_FINDINGS = [  # (name, file, words that name the problem)
    ("SQL injection in db.py", "db.py", r"sql[\s-]*(injection|enjeksiyon)|parametri[sz]|parameteri[sz]|placeholder|\?\s*yer"),
    ("path traversal in files.py", "files.py", r"travers|\.\./|dizin (geçiş|dışı)|path (injection|manipulation)|yol (geçiş|enjeksiyon|manipülasyon)"),
    ("hard-coded secret in config.py", "config.py", r"secret|gizli|hard[\s-]?cod|sabit|kodda|anahtar|ortam değişken|environment"),
    ("off-by-one page start in pages.py", "pages.py", r"off[\s-]*by[\s-]*one|page\s*-\s*1|\(page-1\)|bir (eksik|fazla)|ilk sayfa|first page|skip|atla"),
]


def check_review(ws: Path, run: dict) -> list[Check]:
    f = ws / "review.md"
    text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
    out: list[Check] = [("review.md exists", bool(text), "")]
    chunks = [c.lower() for c in _chunks(text)]
    for name, file, words in _FINDINGS:
        out.append((f"found: {name}", any(file in c and re.search(words, c) for c in chunks), ""))
    sev = any("db.py" in c and re.search(r"sql", c) and re.search(r"crit|kritik|high|yüksek|ciddi", c) for c in chunks)
    out.append(("SQL injection rated critical / high", sev, ""))
    seed = TASKS_DIR / "skill_review" / "seed" / "app"
    changed = [p.name for p in sorted(seed.glob("*.py")) if _sha(ws / "app" / p.name) != _sha(p)]
    out.append(("code left unchanged (review only)", not changed, ", ".join(changed)))
    out.append(_skill_check(run, "code-review"))
    return out


# ------------------------------------------------------------------------------------------------ 8. skill: flowchart
_MERMAID_JS = HERE.parent / "frontend" / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"
_PARSE = """async (t) => {
  mermaid.initialize({startOnLoad: false});
  try {
    const d = await mermaid.mermaidAPI.getDiagramFromText(t);
    if (!d.db.getVertices) return {type: d.type};
    let v = d.db.getVertices(); v = v instanceof Map ? [...v.values()] : Object.values(v);
    await mermaid.render('chk', t);
    return {type: d.type, nodes: v.map(n => [n.id, n.type, n.text || '']),
            edges: d.db.getEdges().map(e => [e.start, e.end, e.text || ''])};
  } catch (err) { return {error: String((err && err.message) || err).slice(0, 200)}; }
}"""


def _has_cycle(edges: list) -> bool:
    graph: dict[str, list[str]] = {}
    for a, b, _ in edges:
        graph.setdefault(a, []).append(b)
    state: dict[str, int] = {}

    def visit(n: str) -> bool:
        state[n] = 1
        for m in graph.get(n, []):
            if state.get(m) == 1 or (m not in state and visit(m)):
                return True
        state[n] = 2
        return False
    return any(n not in state and visit(n) for n in list(graph))


def check_flowchart(ws: Path, run: dict) -> list[Check]:
    f = ws / "diagrams" / "order.mmd"
    text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
    text = re.sub(r"^\s*```(?:mermaid)?\s*\n|\n\s*```\s*$", "", text.strip()) if text else ""
    out: list[Check] = [("diagrams/order.mmd exists", bool(text), "")]
    if not text:
        return out + [_skill_check(run, "flowchart")]
    if not _MERMAID_JS.is_file():
        return out + [("Mermaid parses it", False, "frontend/node_modules missing (npm install)"), _skill_check(run, "flowchart")]
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            page = b.new_page()
            page.set_content("<html><body></body></html>")
            page.add_script_tag(content=_MERMAID_JS.read_text(encoding="utf-8"))
            r = page.evaluate(_PARSE, text)
            b.close()
    except Exception as e:  # noqa: BLE001
        r = {"error": f"{type(e).__name__}: {e}"[:200]}
    out.append(("Mermaid parses and draws it", "error" not in r, r.get("error", "")))
    nodes, edges = r.get("nodes") or [], r.get("edges") or []
    out.append(("it is a flowchart", str(r.get("type", "")).startswith("flowchart"), str(r.get("type", ""))))
    out.append((">= 7 steps", len(nodes) >= 7, f"{len(nodes)} nodes"))
    out.append(("two decisions as diamonds", sum(n[1] == "diamond" for n in nodes) >= 2,
                f"{sum(n[1] == 'diamond' for n in nodes)} diamonds"))
    labels = [str(e[2]).lower() for e in edges]
    yes_no = sum(bool(re.search(r"^(evet|yes)\b", x)) for x in labels) >= 2 and sum(bool(re.search(r"^(hayır|no)\b", x)) for x in labels) >= 2
    out.append(("decision exits labelled yes / no", yes_no, ", ".join(x for x in labels if x)[:120]))
    out.append(("the restock loop goes back to the stock check (a cycle)", _has_cycle(edges), ""))
    out.append(_skill_check(run, "flowchart"))
    return out


# ------------------------------------------------------------------------------------------------ 9. skill: git
def _setup_git(ws: Path) -> None:
    (ws / ".env").write_text("DEBUG=1\nTOKEN=local-only-test-value\n", encoding="utf-8")
    (ws / "__pycache__").mkdir(exist_ok=True)
    (ws / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00eval cache\x00")


def _git(ws: Path, *a: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=off", *a], cwd=ws, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return r.returncode, (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def check_git(ws: Path, run: dict) -> list[Check]:
    out: list[Check] = [("a git repository", (ws / ".git").is_dir(), "")]
    if not (ws / ".git").is_dir():
        return out + [_skill_check(run, "git")]
    rc, branches = _git(ws, "branch", "--format=%(refname:short)")
    names = set(branches.split())
    out.append(("branches main and feature/login", {"main", "feature/login"} <= names, ", ".join(sorted(names))))
    rc, subjects = _git(ws, "log", "main", "--format=%s")
    out.append(("main has the commit 'İlk sürüm'", "İlk sürüm" in subjects.splitlines() or "Initial version" in subjects.splitlines(),
                subjects.replace("\n", " | ")[:120]))
    files = {}
    for b in ("main", "feature/login"):
        files[b] = set(_git(ws, "ls-tree", "-r", "--name-only", b)[1].splitlines())
    tracked = files["main"] | files["feature/login"]
    out.append((".env not committed", ".env" not in tracked, ""))
    out.append(("__pycache__ not committed", not any(p.startswith("__pycache__/") for p in tracked), ""))
    gi = _git(ws, "show", "main:.gitignore")[1]
    out.append((".gitignore on main ignores .env and __pycache__", ".env" in gi and "__pycache__" in gi, ""))
    login = _git(ws, "show", "feature/login:login.py")[1]
    out.append(("feature/login has login.py with login(user, password)",
                bool(re.search(r"def\s+login\s*\(\s*user\s*,\s*password", login)), ""))
    out.append(("main does not have login.py", "login.py" not in files["main"], ""))
    head = _git(ws, "rev-parse", "--abbrev-ref", "HEAD")[1]
    out.append(("back on main at the end", head == "main", head))
    dirty = [ln for ln in _git(ws, "status", "--porcelain")[1].splitlines() if ".session" not in ln]
    out.append(("nothing left uncommitted", not dirty, "; ".join(dirty)[:120]))
    out.append(_skill_check(run, "git"))
    return out


TASKS: list[Task] = [
    Task("web_app", {"tr": "Web uygulaması", "en": "Web app"},
         {"tr": "todo/ klasöründe küçük bir yapılacaklar web uygulaması yap: index.html, style.css ve app.js. "
                "Sayfada id=\"new-todo\" bir metin kutusu, id=\"add\" bir Ekle düğmesi ve id=\"list\" bir liste "
                "olsun. Ekle'ye basınca kutudaki metin listeye bir <li> olarak eklensin ve öğeler localStorage'da "
                "saklansın (sayfa yenilenince kalsın). Harici kütüphane kullanma. Bitince tarayıcıda test et.",
          "en": "Build a small to-do web app in the todo/ folder: index.html, style.css and app.js. The page has a "
                "text box with id=\"new-todo\", an Add button with id=\"add\" and a list with id=\"list\". Clicking Add "
                "puts the box's text into the list as an <li>, and the items are kept in localStorage (they stay "
                "after a reload). No external libraries. Test it in the browser when done."},
         check_web, tags=["web", "browser"]),
    Task("fix_python", {"tr": "Bozuk Python düzeltme", "en": "Fix broken Python"},
         {"tr": "stats.py bozuk ve test_stats.py testleri geçmiyor. stats.py'deki hataları bul ve düzelt (davranış "
                "dosyanın başındaki açıklamada yazıyor), sonra testleri çalıştırıp geçtiğini göster. test_stats.py'yi "
                "değiştirme.",
          "en": "stats.py is broken and the tests in test_stats.py fail. Find and fix the bugs in stats.py (the "
                "behaviour is described at the top of the file), then run the tests and show they pass. Do not change "
                "test_stats.py."},
         check_fix, seed="fix_python/seed", tags=["debug", "python"]),
    Task("multi_file", {"tr": "5 dosyalı değişiklik", "en": "Five-file change"},
         {"tr": "Bu projede Product sınıfının price alanını unit_price olarak yeniden adlandır; tüm modüller "
                "(models, inventory, pricing, report, cli) yeni adı kullansın. Inventory'ye low_stock(limit=5) ekle: "
                "qty < limit olan ürünleri döndürsün. report.render çıktısının sonuna düşük stoklu ürünleri gösteren "
                "bir 'Low stock' bölümü ekle. README.md'yi güncelle. Sonra `python -m shop.cli` ile çalıştığını göster.",
          "en": "In this project rename the Product class's price field to unit_price; every module (models, "
                "inventory, pricing, report, cli) must use the new name. Add low_stock(limit=5) to Inventory: it returns "
                "the products with qty < limit. Add a 'Low stock' section listing them at the end of report.render's "
                "output. Update README.md. Then show it works with `python -m shop.cli`."},
         check_multi, seed="multi_file/seed", tags=["refactor", "python"]),
    Task("documents", {"tr": "Word + PDF üretimi", "en": "Word + PDF"},
         {"tr": "Python programlama dilinin üç güçlü yanını anlatan kısa bir rapor yaz. Başlık \"Python Raporu\"; "
                "bölümler sırasıyla \"Giriş\", \"Güçlü Yanlar\" ve \"Sonuç\", toplam en az 150 kelime. Raporu hem Word "
                "(docs/rapor.docx) hem PDF (docs/rapor.pdf) olarak kaydet, sonra iki belgeyi de açıp içeriğini doğrula.",
          "en": "Write a short report on three strengths of the Python programming language. Title \"Python "
                "Report\"; sections in order \"Introduction\", \"Strengths\" and \"Conclusion\", at least 150 words in "
                "all. Save it as Word (docs/report.docx) and PDF (docs/report.pdf), then open both documents and verify "
                "their content."},
         check_docs, tags=["documents"]),
    Task("net_drop", {"tr": "Bağlantı kopması", "en": "Connection drop"},
         {"tr": "notes/ klasörüne dört dosya yaz, her biri bir gezegen hakkında en az beş cümle: a.md Merkür, b.md "
                "Venüs, c.md Mars, d.md Jüpiter. Dosyaları sırayla, her birini ayrı yaz.",
          "en": "Write four files in the notes/ folder, each at least five sentences about one planet: a.md "
                "Mercury, b.md Venus, c.md Mars, d.md Jupiter. Write them in order, one at a time."},
         check_net, net_drop=True, tags=["network", "continuity"]),
    Task("research", {"tr": "Karmaşık web araştırması", "en": "Complex web research"},
         {"tr": "Web'de araştır ve research/report.md dosyasına bir araştırma notu yaz. Cevaplanacaklar: (1) Python 3.13.0 "
                "hangi tarihte yayınlandı? (2) CPython'da GIL'i isteğe bağlı yapan PEP'in numarası kaç? (3) Rust 1.0 hangi "
                "tarihte yayınlandı? (4) SQLite hangi lisansla dağıtılıyor? (5) Rust 1.0 ile Python 3.13.0 arasında kaç gün "
                "var? Her bilginin aynı satırında kaynağının tam URL'si olsun; en az 4 kaynak ve en az 3 farklı site kullan. "
                "Tarihleri YYYY-AA-GG biçiminde yaz. Sonda bir Kaynaklar bölümü olsun.",
          "en": "Research on the web and write a research note in research/report.md. Answer: (1) On what date was Python "
                "3.13.0 released? (2) What is the number of the PEP that makes the GIL optional in CPython? (3) On what "
                "date was Rust 1.0 released? (4) Under what licence is SQLite distributed? (5) How many days are there "
                "between Rust 1.0 and Python 3.13.0? Put each fact's source as a full URL on the same line; use at least 4 "
                "sources from at least 3 different sites. Write dates as YYYY-MM-DD. End with a Sources section."},
         check_research, tags=["web", "research"]),
    Task("skill_review", {"tr": "Yetenek: kod incelemesi", "en": "Skill: code review"},
         {"tr": "app/ klasöründeki Python kodunu hata ve güvenlik açısından incele. Bulduğun her sorunu ciddiyet sırasına "
                "göre review.md dosyasına yaz: dosya:satır, sorun, nasıl bir hataya yol açtığı ve düzeltme önerisi. Kodu "
                "değiştirme, yalnızca raporla.",
          "en": "Review the Python code in the app/ folder for bugs and security problems. Write every problem you find to "
                "review.md sorted by severity: file:line, the problem, what failure it causes and the suggested fix. Do not "
                "change the code, only report."},
         check_review, seed="skill_review/seed", tags=["skill", "review", "security"]),
    Task("skill_flowchart", {"tr": "Yetenek: akış şeması", "en": "Skill: flowchart"},
         {"tr": "Şu sipariş sürecinin akış şemasını Mermaid ile çiz ve diagrams/order.mmd dosyasına da kaydet: Sipariş "
                "gelir. Stok var mı? Yoksa tedarikçiye sipariş verilir, stok gelene kadar beklenir ve yeniden stok "
                "kontrolüne dönülür. Stok varsa ödeme alınır. Ödeme başarılı mı? Başarısızsa müşteriye bildirilir ve süreç "
                "biter. Başarılıysa sipariş kargolanır, müşteriye kargo bilgisi gönderilir ve süreç biter. Karar "
                "çıkışlarını Evet / Hayır diye etiketle.",
          "en": "Draw a flowchart of this order process with Mermaid and also save it to diagrams/order.mmd: An order "
                "comes in. Is it in stock? If not, it is ordered from the supplier, we wait until the stock arrives and go "
                "back to the stock check. If it is in stock, payment is taken. Did the payment succeed? If not, the "
                "customer is told and the process ends. If it did, the order is shipped, the customer gets the tracking "
                "info and the process ends. Label the decision exits Yes / No."},
         check_flowchart, tags=["skill", "diagram"]),
    Task("skill_git", {"tr": "Yetenek: git", "en": "Skill: git"},
         {"tr": "Bu klasörde bir git deposu başlat, ana dalın adı main olsun. .env dosyası ve __pycache__ klasörü depoya "
                "girmesin diye bir .gitignore ekle. Tüm dosyaları 'İlk sürüm' mesajıyla commit et. Sonra feature/login "
                "adında bir dal aç, içinde login(user, password) fonksiyonu olan bir login.py ekle ve bu dalda commit et. "
                "En sonda main dalına geri dön; commit edilmemiş bir şey kalmasın.",
          "en": "Start a git repository in this folder with main as the main branch's name. Add a .gitignore so the .env "
                "file and the __pycache__ folder stay out of the repository. Commit all files with the message 'Initial "
                "version'. Then create a branch named feature/login, add a login.py with a login(user, password) "
                "function and commit it on that branch. At the end switch back to main; leave nothing uncommitted."},
         check_git, seed="skill_git/seed", setup=_setup_git, tags=["skill", "git"]),
]

BY_ID = {t.id: t for t in TASKS}


def to_json(t: Task) -> dict:
    return {"id": t.id, "title": t.title, "seed": t.seed, "net_drop": t.net_drop, "timeout_s": t.timeout_s, "tags": t.tags}


if __name__ == "__main__":
    print(json.dumps([to_json(t) for t in TASKS], ensure_ascii=False, indent=2))
