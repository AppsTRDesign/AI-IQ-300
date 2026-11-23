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
                n0 = page.locator("#list li").count()
                page.fill("#new-todo", "Süt al 42")
                page.click("#add")
                page.wait_for_timeout(400)
                added = page.locator("#list li").count() == n0 + 1 and "Süt al 42" in page.inner_text("#list")
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
]

BY_ID = {t.id: t for t in TASKS}


def to_json(t: Task) -> dict:
    return {"id": t.id, "title": t.title, "seed": t.seed, "net_drop": t.net_drop, "timeout_s": t.timeout_s, "tags": t.tags}


if __name__ == "__main__":
    print(json.dumps([to_json(t) for t in TASKS], ensure_ascii=False, indent=2))
