"""The user's current location for map searches. The open app is asked first: the browser's geolocation (Wi-Fi /
GPS through the operating system, metres; the browser asks the user's permission once). Without it (permission
refused, no window open, timeout) an approximate location from the internet address is used and marked as such.
The result is kept for a few minutes and turned into a street address with OpenStreetMap."""
from __future__ import annotations

import asyncio
import time
import uuid

import httpx

from .events import bus

_PENDING: dict[str, asyncio.Future] = {}
_LAST: dict = {}
KEEP_SECONDS = 600
UA = "AI-IQ-300/0.8 (local research assistant; https://github.com/AppsTRDesign)"


def answer(request_id: str, data: dict) -> bool:
    """The app's reply to a location request (POST /api/location/{id})."""
    fut = _PENDING.get(request_id)
    if not fut or fut.done():
        return False
    fut.set_result(data)
    return True


async def _from_browser(timeout: float) -> dict | None:
    rid = uuid.uuid4().hex[:12]
    fut = asyncio.get_running_loop().create_future()
    _PENDING[rid] = fut
    bus.publish("app", "location.request", {"request_id": rid})
    try:
        data = await asyncio.wait_for(fut, timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        _PENDING.pop(rid, None)
    if not isinstance(data, dict) or data.get("lat") is None:
        return {"error": (data or {}).get("error") or "unavailable"} if isinstance(data, dict) else None
    return {"lat": float(data["lat"]), "lon": float(data["lon"]), "accuracy_m": int(float(data.get("accuracy") or 0)),
            "source": "device"}


async def _from_ip() -> dict | None:
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": UA}) as c:
        for url in ("https://ipapi.co/json/", "https://ipinfo.io/json", "https://ipwho.is/"):
            try:
                d = (await c.get(url)).json()
            except (httpx.HTTPError, ValueError):
                continue
            lat, lon = d.get("latitude"), d.get("longitude")
            if lat is None and isinstance(d.get("loc"), str) and "," in d["loc"]:
                lat, lon = (float(x) for x in d["loc"].split(","))
            if lat is not None:
                return {"lat": float(lat), "lon": float(lon), "accuracy_m": 5000, "source": "ip",
                        "city": d.get("city") or "", "region": d.get("region") or d.get("region_name") or ""}
    return None


async def _address(lat: float, lon: float, lang: str) -> str:
    from .tools import maps
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            d = await maps._nominatim(c, "reverse", {"lat": lat, "lon": lon, "zoom": 17, "accept-language": lang})
        return d.get("display_name", "") if isinstance(d, dict) else ""
    except (httpx.HTTPError, ValueError):
        return ""


async def current(lang: str = "tr", fresh: bool = False) -> dict:
    """{lat, lon, accuracy_m, source: device|ip, address, at} or {error}."""
    if _LAST and not fresh and time.time() - _LAST["at"] < KEEP_SECONDS:
        return _LAST
    loc = await _from_browser(20)
    refused = loc.get("error") if loc and "error" in loc else None
    if not loc or "error" in loc:
        loc = await _from_ip()
    if not loc:
        return {"error": "location unavailable" + (f" ({refused})" if refused else "")}
    loc["address"] = await _address(loc["lat"], loc["lon"], lang)
    loc["at"] = time.time()
    if refused:
        loc["note"] = f"device location: {refused}"
    _LAST.clear()
    _LAST.update(loc)
    return loc


HERE_WORDS = {"", "me", "here", "current", "current location", "my location", "near me", "nearby", "konum", "konumum",
              "burası", "burasi", "burada", "yakınımda", "yakinimda", "bulunduğum yer", "mevcut konum", "anlık konum"}


def means_here(near: str) -> bool:
    return (near or "").strip().lower() in HERE_WORDS


def describe(loc: dict) -> str:
    if "error" in loc:
        return f"Location unavailable: {loc['error']}. Ask the user for a district or address."
    how = ("from this device (Wi-Fi/GPS), accurate to about {a} m".format(a=loc.get("accuracy_m") or "?")
           if loc["source"] == "device" else "APPROXIMATE, from the internet address (city level, may be off by "
           "kilometres; say so and offer to use the exact district or address)")
    return (f"Current location {how}: {loc['lat']:.6f},{loc['lon']:.6f}"
            + (f"\nAddress: {loc['address']}" if loc.get("address") else "")
            + (f"\n({loc['note']})" if loc.get("note") else ""))
