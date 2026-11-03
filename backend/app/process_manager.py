"""Background process supervisor: argv-based spawn, concurrent stdout/stderr streaming, tree kill."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from . import db
from .events import bus

# Windows console programs (cmd, mkdir, many CLIs) write in the OEM code page (e.g. cp857 for Turkish), not UTF-8.
LEGACY = "oem" if sys.platform == "win32" else "latin-1"


def _decode(line: bytes) -> str:
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        return line.decode(LEGACY, errors="replace")

MAX_CONCURRENT = 8
TAIL_LINES = 400
TERMINAL = ("exited", "failed", "timed_out", "cancelled")


@dataclass
class ProcInfo:
    id: str
    argv: list[str]
    cwd: str
    owner: str
    state: str = "queued"
    pid: int | None = None
    exit_code: int | None = None
    started: float = field(default_factory=time.time)
    tail: deque = field(default_factory=lambda: deque(maxlen=TAIL_LINES))
    proc: asyncio.subprocess.Process | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_requested: bool = False

    def public(self) -> dict:
        return {"id": self.id, "argv": self.argv, "cwd": self.cwd, "owner": self.owner, "state": self.state,
                "pid": self.pid, "exit_code": self.exit_code, "started": self.started}


class ProcessManager:
    def __init__(self) -> None:
        self.procs: dict[str, ProcInfo] = {}
        self._sem: asyncio.Semaphore | None = None

    def _emit(self, info: ProcInfo, type_: str, **payload) -> None:
        bus.publish("process", type_, {"process_id": info.id, "owner": info.owner, **payload})

    def _persist(self, info: ProcInfo) -> None:
        db.execute(
            "INSERT OR REPLACE INTO processes(id,pid,argv,cwd,state,exit_code,started,ended,owner) VALUES(?,?,?,?,?,?,?,?,?)",
            (info.id, info.pid, json.dumps(info.argv), info.cwd, info.state, info.exit_code, info.started,
             time.time() if info.state in TERMINAL else None, info.owner),
        )

    async def start(self, argv: list[str], cwd: str, env: dict[str, str], owner: str = "user",
                    timeout: float | None = None) -> ProcInfo:
        self._sem = self._sem or asyncio.Semaphore(MAX_CONCURRENT)
        info = ProcInfo(id=uuid.uuid4().hex[:12], argv=argv, cwd=cwd, owner=owner)
        self.procs[info.id] = info
        self._persist(info)
        await self._sem.acquire()
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        try:
            info.proc = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **kwargs)
        except Exception as e:
            self._sem.release()
            info.state, info.exit_code = "failed", -1
            info.tail.append(f"[spawn error] {e}")
            self._persist(info)
            self._emit(info, "exit", state=info.state, exit_code=-1, error=str(e))
            info.done.set()
            return info
        info.pid, info.state = info.proc.pid, "running"
        self._persist(info)
        self._emit(info, "started", argv=argv, pid=info.pid, cwd=cwd)
        asyncio.create_task(self._supervise(info, timeout))
        return info

    async def _pump(self, info: ProcInfo, stream: asyncio.StreamReader, name: str) -> None:
        buf = b""
        while chunk := await stream.read(4096):
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for line in lines:
                self._line(info, name, _decode(line).rstrip("\r"))
        if buf:
            self._line(info, name, _decode(buf))

    def _line(self, info: ProcInfo, name: str, line: str) -> None:
        info.tail.append(f"[stderr] {line}" if name == "stderr" else line)
        self._emit(info, "log", stream=name, line=line)

    async def _supervise(self, info: ProcInfo, timeout: float | None) -> None:
        p = info.proc
        assert p and p.stdout and p.stderr
        pumps = asyncio.gather(self._pump(info, p.stdout, "stdout"), self._pump(info, p.stderr, "stderr"))
        try:
            await asyncio.wait_for(asyncio.shield(p.wait()), timeout)
        except asyncio.TimeoutError:
            info.state = "timed_out"
            await self._kill_tree(info)
            await p.wait()
        try:
            await asyncio.wait_for(pumps, 10)  # descendants may hold pipes open briefly
        except asyncio.TimeoutError:
            pass
        info.exit_code = p.returncode
        if info.cancel_requested:
            info.state = "cancelled"
        elif info.state == "running":
            info.state = "exited" if p.returncode == 0 else "failed"
        self._sem.release()
        self._persist(info)
        self._emit(info, "exit", state=info.state, exit_code=info.exit_code)
        info.done.set()

    async def _kill_tree(self, info: ProcInfo) -> None:
        p = info.proc
        if not p or p.returncode is not None:
            return
        if sys.platform == "win32":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(p.pid),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await killer.wait()
        else:
            try:
                os.killpg(p.pid, signal.SIGTERM)
                await asyncio.wait_for(p.wait(), 5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    async def stop(self, proc_id: str) -> bool:
        info = self.procs.get(proc_id)
        if not info or info.state != "running":
            return False
        info.cancel_requested = True
        info.state = "cancelling"
        self._emit(info, "state", state="cancelling")
        await self._kill_tree(info)
        await info.done.wait()
        return True

    async def stop_owner(self, owner: str) -> None:
        await asyncio.gather(*(self.stop(i.id) for i in list(self.procs.values())
                               if i.owner == owner and i.state == "running"))

    async def shutdown(self) -> None:
        await asyncio.gather(*(self.stop(i) for i, p in list(self.procs.items()) if p.state == "running"))

    def list(self) -> list[dict]:
        return [p.public() for p in self.procs.values()]


manager = ProcessManager()
