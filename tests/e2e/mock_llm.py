"""Scripted OpenAI-compatible model server for logic tests (no real model)."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

LOG = Path(sys.argv[2])
app = FastAPI()
state = {"busy": 0}


@app.get("/v1/models")
def models():
    return {"data": [{"id": "mock-1", "context_length": 64000}, {"id": "mock-2", "context_length": 64000}]}


def chunk(text):
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n"


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    msgs = body["messages"]
    system = next((m["content"] for m in msgs if m["role"] == "system"), "") or ""
    users = [m for m in msgs if m["role"] == "user"]
    last = str(users[-1]["content"]) if users else ""
    whole = "\n".join(str(m.get("content") or "") for m in msgs if m["role"] != "system")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "model": body["model"], "n": len(msgs), "sys_chars": len(system),
                            "tools": len(body.get("tools") or []), "last": last[:600],
                            "roles": [m["role"] for m in msgs]}, ensure_ascii=False) + "\n")
    drop = False
    delay = 0.0
    sim = os.environ.get("AIIQ_NET_SIM")
    if last == "ping" and body.get("max_tokens") == 1:  # the app's connection check: answers at once
        text = "p"
    elif "Write a short title" in system:
        text = "Deneme Sohbeti"
    elif "SESSIZ" in whole and state.get("silent", 0) < 1:
        # The stream starts, then goes silent with the connection left open (a lost generation): the app's
        # connection check must see the provider answering and continue where it stopped, long before 300 s.
        state["silent"] = 1

        async def hang():
            for p in ["SES-ILK ", "kelime " * 60]:  # > 300 characters: a part that short is kept and continued
                yield chunk(p)
            await asyncio.sleep(120)
            yield chunk("COK-GEC")
        return StreamingResponse(hang(), media_type="text/event-stream")
    elif "SESSIZ" in whole:
        text = "SES-DEVAM bitti."
    elif "NETCUT" in whole and sim and state.get("netcut", 0) < 1:
        # This computer "loses its internet" mid-answer (the app's probe sees the file) and gets it back 5 s later
        state["netcut"] = 1
        Path(sim).write_text("down", encoding="utf-8")
        asyncio.get_running_loop().call_later(5, lambda: Path(sim).unlink(missing_ok=True))
        text, drop = "NET-ILK " + "parca " * 80, True
    elif "NETCUT" in whole:
        text = "NET-DEVAM tamamlandi."
    elif "Summarize the conversation" in system:
        text = "- ozet: kullanici ALFA-7 kod adini verdi"
    elif "[App note: connection dropped]" in last:
        text = "DEVAM-KISMI tamamlandi."
    elif "BUSY" in whole and state["busy"] < 1:
        state["busy"] += 1
        return JSONResponse({"error": {"message": "model is busy"}}, status_code=503)
    elif "DROP" in whole and "[App note: connection dropped]" not in whole:
        text, drop = "ILK-KISIM " + "kelime " * 80, True
    elif "SLOW" in last:
        text, delay = "yavas " * 60, 0.5
    elif "DOSYA" in whole and "Tool results:" not in whole and not any(m["role"] == "tool" for m in msgs):
        text = 'Dosyayi yaziyorum.\n<tool name="write_file" path="t.txt">merhaba dunya</tool>'
    elif "DOSYA" in whole:
        text = "Dosya yazildi: t.txt"
    elif "PSEUDO" in whole and "Tool results:" not in whole:
        text = ('Adim 1: dosyayi kaydet\n```powershell\nwrite_file path="p.txt" content="selam\\ndunya \\"tirnak\\""\n```\n'
                "Sonuc: p.txt olusturuldu.")
    elif "PSEUDO" in whole:
        text = "Tamam, p.txt yazildi."
    elif "GARBAGE" in last and state.get("garbage", 0) < 1:
        state["garbage"] = state.get("garbage", 0) + 1

        async def bad():
            yield chunk("@" * 60)
            yield "data: " + json.dumps({"error": "prediction aborted, token repeat limit reached"}) + "\n\n"
        return StreamingResponse(bad(), media_type="text/event-stream")
    elif "GARBAGE" in last:
        text = "Duzgun cevap."
    elif "NOFILE" in whole and "does NOT exist" not in whole:
        text = 'Calistiriyorum.\n<tool name="run" shell="python">hesap.py</tool>'
    elif "NOFILE" in whole and "Tool results:" in last and "hesap.py" in last and "55" not in whole:
        text = ('Dosyayi yaziyorum.\n<tool name="write_file" path="hesap.py">print(sum(range(1, 11)))</tool>\n'
                '<tool name="run" shell="python">hesap.py</tool>')
    elif "NOFILE" in whole:
        text = "Sonuc 55."
    elif "FAKEPDF" in whole:
        text = "Rapor hazir. Raporu gormek icin `donanim_raporu.pdf` dosyasini acin."
    else:
        text = "Merhaba! Ben AI IQ 300."

    async def gen():
        parts = [text[i:i + 12] for i in range(0, len(text), 12)]
        for i, p in enumerate(parts):
            yield chunk(p)
            await asyncio.sleep(delay or 0.003)
            if drop and i > len(parts) * 0.7:
                await asyncio.sleep(0.05)
                raise ConnectionResetError("cut")
        yield "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": sum(len(str(m.get('content') or '')) for m in msgs) // 4,
                                               "completion_tokens": len(text) // 4}}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
