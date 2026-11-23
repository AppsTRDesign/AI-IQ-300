r"""Agent Evaluation: the same tasks for several models, scored from what really exists afterwards.

    .venv\Scripts\python.exe eval\run_eval.py --models mock                       (self-test, no real model)
    .venv\Scripts\python.exe eval\run_eval.py --models "evren:auto,nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
    .venv\Scripts\python.exe eval\run_eval.py --models evren:auto --tasks fix_python,documents --lang en

Each model runs each task in a fresh chat of its own isolated app instance (a temporary data folder; your data/
folder is only read: its settings.json and secrets.json are copied into the temporary folder so your providers work,
and the copy is deleted at the end). The report (Markdown + JSON) and each task's trace go to eval/reports/<time>/.

A task that does not finish in --timeout seconds is stopped by the runner (an evaluation limit; the app itself
never stops a task for failures or budgets).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import charts  # noqa: E402
from tasks import BY_ID, INFO, TASKS, Task  # noqa: E402

PY = sys.executable
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

T = {
    "tr": {"title": "AI IQ 300 — Ajan Değerlendirmesi", "model": "Model", "task": "Görev", "score": "Puan",
           "status": "Durum", "time": "Süre", "turns": "Tur", "tokens": "Çıktı token", "tools": "Araç (hata)",
           "retries": "Yeniden deneme", "switches": "Model değişimi", "summary": "Özet", "failed": "Geçmeyen kontroller",
           "errors": "Hata türleri (araca göre)", "none": "yok", "passed": "tam geçen görev", "version": "Sürüm",
           "date": "Tarih", "lang": "Dil", "checks": "Kontroller", "note": "Görev puanı = geçen kontrol / görevin kontrolleri. "
           "Kontroller gerçek çıktıya bakar: diskteki dosyalar, çalışan testler, gerçek tarayıcı, belge okuyucular, iz kaydı.",
           "by_task": "Görev başına (eşit ağırlık)", "by_check": "Kontrol başına (tek havuz)",
           "scores_note": "Üç ayrı ölçü: görev başına = görev puanlarının ortalaması (her görev eşit sayılır); kontrol "
           "başına = tüm kontroller tek havuzda (çok kontrollü görev daha ağır basar); tam geçen = her kontrolü geçen "
           "görevlerin oranı, işin gerçekten bitirilme sıklığı.",
           "where": "Süre nereye gitti", "where_note": "Bekleme = her isteğin ilk token'ına kadar (sağlayıcı kuyruğu + "
           "istemin okunması); üretim = ilk token'dan sonra akış; uygulama = geri kalan, uygulamanın kendi işi. "
           "1K başına bekleme = 1.000 istem token'ı başına bekleme saniyesi (medyan): kısa istemlerde yüksekse "
           "gecikme sağlayıcıdan gelir.",
           "wait": "Bekleme", "gen": "Üretim", "tools_t": "Araçlar", "retry_t": "Hata sonrası bekleme",
           "app_t": "Uygulama", "max_wait": "En uzun bekleme", "per_k": "1K istem başına bekleme",
           "chart_scores": "Üç puan, modele göre", "chart_heat": "Görev × model: geçen kontroller",
           "chart_heat_note": "Hücre = geçen / tüm kontroller; koyu mavi = daha çok geçen, ✓ = tam geçti",
           "table": "Tüm sonuçlar (tablo)", "charts": "Grafikler", "html": "Etkileşimli rapor: report.html",
           "verdict": "Değerlendirme",
           "verdict_note": "Ölçüt başarı oranı ve uygulama hatası olmamasıdır. Süre çoğunlukla modele ve sağlayıcıya "
           "bağlıdır: büyük bir modelin paylaşılan ücretsiz kuyruğu her istekte onlarca saniye bekletebilir; bu "
           "uygulamanın hatası değildir ve puanı etkilemez.",
           "verdict_line": "{model}: tam geçen {full} ({fp}/{n}), kontrol başına {bc}. Süre {mins:.1f} dk: %{prov} "
           "sağlayıcı beklemesi (ilk token + hız sınırı), %{gen} modelin yazması, %{tools} araçlar, %{app} uygulama. "
           "{apperr}",
           "app_ok": "Uygulama hatası yok: her görev uygulama tarafında sorunsuz bitti.",
           "app_bad": "Uygulama tarafında sorunlu biten görev: {tasks}.",
           "slow_provider": "Yavaşlığın kaynağı sağlayıcı: istek başına ilk token beklemesi ortalama {avg:.0f} sn."},
    "en": {"title": "AI IQ 300 — Agent Evaluation", "model": "Model", "task": "Task", "score": "Score",
           "status": "Status", "time": "Time", "turns": "Turns", "tokens": "Output tokens", "tools": "Tools (errors)",
           "retries": "Retries", "switches": "Model switches", "summary": "Summary", "failed": "Failed checks",
           "errors": "Error kinds (by tool)", "none": "none", "passed": "tasks fully passed", "version": "Version",
           "date": "Date", "lang": "Language", "checks": "Checks", "note": "Task score = passed checks / the task's checks. "
           "Checks look at real output: files on disk, tests that run, a real browser, document readers, the trace.",
           "by_task": "Per task (equal weight)", "by_check": "Per check (pooled)",
           "scores_note": "Three separate measures: per task = mean of the task scores (each task counts the same); "
           "per check = all checks in one pool (a task with more checks weighs more); fully passed = share of tasks "
           "with every check passed, how often the whole job was really done.",
           "where": "Where the time went", "where_note": "Wait = until each request's first token (provider queue + "
           "reading the prompt); generation = streaming after the first token; app = the rest, the app's own work. "
           "Wait per 1K = wait seconds per 1,000 prompt tokens (median): high with short prompts means the delay "
           "comes from the provider.",
           "wait": "Wait", "gen": "Generation", "tools_t": "Tools", "retry_t": "Wait after errors", "app_t": "App",
           "max_wait": "Longest wait", "per_k": "Wait per 1K prompt",
           "chart_scores": "Three scores by model", "chart_heat": "Task × model: checks passed",
           "chart_heat_note": "Cell = passed / all checks; darker blue = more passed, ✓ = fully passed",
           "table": "All results (table)", "charts": "Charts", "html": "Interactive report: report.html",
           "verdict": "Assessment",
           "verdict_note": "What counts is the success rate and no app errors. The time mostly depends on the model and "
           "its provider: a big model's shared free queue can hold every request for tens of seconds; that is not an "
           "app error and does not change the score.",
           "verdict_line": "{model}: fully passed {full} ({fp}/{n}), per check {bc}. Time {mins:.1f} min: {prov}% "
           "provider wait (first token + rate limits), {gen}% the model writing, {tools}% tools, {app}% the app. "
           "{apperr}",
           "app_ok": "No app errors: every task finished cleanly on the app's side.",
           "app_bad": "Tasks that ended with a problem on the app's side: {tasks}.",
           "slow_provider": "The slowness comes from the provider: the first token took {avg:.0f} s per request on average."},
}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Instance:
    """One isolated app (temporary data folder) plus the connection-cut proxy (and the scripted model for mock)."""

    def __init__(self, args):
        self.args = args
        self.sp = Path(tempfile.mkdtemp(prefix="aiiq-eval-"))
        self.data = self.sp / "appdata"
        self.port = args.port
        self.app = f"http://127.0.0.1:{self.port}"
        self.proxy = f"http://127.0.0.1:{self.port + 1}"
        self.sim = self.sp / "net_down"
        self.procs: list[subprocess.Popen] = []
        self.mock = args.models.strip() == "mock"

    def prepare(self) -> None:
        self.data.mkdir(parents=True)
        src = Path(self.args.data)
        if self.mock:
            settings = {"providers": {"mock": {"name": "Mock solver", "kind": "openai", "enabled": True,
                                               "base_url": f"http://127.0.0.1:{self.port + 2}/v1"}}}
            (self.data / "secrets.json").write_text(json.dumps({"mock_api_key": "mock"}), encoding="utf-8")
        else:
            try:
                settings = json.loads((src / "settings.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sys.exit(f"cannot read {src / 'settings.json'}: pass --data <your AI IQ 300 data folder>")
            if (src / "secrets.json").is_file():
                shutil.copy2(src / "secrets.json", self.data / "secrets.json")
        settings.update({"language": self.args.lang, "permission_mode": "full"})
        settings.pop("mcp_servers", None)  # no user MCP servers in an evaluation
        (self.data / "settings.json").write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")

    def start(self) -> None:
        env = {**os.environ, "AIIQ_DATA": str(self.data), "PYTHONIOENCODING": "utf-8", "AIIQ_NET_SIM": str(self.sim)}
        logf = open(self.sp / "app.log", "w", encoding="utf-8")
        self.procs.append(subprocess.Popen([PY, str(HERE / "net_proxy.py"), str(self.port + 1), str(self.sim)], env=env))
        if self.mock:
            self.procs.append(subprocess.Popen([PY, str(HERE / "mock_solver.py"), str(self.port + 2)], env=env))
        self.procs.append(subprocess.Popen([PY, str(ROOT / "launcher.py"), "--port", str(self.port), "--no-browser"],
                                           env=env, cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT))
        for _ in range(150):
            try:
                if httpx.get(f"{self.app}/api/health", timeout=1).status_code == 200 and \
                        httpx.get(f"{self.proxy}/_ctl/state", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.4)
        sys.exit(f"the app did not start; see {self.sp / 'app.log'}")

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        time.sleep(0.5)
        if self.args.keep:
            log("kept:", self.sp)
        else:
            shutil.rmtree(self.sp, ignore_errors=True)


async def _settings(c: httpx.AsyncClient, inst: Instance) -> dict:
    return (await c.get(f"{inst.app}/api/settings")).json()


async def run_task(c: httpx.AsyncClient, inst: Instance, model: str, task: Task) -> dict:
    lang = inst.args.lang
    sid = (await c.post(f"{inst.app}/api/sessions", json={"title": f"eval {task.id}"})).json()["id"]
    ws = inst.data / "chat" / sid
    ws.mkdir(parents=True, exist_ok=True)
    if task.seed:
        shutil.copytree(HERE / "tasks" / task.seed, ws, dirs_exist_ok=True)
    if task.setup:
        task.setup(ws)
    pid = model.partition(":")[0]
    restore = None
    if task.net_drop:  # this task's provider requests go through the proxy that can cut them
        cfg = (await _settings(c, inst))["providers"].get(pid) or {}
        base = (cfg.get("base_url") or "").rstrip("/")
        if base:
            await c.post(f"{inst.proxy}/_ctl/map", json={pid: base})
            restore = base
            await c.patch(f"{inst.app}/api/settings", json={"providers": {pid: {"base_url": f"{inst.proxy}/p/{pid}"}}})
    t0 = time.time()
    r = (await c.post(f"{inst.app}/api/sessions/{sid}/chat", json={"text": task.prompt[lang], "model": model,
                                                                  "permission_mode": "full"})).json()
    run_id = r.get("run_id") or ""
    timeout = inst.args.timeout or task.timeout_s
    net = {"cut_at": None, "note": ""}
    timed_out = False
    while True:
        await asyncio.sleep(0.5)
        if not (await c.get(f"{inst.app}/api/sessions/{sid}/active")).json():
            break
        if task.net_drop and not net["cut_at"]:
            st = (await c.get(f"{inst.proxy}/_ctl/state")).json()
            first = (ws / "notes" / "a.md").exists()
            second = (ws / "notes" / "b.md").exists()
            waited = time.time() - t0
            if st["open"] and st["bytes"] > 200 and (second or (first and waited > 30) or waited > 240):
                await c.post(f"{inst.proxy}/_ctl/cut", json={"seconds": 8})
                net = {"cut_at": round(time.time() - t0, 1), "note": f"cut at {time.time() - t0:.0f}s, "
                       f"{'b.md' if second else 'a.md' if first else 'no file'} on disk, {st['bytes']} bytes in the stream"}
                log("   connection cut:", net["note"])
        if time.time() - t0 > timeout:
            timed_out = True
            await c.post(f"{inst.app}/api/runs/{run_id}/cancel")
            for _ in range(60):
                await asyncio.sleep(0.5)
                if not (await c.get(f"{inst.app}/api/sessions/{sid}/active")).json():
                    break
            break
    if restore:
        await c.patch(f"{inst.app}/api/settings", json={"providers": {pid: {"base_url": restore}}})
    msgs = (await c.get(f"{inst.app}/api/sessions/{sid}/messages")).json()
    last = next((m for m in reversed(msgs if isinstance(msgs, list) else msgs.get("messages", [])) if m["role"] == "assistant"), {})
    meta = last.get("meta") or {}
    tr = await c.get(f"{inst.app}/api/sessions/{sid}/traces/{run_id}")
    trace = tr.json() if tr.status_code == 200 else {"summary": {}, "events": []}
    info = {"status": "timeout" if timed_out else meta.get("status"), "lang": lang, "trace": trace["events"], "net_cut": net}
    allc = await asyncio.to_thread(task.check, ws, info)
    notes = [(n[len(INFO):], ok, i) for n, ok, i in allc if n.startswith(INFO)]
    checks = [c for c in allc if not c[0].startswith(INFO)]
    passed = sum(ok for _, ok, _ in checks)
    s = trace.get("summary") or {}
    return {"model": model, "task": task.id, "title": task.title[lang], "status": info["status"],
            "seconds": round(time.time() - t0, 1), "score": round(passed / max(1, len(checks)), 3),
            "passed": passed, "total": len(checks), "full_pass": passed == len(checks),
            "checks": [{"name": n, "ok": ok, "info": i} for n, ok, i in checks],
            "notes": [{"name": n, "ok": ok, "info": i} for n, ok, i in notes],
            "turns": s.get("turns"), "out_tokens": s.get("out_tokens"), "tool_calls": s.get("tool_calls"),
            "tool_errors": s.get("tool_errors"), "errors_by_tool": s.get("errors_by_tool") or {},
            "retries": s.get("retries"), "fallbacks": s.get("fallbacks"), "debug_rounds": s.get("debug_rounds"),
            "time_split": {k: s.get(k) for k in ("wait_s", "gen_s", "tools_s", "retry_s", "app_s", "max_wait_s",
                                                 "wait_per_1k")},
            "answer": (last.get("content") or "")[:600], "error": meta.get("error") or "", "run_id": run_id,
            "net_cut": net if task.net_drop else None, "_trace": trace["events"]}


def scores(rs: list[dict]) -> dict:
    """Three different measures, all reported: they answer different questions and must not be mixed up.
    by_task         mean of each task's own pass share (every task weighs the same, however many checks it has)
    by_check        all checks pooled (a task with more checks weighs more)
    full_pass_rate  share of tasks with every check passed: how often the whole job was really done"""
    n = max(1, len(rs))
    checks = sum(r["total"] for r in rs)
    passed = sum(r["passed"] for r in rs)
    full = sum(bool(r["full_pass"]) for r in rs)
    return {"by_task": round(sum(r["score"] for r in rs) / n, 4), "by_check": round(passed / max(1, checks), 4),
            "full_pass_rate": round(full / n, 4), "checks_passed": passed, "checks": checks, "full_passed": full,
            "tasks": len(rs)}


def verdict(results: list[dict], t: dict) -> list[str]:
    """One line per model: the success rate first, then where the time went (provider / model / tools / app) and
    whether the app itself had a problem. A slow provider queue is named as such, apart from the score."""
    out = []
    for m in dict.fromkeys(r["model"] for r in results):
        rs = [r for r in results if r["model"] == m]
        s = scores(rs)
        tot = sum(r["seconds"] or 0 for r in rs) or 1
        part = lambda k: sum((r.get("time_split") or {}).get(k) or 0 for r in rs)  # noqa: E731
        pct = lambda v: round(100 * v / tot)  # noqa: E731
        bad = [r["task"] for r in rs if r["status"] not in ("ok",) or r.get("error")]
        tr = t is T["tr"]  # Turkish writes the percent sign first (%100)
        full = f"%{round(s['full_pass_rate'] * 100)}" if tr else f"{s['full_pass_rate']:.0%}"
        bc = f"%{s['by_check'] * 100:.1f}".replace(".", ",") if tr else f"{s['by_check']:.1%}"
        line = t["verdict_line"].format(
            model=m, full=full, fp=s["full_passed"], n=s["tasks"], bc=bc,
            mins=tot / 60, prov=pct(part("wait_s") + part("retry_s")), gen=pct(part("gen_s")), tools=pct(part("tools_s")),
            app=pct(part("app_s")), apperr=t["app_bad"].format(tasks=", ".join(bad)) if bad else t["app_ok"])
        turns = sum(r["turns"] or 0 for r in rs)
        if turns and part("wait_s") / turns > 10:
            line += " " + t["slow_provider"].format(avg=part("wait_s") / turns)
        out.append(line)
    return out


def report(results: list[dict], out: Path, lang: str, version: str) -> Path:
    t = T[lang]
    out.mkdir(parents=True, exist_ok=True)
    (out / "traces").mkdir(exist_ok=True)
    for r in results:
        name = f"{r['model'].replace(':', '_').replace('/', '_')}__{r['task']}.jsonl"
        events = r.pop("_trace", None)
        if events is None and r.get("_from"):  # a merged report: the trace file of the run it came from
            src = Path(r.pop("_from")) / (r.get("trace_file") or "")
            events = [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x.strip()] if src.is_file() else []
        (out / "traces" / name).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in events or []) + "\n",
                                           encoding="utf-8")
        r["trace_file"] = f"traces/{name}"
    data = {"version": version, "date": time.strftime("%Y-%m-%d %H:%M"), "lang": lang,
            "scores": {m: scores([r for r in results if r["model"] == m]) for m in dict.fromkeys(r["model"] for r in results)},
            "verdict": verdict(results, t), "results": results}
    (out / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# {t['title']}", "", f"{t['version']}: {version} · {t['date']}: {data['date']} · {t['lang']}: {lang}", "",
          f"_{t['note']}_", "", f"## {t['summary']}", "",
          f"| {t['model']} | {t['by_task']} | {t['by_check']} | {t['passed']} | {t['time']} | {t['tokens']} | {t['tools']} |",
          "|---|---|---|---|---|---|---|"]
    models = list(dict.fromkeys(r["model"] for r in results))
    for m in models:
        s = scores([r for r in results if r["model"] == m])
        rs = [r for r in results if r["model"] == m]
        md.append(f"| `{m}` | **{s['by_task']:.1%}** | {s['by_check']:.1%} ({s['checks_passed']}/{s['checks']}) | "
                  f"{s['full_pass_rate']:.0%} ({s['full_passed']}/{s['tasks']}) | "
                  f"{sum(r['seconds'] for r in rs) / 60:.1f} min | {sum(r['out_tokens'] or 0 for r in rs):,} | "
                  f"{sum(r['tool_calls'] or 0 for r in rs)} ({sum(r['tool_errors'] or 0 for r in rs)}) |")
    md += ["", f"## {t['verdict']}", "", f"_{t['verdict_note']}_", ""] + [f"- {x}" for x in data["verdict"]]
    try:
        files = charts.write(out, data, t)
        md += ["", f"_{t['scores_note']}_", "", f"## {t['charts']}", "", f"{t['html']}", "",
               f"![{t['chart_scores']}]({files['scores']})", "", f"![{t['chart_heat']}]({files['heatmap']})", "",
               f"![{t['where']}]({files['time']})"]
    except Exception as e:  # noqa: BLE001 - a chart problem never loses the report
        log("charts not drawn:", f"{type(e).__name__}: {e}")
        md += ["", f"_{t['scores_note']}_"]
    md += ["", f"## {t['where']}", "", f"_{t['where_note']}_", "",
           f"| {t['model']} | {t['task']} | {t['wait']} | {t['gen']} | {t['tools_t']} | {t['retry_t']} | {t['app_t']} | "
           f"{t['max_wait']} | {t['per_k']} |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        x = r.get("time_split") or {}
        f = lambda k: f"{x[k]:.0f} s" if isinstance(x.get(k), (int, float)) else "—"  # noqa: E731
        per_k = f"{x['wait_per_1k']:.2f} s" if x.get("wait_per_1k") is not None else "—"
        md.append(f"| `{r['model']}` | {r['title']} | {f('wait_s')} | {f('gen_s')} | {f('tools_s')} | {f('retry_s')} | "
                  f"{f('app_s')} | {f('max_wait_s')} | {per_k} |")
    md += ["", f"| {t['model']} | {t['task']} | {t['score']} | {t['status']} | {t['time']} | {t['turns']} | "
               f"{t['tokens']} | {t['tools']} | {t['retries']} | {t['switches']} |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| `{r['model']}` | {r['title']} | {r['passed']}/{r['total']} | {r['status']} | {r['seconds']:.0f} s | "
                  f"{r['turns'] or 0} | {r['out_tokens'] or 0:,} | {r['tool_calls'] or 0} ({r['tool_errors'] or 0}) | "
                  f"{r['retries'] or 0} | {r['fallbacks'] or 0} |")
    fails = [(r, c) for r in results for c in r["checks"] if not c["ok"]]
    md += ["", f"## {t['failed']}", ""]
    md += [f"- `{r['model']}` · {r['title']}: {c['name']}" + (f" — {c['info']}" if c["info"] else "") for r, c in fails] or [f"- {t['none']}"]
    errs: dict[str, int] = {}
    for r in results:
        for k, v in (r["errors_by_tool"] or {}).items():
            errs[k] = errs.get(k, 0) + v
    md += ["", f"## {t['errors']}", ""]
    md += [f"- `{k}`: {v}" for k, v in sorted(errs.items(), key=lambda x: -x[1])] or [f"- {t['none']}"]
    md += ["", f"## {t['checks']}", ""]
    for r in results:
        md.append(f"### `{r['model']}` · {r['title']} ({r['passed']}/{r['total']})")
        md += [f"- {'✅' if c['ok'] else '❌'} {c['name']}" + (f" — {c['info']}" if c["info"] else "") for c in r["checks"]]
        md += [f"- ℹ️ {'yes' if c['ok'] else 'no'} · {c['name']}" + (f" — {c['info']}" if c["info"] else "")
               for c in r.get("notes") or []]
        if r.get("net_cut"):
            md.append(f"- ℹ️ {r['net_cut'].get('note') or '-'}")
        md.append("")
    path = out / "report.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


def merge(dirs: list[str], out_root: str, lang: str) -> Path:
    """One report from several runs (models run apart, in parallel or on different days)."""
    results, versions = [], []
    for d in dirs:
        data = json.loads((Path(d) / "report.json").read_text(encoding="utf-8"))
        versions.append(data.get("version", "?"))
        for r in data["results"]:
            r["_from"] = d
            if r.get("task") in BY_ID:  # task names in the report's language, whatever language the run used
                r["title"] = BY_ID[r["task"]].title[lang]
            # reports from before the skill check became a note: re-score without it
            old = [c for c in r["checks"] if c["name"].startswith("chose the ") and "skill" in c["name"]]
            if old:
                r["checks"] = [c for c in r["checks"] if c not in old]
                r["notes"] = (r.get("notes") or []) + [{**c, "name": c["name"].replace("chose the", "loaded the", 1)}
                                                       for c in old]
                r["passed"] = sum(c["ok"] for c in r["checks"])
                r["total"] = len(r["checks"])
                r["score"] = round(r["passed"] / max(1, r["total"]), 3)
                r["full_pass"] = r["passed"] == r["total"]
            results.append(r)
    out = Path(out_root) / (time.strftime("%Y%m%d-%H%M%S") + "-merged")
    return report(results, out, lang, " + ".join(dict.fromkeys(versions)))


def rescore(report_dir: str, data_dir: str, out_root: str) -> Path:
    """The checks of a finished run again, on the folders it left (kept with --keep): a checker fix applies to the run
    without running the models again. The traces stay as recorded; the report says it was re-scored."""
    src = Path(report_dir)
    data = json.loads((src / "report.json").read_text(encoding="utf-8"))
    chats = Path(data_dir) / "appdata" / "chat"
    results = []
    for r in data["results"]:
        trace_file = src / (r.get("trace_file") or "")
        events = [json.loads(x) for x in trace_file.read_text(encoding="utf-8").splitlines() if x.strip()] \
            if trace_file.is_file() else []
        hits = list(chats.glob(f"*/.session/traces/{r.get('run_id')}.jsonl")) if r.get("run_id") else []
        if not hits:
            log("   no folder for", r["task"], "- kept as recorded")
            r["_from"] = str(src)
            results.append(r)
            continue
        ws = hits[0].parents[2]
        info = {"status": r["status"], "lang": data.get("lang", "tr"), "trace": events, "net_cut": r.get("net_cut")}
        allc = BY_ID[r["task"]].check(ws, info)
        checks = [c for c in allc if not c[0].startswith(INFO)]
        r["checks"] = [{"name": n, "ok": ok, "info": i} for n, ok, i in checks]
        r["notes"] = [{"name": n[len(INFO):], "ok": ok, "info": i} for n, ok, i in allc if n.startswith(INFO)]
        r["passed"] = sum(ok for _, ok, _ in checks)
        r["total"] = len(checks)
        r["score"] = round(r["passed"] / max(1, r["total"]), 3)
        r["full_pass"] = r["passed"] == r["total"]
        r["_trace"] = events
        results.append(r)
        log(f"   {r['task']}: {r['passed']}/{r['total']}")
    out = Path(out_root) / (src.name + "-rescored")
    lang = data.get("lang", "tr")
    return report(results, out, lang, str(data.get("version", "?"))
                  + (" (yeniden puanlandı)" if lang == "tr" else " (re-scored)"))


async def main(args) -> int:
    models = ["mock:solver"] if args.models.strip() == "mock" else [m.strip() for m in args.models.split(",") if m.strip()]
    tasks = TASKS if not args.tasks else [BY_ID[t.strip()] for t in args.tasks.split(",") if t.strip()]
    inst = Instance(args)
    inst.prepare()
    log("starting an isolated app in", inst.sp)
    inst.start()
    results = []
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            version = (await c.get(f"{inst.app}/api/health")).json().get("version", "?")
            for m in models:
                for t in tasks:
                    log(f"{m} · {t.id} ...")
                    r = await run_task(c, inst, m, t)
                    log(f"   {r['passed']}/{r['total']} checks, {r['status']}, {r['seconds']:.0f} s")
                    for ch in r["checks"]:
                        if not ch["ok"]:
                            log(f"   ✗ {ch['name']} {ch['info']}")
                    results.append(r)
    finally:
        inst.stop()
    out = Path(args.out) / time.strftime("%Y%m%d-%H%M%S")
    path = report(results, out, args.lang, version)
    log("report:", path)
    return 0 if all(r["full_pass"] for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AI IQ 300 agent evaluation")
    ap.add_argument("--models", default="", help='comma list of provider:model ids, or "mock" for the self-test')
    ap.add_argument("--merge", default="", help="comma list of report folders to combine into one report (no run)")
    ap.add_argument("--tasks", default="", help="comma list of task ids (default: all): " + ",".join(BY_ID))
    ap.add_argument("--lang", default="tr", choices=["tr", "en"])
    ap.add_argument("--data", default=str(ROOT / "data"), help="AI IQ 300 data folder to copy settings and keys from")
    ap.add_argument("--timeout", type=int, default=0, help="seconds per task (default: the task's own, 1800)")
    ap.add_argument("--port", type=int, default=8390, help="app port; +1 proxy, +2 mock model")
    ap.add_argument("--out", default=str(HERE / "reports"))
    ap.add_argument("--keep", action="store_true", help="keep the temporary data folder (chats, logs) to debug")
    ap.add_argument("--rescore", default="", help="a report folder to score again on the data folder a --keep run "
                                                  "left (give it with --kept); no model is run")
    ap.add_argument("--kept", default="", help="with --rescore: the kept temporary folder of that run")
    a = ap.parse_args()
    if a.rescore:
        if not a.kept:
            ap.error("--rescore needs --kept")
        log("report:", rescore(a.rescore, a.kept, a.out))
        sys.exit(0)
    if a.merge:
        log("report:", merge([d.strip() for d in a.merge.split(",") if d.strip()], a.out, a.lang))
        sys.exit(0)
    if not a.models:
        ap.error("--models (or --merge) is required")
    sys.exit(asyncio.run(main(a)))
