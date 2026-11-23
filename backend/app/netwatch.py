"""This computer's internet connection, watched in the background.

A short drop used to be noticed only when a cloud model call failed: the task retried a few times, often switched to
another model (a handover that loses the model's own train of thought) and ended after two 5-minute waits. Now:
- a probe runs every 10 s (every 3 s while offline): DNS + a TCP connect to a few well-known anycast hosts, or to the
  system proxy when one is set;
- "offline" is declared only after two failed probes in a row (one lost packet is not an outage), "online" on the
  first good one;
- every change is pushed to the UI (topic "system", type "net") and kept for clients that connect later;
- a running task that hits a network error asks `check_now()`; when this computer is offline it waits with
  `wait_online()` - as long as it takes, until the user stops it - and then continues on the same model with the same
  conversation (nothing is retried against the quota, no model switch, nothing forgotten)."""
from __future__ import annotations

import asyncio
import os
import re
import socket
import time

from .events import bus

INTERVAL_UP = 10.0
INTERVAL_DOWN = 3.0
TARGETS = (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443), ("208.67.222.222", 443))
NAMES = ("one.one.one.one", "dns.google", "www.msftconnecttest.com")
# Error texts that may mean this computer lost its connection (not that the provider is busy)
NET_ERROR = re.compile(r"getaddrinfo|Name or service|nodename|No address|network is unreachable|unreachable|"
                       r"10051|10065|11001|11002|ConnectError|ConnectTimeout|ReadError|RemoteProtocolError|"
                       r"connection (lost|reset|aborted|refused|closed)|connection dropped|WinError 1023[0-9]|"
                       r"timed out|timeout|stalled|server disconnected|EOF occurred", re.I)

STATE: dict = {"online": True, "since": time.time(), "checked": 0.0, "down_at": None, "last_down_secs": 0}
_fails = 0
_lock: asyncio.Lock | None = None  # created inside the running loop


def _proxy() -> tuple[str, int] | None:
    try:
        import urllib.request
        from urllib.parse import urlsplit
        px = urllib.request.getproxies()
        val = px.get("https") or px.get("http")
        if not val:
            return None
        u = urlsplit(val if "://" in val else f"http://{val}")
        return (u.hostname, u.port or 80) if u.hostname else None
    except Exception:  # noqa: BLE001 - a broken proxy setting must not break the watcher
        return None


def enabled() -> bool:
    """AIIQ_NETWATCH=0 turns the watcher off (tests with mock providers; machines that block probes)."""
    return os.environ.get("AIIQ_NETWATCH", "1") != "0"


def probe() -> bool:
    """True when this computer reaches the internet (blocking, ~0.1 s online, at most ~4 s offline)."""
    sim = os.environ.get("AIIQ_NET_SIM")  # end-to-end tests: while this file exists the computer counts as offline
    if sim and os.path.exists(sim):
        return False
    # Without the file the real connection is probed: the evaluation sets AIIQ_NET_SIM for every task, and a real
    # outage during one was taken for "online" (the provider was then called unreachable and the task ended).
    if not enabled():
        return True
    px = _proxy()
    if px:
        try:
            socket.create_connection(px, timeout=3).close()
            return True
        except OSError:
            return False
    dns = False
    for name in NAMES:
        try:
            socket.getaddrinfo(name, 443)
            dns = True
            break
        except OSError:
            continue
    if not dns:
        return False
    for host in TARGETS:
        try:
            socket.create_connection(host, timeout=2.5).close()
            return True
        except OSError:
            continue
    return False


def is_online() -> bool:
    return bool(STATE["online"])


def snapshot() -> dict:
    return {"online": STATE["online"], "since": STATE["since"], "down_secs": STATE["last_down_secs"]}


def _set(online: bool) -> None:
    if online == STATE["online"]:
        return
    now = time.time()
    if online:
        STATE["last_down_secs"] = int(now - (STATE["down_at"] or now))
        STATE["down_at"] = None
    else:
        STATE["down_at"] = now
    STATE["online"], STATE["since"] = online, now
    bus.publish("system", "net", snapshot())


async def check_now(confirm: int = 2) -> bool:
    """Probes at once (a task just hit a network error). Offline is confirmed by `confirm` failed probes 1.5 s apart."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        for i in range(max(1, confirm)):
            ok = await asyncio.to_thread(probe)
            STATE["checked"] = time.time()
            if ok:
                _set(True)
                return True
            if i + 1 < confirm:
                await asyncio.sleep(1.5)
        _set(False)
        return False


async def wait_online(cancel: asyncio.Event | None = None, limit: float | None = None) -> bool:
    """Waits until the connection is back (probing every 3 s), the task is stopped, or `limit` seconds pass."""
    end = time.monotonic() + limit if limit else None
    while True:
        if cancel is not None and cancel.is_set():
            return False
        if await check_now(confirm=1):
            return True
        if end and time.monotonic() >= end:
            return False
        try:
            if cancel is not None:
                await asyncio.wait_for(cancel.wait(), INTERVAL_DOWN)
            else:
                await asyncio.sleep(INTERVAL_DOWN)
        except asyncio.TimeoutError:
            pass


def looks_like_network(err: object) -> bool:
    return bool(NET_ERROR.search(str(err or "")))


async def watch() -> None:
    """The background loop started with the app."""
    global _fails
    while True:
        try:
            ok = await asyncio.to_thread(probe)
            STATE["checked"] = time.time()
            if ok:
                _fails = 0
                _set(True)
            else:
                _fails += 1
                if _fails >= 2:
                    _set(False)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the watcher never dies
            pass
        await asyncio.sleep(INTERVAL_DOWN if (not STATE["online"] or _fails) else INTERVAL_UP)
