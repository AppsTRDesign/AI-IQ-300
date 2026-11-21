r"""End-to-end logic tests: an isolated app instance (its own temporary data folder) driven against the scripted mock
model in mock_llm.py. No real model, no keys. Run from the project root:

    .venv\Scripts\python.exe tests\e2e\run_e2e.py        (Windows)
    .venv/bin/python tests/e2e/run_e2e.py                (Linux / macOS)

Ports: AIIQ_TEST_PORT (default 8399) for the app, the next lower one for the mock. Exit code 0 = all passed."""
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
import websockets

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SP = Path(tempfile.mkdtemp(prefix="aiiq-e2e-"))
PORT = int(os.environ.get("AIIQ_TEST_PORT", "8399"))
DATA = SP / "appdata"
LOG = SP / "mock_log.jsonl"
APP, MOCK = f"http://127.0.0.1:{PORT}", f"http://127.0.0.1:{PORT - 1}"
PY = sys.executable
results = []
for _s in (sys.stdout, sys.stderr):  # a Windows console (cp1254 / cp437) cannot print the check names' symbols
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def check(name, ok, info=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def mock_log():
    return [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()] if LOG.exists() else []


async def wait_done(c, sid, limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        if not (await c.get(f"{APP}/api/sessions/{sid}/active")).json():
            return True
        await asyncio.sleep(0.3)
    return False


async def new_chat(c, text, **kw):
    sid = (await c.post(f"{APP}/api/sessions", json={})).json()["id"]
    r = await c.post(f"{APP}/api/sessions/{sid}/chat", json={"text": text, "model": "mock:mock-1", **kw})
    return sid, r.json()


async def msgs(c, sid):
    return (await c.get(f"{APP}/api/sessions/{sid}/messages")).json()


async def ws_read(url, seconds):
    out = []
    try:
        async with websockets.connect(url, origin=APP, max_size=None) as ws:
            t0 = time.time()
            while time.time() - t0 < seconds:
                try:
                    d = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
                except asyncio.TimeoutError:
                    continue
                out += d if isinstance(d, list) else [d]
    except Exception as e:  # noqa: BLE001
        out.append({"topic": "error", "type": str(e)})
    return out


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        h = (await c.get(f"{APP}/api/health")).json()
        print("version", h["version"])

        # 1. small talk + automatic title (the title was only made after a follow-up message)
        sid, r = await new_chat(c, "merhaba")
        check("small talk finishes", await wait_done(c, sid))
        m = await msgs(c, sid)
        check("small talk answer stored", m[-1]["role"] == "assistant" and "AI IQ 300" in m[-1]["content"], m[-1]["content"][:40])
        await asyncio.sleep(1.5)
        title = next(s for s in (await c.get(f"{APP}/api/sessions")).json() if s["id"] == sid)
        check("chat title written by the model", title["title"] == "Deneme Sohbeti", title["title"])
        first = [x for x in mock_log() if x["last"].startswith("merhaba")]
        check("small talk prompt is lean (<3500 chars)", first and first[0]["sys_chars"] < 3500, first[0]["sys_chars"] if first else "")

        # 2. a file task through the tag protocol
        sid, r = await new_chat(c, "DOSYA t.txt olustur")
        check("file task finishes", await wait_done(c, sid))
        m = await msgs(c, sid)
        f = Path(r["cwd"]) / "t.txt"
        check("file written by the tool", f.exists() and "merhaba dunya" in f.read_text(encoding="utf-8"))
        check("file task answer", "Dosya yazildi" in m[-1]["content"], m[-1]["content"][:60])
        task = [x for x in mock_log() if "DOSYA" in x["last"]]
        print("   file-task system prompt chars:", task[0]["sys_chars"], "native tools:", task[0]["tools"])

        # 3. the connection drops mid-answer: the written part is kept and continued, not rewritten
        t0 = time.time()
        sid, r = await new_chat(c, "DROP uzun bir cevap yaz")
        check("dropped answer finishes", await wait_done(c, sid, 60), f"{time.time() - t0:.1f}s")
        m = await msgs(c, sid)
        ans = m[-1]["content"]
        check("answer keeps the first part", "ILK-KISIM" in ans and ans.count("ILK-KISIM") == 1, ans[:30])
        check("answer has the continuation", "DEVAM-KISMI" in ans, ans[-40:])
        check("status ok after a drop", m[-1]["meta"].get("status") == "ok", m[-1]["meta"].get("status"))

        # 3b. this computer loses its internet mid-answer and gets it back 5 s later: the task waits (no retries against
        # the quota, no model switch), the UI hears "offline" then "online", and the same model continues the answer
        t0 = time.time()
        watch = asyncio.create_task(ws_read(f"ws://127.0.0.1:{PORT}/ws/events?since=0", 14))
        sid, r = await new_chat(c, "NETCUT uzun bir cevap yaz")
        check("internet drop: task finishes after the connection is back", await wait_done(c, sid, 60), f"{time.time() - t0:.1f}s")
        m = await msgs(c, sid)
        ans, meta = m[-1]["content"], m[-1]["meta"]
        steps = meta.get("steps") or []
        check("internet drop: answer keeps the first part and continues", "NET-ILK" in ans and "NET-DEVAM" in ans, ans[-40:])
        check("internet drop: waited for the connection (offline step)",
              any(s.get("kind") == "retry" and s.get("title") == "offline" and (s.get("data") or {}).get("until_online")
                  for s in steps), [s.get("title") for s in steps])
        check("internet drop: no switch to another model", not any(s.get("kind") == "fallback" for s in steps))
        check("internet drop: status ok", meta.get("status") == "ok", meta.get("status"))
        ev = await watch
        net = [e["payload"]["online"] for e in ev if e.get("topic") == "system" and e.get("type") == "net"]
        check("internet drop: UI told offline then online", False in net and net[-1] is True, net)

        # 3c. the stream goes silent but the provider answers a new request: the connection check continues where it
        # stopped after ~PROBE_CUT s instead of waiting for the 300 s stream timeout
        t0 = time.time()
        sid, r = await new_chat(c, "SESSIZ uzun bir cevap yaz")
        check("silent stream: finishes long before the stream timeout", await wait_done(c, sid, 90), f"{time.time() - t0:.1f}s")
        m = await msgs(c, sid)
        ans, steps = m[-1]["content"], m[-1]["meta"].get("steps") or []
        check("silent stream: cut by the connection check", any(s.get("kind") == "retry" and s.get("title") == "stalled"
              and "connection check" in (s.get("detail") or "") for s in steps), [s.get("title") for s in steps])
        check("silent stream: answer keeps the first part and continues", "SES-ILK" in ans and "SES-DEVAM" in ans
              and "COK-GEC" not in ans, ans[-50:])
        check("silent stream: no model switch", not any(s.get("kind") == "fallback" for s in steps))
        check("connection check: probe sent one 1-token request", any(x["last"] == "ping" for x in mock_log()))

        # 4. a busy provider (503) is retried
        sid, r = await new_chat(c, "BUSY selam")
        check("busy provider retried", await wait_done(c, sid, 60) and (await msgs(c, sid))[-1]["meta"].get("status") == "ok")

        # 5. websocket: a fresh page gets hello(reset) + a snapshot of the running task; a reconnect gets a replay
        sid, r = await new_chat(c, "SLOW say")
        await asyncio.sleep(2.0)
        ev = await ws_read(f"ws://127.0.0.1:{PORT}/ws/events?since=0", 1.5)
        hello = next((e for e in ev if e.get("type") == "hello"), None)
        snap = next((e for e in ev if e.get("type") == "snapshot"), None)
        check("ws hello with reset on a fresh page", bool(hello and hello["payload"]["reset"]))
        check("ws snapshot carries the running text", bool(snap and "yavas" in snap["payload"]["text"]),
              len(snap["payload"]["text"]) if snap else "no snapshot")
        last = max((e.get("seq") or 0) for e in ev)
        boot = hello["payload"]["boot"] if hello else ""
        ev2 = await ws_read(f"ws://127.0.0.1:{PORT}/ws/events?since={last}&boot={boot}", 1.2)
        h2 = next((e for e in ev2 if e.get("type") == "hello"), None)
        check("ws reconnect replays (no reset)", bool(h2 and not h2["payload"]["reset"]) and not any(e.get("type") == "snapshot" for e in ev2))
        check("ws replay has no gap", all((e.get("seq") or 0) > last for e in ev2 if e.get("topic") == "run"))
        ev3 = await ws_read(f"ws://127.0.0.1:{PORT}/ws/events?since={last}&boot=otherboot", 0.8)
        check("ws other boot id -> reset", any(e.get("type") == "hello" and e["payload"]["reset"] for e in ev3))
        ev4 = await ws_read(f"ws://127.0.0.1:{PORT}/ws/events?since=99999999", 0.8)
        check("ws since ahead of the server -> reset", any(e.get("type") == "hello" and e["payload"]["reset"] for e in ev4))

        # 6. stop twice (double click) while streaming: the task ends once, its answer is stored, the chat is free
        run_id = r["run_id"]
        a, b = await asyncio.gather(c.post(f"{APP}/api/runs/{run_id}/cancel"), c.post(f"{APP}/api/runs/{run_id}/cancel"))
        await c.post(f"{APP}/api/runs/{run_id}/cancel")
        check("stopped task leaves the run list", await wait_done(c, sid, 15))
        m = await msgs(c, sid)
        check("stopped task stored one answer", sum(x["role"] == "assistant" for x in m) == 1 and m[-1]["meta"].get("status") == "cancelled",
              m[-1]["meta"].get("status"))
        r2 = await c.post(f"{APP}/api/sessions/{sid}/chat", json={"text": "merhaba", "model": "mock:mock-1"})
        check("chat usable after stop", r2.status_code == 200 and not r2.json().get("steered"))
        await wait_done(c, sid)

        # 7. delete a chat while its task runs: no orphan folder or message comes back
        sid, r = await new_chat(c, "SLOW say")
        await asyncio.sleep(1.0)
        await c.delete(f"{APP}/api/sessions/{sid}")
        await asyncio.sleep(1.0)
        check("deleted chat folder stays gone", not Path(r["cwd"]).exists())
        check("deleted chat has no messages", (await msgs(c, sid)) == [])

        import sqlite3
        # 8. long chat: messages older than the history window are folded into the summary (nothing forgotten)
        sid = (await c.post(f"{APP}/api/sessions", json={})).json()["id"]
        db = sqlite3.connect(DATA / "aiiq.db", timeout=15)
        now = time.time()
        for i in range(70):
            db.execute("INSERT INTO messages(session_id, role, content, meta, created) VALUES(?,?,?,?,?)",
                       (sid, "user" if i % 2 == 0 else "assistant", f"eski mesaj {i}" + (" kod adi ALFA-7" if i == 3 else ""), "{}", now))
        db.commit()
        db.close()
        n0 = len(mock_log())
        r = await c.post(f"{APP}/api/sessions/{sid}/chat", json={"text": "selam", "model": "mock:mock-1"})
        check("long chat task finishes", await wait_done(c, sid))
        calls = mock_log()[n0:]
        check("old messages were summarized", any("eski mesaj 3" in json.dumps(x, ensure_ascii=False) or x["n"] == 2 for x in calls)
              and bool(sqlite3.connect(DATA / "aiiq.db").execute("SELECT summary FROM sessions WHERE id=?", (sid,)).fetchone()[0]))
        row = sqlite3.connect(DATA / "aiiq.db").execute("SELECT summary, summary_upto FROM sessions WHERE id=?", (sid,)).fetchone()
        print("   summary:", (row[0] or "")[:60], "| upto", row[1])

        # 8b. a weak model writes a tool call as a command line inside a code block: it is recognized and run
        sid, r = await new_chat(c, "PSEUDO p.txt dosyasini olustur")
        check("pseudo call task finishes", await wait_done(c, sid))
        f = Path(r["cwd"]) / "p.txt"
        check("pseudo call wrote the file", f.exists() and f.read_text(encoding="utf-8").startswith('selam\ndunya "tirnak"'),
              f.read_text(encoding="utf-8")[:30] if f.exists() else "missing")
        m = await msgs(c, sid)
        check("pseudo call final answer", "p.txt yazildi" in m[-1]["content"], m[-1]["content"][:60])

        # 8c. "the PDF is ready" while no PDF exists: asked twice, then a plain warning (no false "done")
        n0 = len(mock_log())
        sid, r = await new_chat(c, "FAKEPDF bilgisayarimin donanimini pdf rapor olarak yaz")
        check("fake pdf task finishes", await wait_done(c, sid))
        m = await msgs(c, sid)
        ans = m[-1]["content"]
        check("fake pdf answer carries the warning", ans.startswith("> ⚠️") and "donanim_raporu.pdf" in ans.split("\n")[0], ans[:120])
        calls = mock_log()[n0:]
        check("model was told the file is missing (twice)", sum("Checked on disk" in x["last"] for x in calls) == 2,
              sum("Checked on disk" in x["last"] for x in calls))
        check("request got the make_doc / system_info hint", "make_doc" in calls[0]["last"] and "system_info" in calls[0]["last"],
              calls[0]["last"][-200:])

        # 8c2. a script run before it was written: the model is told the file does not exist (no web search)
        n0 = len(mock_log())
        sid, r = await new_chat(c, "NOFILE hesap.py yaz ve calistir")
        check("missing-file task finishes", await wait_done(c, sid))
        calls = mock_log()[n0:]
        check("model told the file does not exist", any("does NOT exist" in x["last"] for x in calls))
        check("missing-file task wrote and ran it", (Path(r["cwd"]) / "hesap.py").exists()
              and "55" in (await msgs(c, sid))[-1]["content"])

        # 8c3. a reply that turns into one repeated token is never shown or stored; one cooler retry fixes it
        sid, r = await new_chat(c, "GARBAGE bir cevap ver")
        check("garbage task finishes", await wait_done(c, sid))
        ans = (await msgs(c, sid))[-1]["content"]
        check("garbage never stored, retry answered", "@" not in ans and "Duzgun cevap" in ans, ans[:60])

        # 8d. full-text search, the per-model record, long step details sent cut and loaded in full on demand
        hits = (await c.get(f"{APP}/api/search", params={"q": "yazildi"})).json()["results"]
        check("chat search finds a message", any("yazildi" in (h["snippet"] or "") for h in hits), len(hits))
        stats = (await c.get(f"{APP}/api/models/stats")).json()["models"]
        check("model record counts tasks", (stats.get("mock:mock-1") or {}).get("tasks", 0) >= 3, stats.get("mock:mock-1"))
        sid = (await c.post(f"{APP}/api/sessions", json={})).json()["id"]
        db = sqlite3.connect(DATA / "aiiq.db", timeout=15)
        big = "x" * 9000
        db.execute("INSERT INTO messages(session_id, role, content, meta, created) VALUES(?,?,?,?,?)",
                   (sid, "assistant", "uzun adim", json.dumps({"steps": [{"id": "s1", "kind": "command", "title": "t",
                                                                             "status": "done", "detail": big}]}), time.time()))
        db.commit()
        db.close()
        page = (await c.get(f"{APP}/api/sessions/{sid}/messages", params={"limit": 20})).json()["messages"]
        st0 = page[-1]["meta"]["steps"][0]
        check("long step detail sent cut", len(st0["detail"]) < 3000 and st0.get("lazy", {}).get("chars") == 9000)
        full = (await c.get(f"{APP}/api/messages/{st0['lazy']['mid']}/steps/{st0['lazy']['i']}")).json()
        check("step loads in full on demand", full.get("detail") == big)

        # 9. settings: provider concurrency is applied live; the fallback model needs its switch
        s = (await c.patch(f"{APP}/api/settings", json={"local_guard": {"emergency_unload": False}, "agent": {"prompt_mode": "lean"}})).json()
        check("new settings saved", s["local_guard"]["enabled"] is True and s["agent"]["prompt_mode"] == "lean")
        hh = (await c.get(f"{APP}/api/health")).json()
        check("no run left behind", hh["runs"] == [], hh["runs"])
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed" + (f"; FAILED: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir(parents=True)
    LOG.unlink(missing_ok=True)
    (DATA / "settings.json").write_text(json.dumps({
        "language": "tr", "permission_mode": "full", "active_model": "mock:mock-1",
        "providers": {"mock": {"name": "Mock", "kind": "openai", "base_url": f"{MOCK}/v1", "enabled": True}}}), encoding="utf-8")
    (DATA / "secrets.json").write_text(json.dumps({"mock_api_key": "test-key-for-the-mock"}), encoding="utf-8")
    env = {**os.environ, "AIIQ_DATA": str(DATA), "PYTHONIOENCODING": "utf-8", "AIIQ_NET_SIM": str(SP / "net_down"),
           "AIIQ_PROBE_AFTER": "6", "AIIQ_PROBE_CUT": "10"}
    mock = subprocess.Popen([PY, str(HERE / "mock_llm.py"), str(PORT - 1), str(LOG)], env=env)
    app = subprocess.Popen([PY, str(ROOT / "launcher.py"), "--port", str(PORT), "--no-browser"], env=env, cwd=str(ROOT),
                           stdout=open(SP / "app.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    code = 1
    try:
        for _ in range(80):
            try:
                if httpx.get(f"{APP}/api/health", timeout=1).status_code == 200 and httpx.get(f"{MOCK}/v1/models", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.4)
        code = asyncio.run(main())
    finally:
        app.terminate()
        mock.terminate()
        time.sleep(1)
        if os.environ.get("AIIQ_E2E_KEEP"):  # keep the mock log and chats to debug a failure
            print("kept:", SP)
        else:
            shutil.rmtree(SP, ignore_errors=True)
    sys.exit(code)
