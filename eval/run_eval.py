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
from tasks import BY_ID, TASKS, Task  # noqa: E402

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
           "date": "Tarih", "lang": "Dil", "checks": "Kontroller", "note": "Puan = geçen kontrol / tüm kontroller. "
           "Kontroller gerçek çıktıya bakar: diskteki dosyalar, çalışan testler, gerçek tarayıcı, belge okuyucular, iz kaydı."},
    "en": {"title": "AI IQ 300 — Agent Evaluation", "model": "Model", "task": "Task", "score": "Score",
           "status": "Status", "time": "Time", "turns": "Turns", "tokens": "Output tokens", "tools": "Tools (errors)",
           "retries": "Retries", "switches": "Model switches", "summary": "Summary", "failed": "Failed checks",
           "errors": "Error kinds (by tool)", "none": "none", "passed": "tasks fully passed", "version": "Version",
           "date": "Date", "lang": "Language", "checks": "Checks", "note": "Score = passed checks / all checks. "
           "Checks look at real output: files on disk, tests that run, a real browser, document readers, the trace."},
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
    checks = await asyncio.to_thread(task.check, ws, info)
    passed = sum(ok for _, ok, _ in checks)
    s = trace.get("summary") or {}
    return {"model": model, "task": task.id, "title": task.title[lang], "status": info["status"],
            "seconds": round(time.time() - t0, 1), "score": round(passed / max(1, len(checks)), 3),
            "passed": passed, "total": len(checks), "full_pass": passed == len(checks),
            "checks": [{"name": n, "ok": ok, "info": i} for n, ok, i in checks],
            "turns": s.get("turns"), "out_tokens": s.get("out_tokens"), "tool_calls": s.get("tool_calls"),
            "tool_errors": s.get("tool_errors"), "errors_by_tool": s.get("errors_by_tool") or {},
            "retries": s.get("retries"), "fallbacks": s.get("fallbacks"), "debug_rounds": s.get("debug_rounds"),
            "answer": (last.get("content") or "")[:600], "error": meta.get("error") or "", "run_id": run_id,
            "net_cut": net if task.net_drop else None, "_trace": trace["events"]}


def report(results: list[dict], out: Path, lang: str, version: str) -> Path:
    t = T[lang]
    out.mkdir(parents=True, exist_ok=True)
    (out / "traces").mkdir(exist_ok=True)
    for r in results:
        name = f"{r['model'].replace(':', '_').replace('/', '_')}__{r['task']}.jsonl"
        (out / "traces" / name).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in r.pop("_trace")) + "\n",
                                           encoding="utf-8")
        r["trace_file"] = f"traces/{name}"
    data = {"version": version, "date": time.strftime("%Y-%m-%d %H:%M"), "lang": lang, "results": results}
    (out / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# {t['title']}", "", f"{t['version']}: {version} · {t['date']}: {data['date']} · {t['lang']}: {lang}", "",
          f"_{t['note']}_", "", f"## {t['summary']}", "",
          f"| {t['model']} | {t['score']} | {t['passed']} | {t['time']} | {t['tokens']} | {t['tools']} |", "|---|---|---|---|---|---|"]
    for m in dict.fromkeys(r["model"] for r in results):
        rs = [r for r in results if r["model"] == m]
        score = sum(r["score"] for r in rs) / len(rs)
        md.append(f"| `{m}` | **{score:.0%}** | {sum(r['full_pass'] for r in rs)}/{len(rs)} | "
                  f"{sum(r['seconds'] for r in rs) / 60:.1f} min | {sum(r['out_tokens'] or 0 for r in rs):,} | "
                  f"{sum(r['tool_calls'] or 0 for r in rs)} ({sum(r['tool_errors'] or 0 for r in rs)}) |")
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
        if r.get("net_cut"):
            md.append(f"- ℹ️ {r['net_cut'].get('note') or '-'}")
        md.append("")
    path = out / "report.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


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
    ap.add_argument("--models", required=True, help='comma list of provider:model ids, or "mock" for the self-test')
    ap.add_argument("--tasks", default="", help="comma list of task ids (default: all): " + ",".join(BY_ID))
    ap.add_argument("--lang", default="tr", choices=["tr", "en"])
    ap.add_argument("--data", default=str(ROOT / "data"), help="AI IQ 300 data folder to copy settings and keys from")
    ap.add_argument("--timeout", type=int, default=0, help="seconds per task (default: the task's own, 1800)")
    ap.add_argument("--port", type=int, default=8390, help="app port; +1 proxy, +2 mock model")
    ap.add_argument("--out", default=str(HERE / "reports"))
    ap.add_argument("--keep", action="store_true", help="keep the temporary data folder (chats, logs) to debug")
    sys.exit(asyncio.run(main(ap.parse_args())))
