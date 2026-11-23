"""A pass-through proxy between the app and a model provider that can cut the connection on demand (eval task
net_drop). Run by run_eval.py:  python net_proxy.py <port> <net-sim-file>

  /p/<id>/<path>   forwarded to the target registered for <id> (streams kept as streams)
  POST /_ctl/map   {"id": "https://api.example.com/v1"}  register targets
  POST /_ctl/cut   {"seconds": 8}  every open stream breaks now; the net-sim file says "offline" (the app's own
                   connection check reads it) and new requests wait until the time is over
  GET  /_ctl/state open streams, bytes of the current stream, cuts so far
"""
import asyncio
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

PORT, SIM = int(sys.argv[1]), Path(sys.argv[2])
app = FastAPI()
TARGETS: dict[str, str] = {}
STATE = {"open": 0, "bytes": 0, "cuts": [], "requests": 0}
online = asyncio.Event()
online.set()
cut_now = {"gen": 0}
client = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=30), follow_redirects=True)
HOP = {"host", "content-length", "transfer-encoding", "connection", "accept-encoding", "keep-alive"}


@app.post("/_ctl/map")
async def set_map(req: Request):
    TARGETS.update({k: str(v).rstrip("/") for k, v in (await req.json()).items()})
    return TARGETS


@app.get("/_ctl/state")
async def state():
    return STATE


@app.post("/_ctl/cut")
async def cut(req: Request):
    secs = float((await req.json()).get("seconds") or 8)
    cut_now["gen"] += 1
    online.clear()
    SIM.write_text("down", encoding="utf-8")
    STATE["cuts"].append({"at": time.time(), "seconds": secs, "open": STATE["open"], "bytes": STATE["bytes"]})

    async def back():
        await asyncio.sleep(secs)
        SIM.unlink(missing_ok=True)
        online.set()
    asyncio.create_task(back())
    return {"ok": True}


@app.api_route("/p/{pid}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def forward(pid: str, path: str, req: Request):
    await online.wait()
    base = TARGETS.get(pid)
    if not base:
        return JSONResponse({"error": f"no target for {pid}"}, status_code=502)
    url = f"{base}/{path}" + (f"?{req.url.query}" if req.url.query else "")
    headers = {k: v for k, v in req.headers.items() if k.lower() not in HOP}
    body = await req.body()
    STATE["requests"] += 1
    r = await client.send(client.build_request(req.method, url, headers=headers, content=body), stream=True)
    gen0 = cut_now["gen"]

    async def relay():
        STATE["open"] += 1
        STATE["bytes"] = 0
        try:
            async for chunk in r.aiter_bytes():  # decoded: content-encoding is not passed on
                if cut_now["gen"] != gen0:
                    raise ConnectionResetError("cut by the eval proxy")
                STATE["bytes"] += len(chunk)
                yield chunk
        finally:
            STATE["open"] -= 1
            await r.aclose()
    out_headers = {k: v for k, v in r.headers.items() if k.lower() not in HOP | {"content-encoding"}}
    return StreamingResponse(relay(), status_code=r.status_code, headers=out_headers)


if __name__ == "__main__":
    # "critical": a stream cut on purpose ends in ConnectionResetError, which is the point, not an error to print
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="critical")
