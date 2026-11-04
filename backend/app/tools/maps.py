"""Places on a map: find venues near a place or coordinates, with address, phone, website, opening hours, rating
and distance, and draw them on an interactive map page.

Providers: Google Places API (New) and Yandex Places API when their keys are set (ratings, review counts, price
level); OpenStreetMap otherwise (free, no key): Nominatim for addresses and Overpass for venues around a point.
OpenStreetMap's usage policies are respected: an identifying User-Agent, at most one Nominatim request a second,
and results cached.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
from html import escape
from pathlib import Path

import httpx

from ..config import get_secret

UA = "AI-IQ-300/0.8 (local research assistant; https://github.com/AppsTRDesign)"
NOMINATIM = "https://nominatim.openstreetmap.org"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter")

# Words people use for a kind of place -> OpenStreetMap tags (TR + EN).
CATEGORIES: list[tuple[str, list[str]]] = [
    (r"kahve|kafe|cafe|coffee|kahveci", ['"amenity"="cafe"']),
    (r"restoran|restaurant|lokanta|yemek|kebap|kebab|pizza|burger|meyhane|balık|fish", ['"amenity"="restaurant"', '"amenity"="fast_food"']),
    (r"\bbar\b|pub|birahane", ['"amenity"="bar"', '"amenity"="pub"']),
    (r"pastane|fırın|firin|bakery|börek", ['"shop"="bakery"', '"shop"="pastry"']),
    (r"otel|hotel|pansiyon|hostel|konaklama", ['"tourism"="hotel"', '"tourism"="guest_house"', '"tourism"="hostel"']),
    (r"eczane|pharmacy", ['"amenity"="pharmacy"']),
    (r"hastane|hospital", ['"amenity"="hospital"']),
    (r"klinik|clinic|doktor|doctor|diş|dentist", ['"amenity"="clinic"', '"amenity"="doctors"', '"amenity"="dentist"']),
    (r"market|süpermarket|supermarket|bakkal|grocery", ['"shop"="supermarket"', '"shop"="convenience"']),
    (r"benzin|akaryakıt|fuel|gas station|petrol", ['"amenity"="fuel"']),
    (r"şarj|charging|ev charger", ['"amenity"="charging_station"']),
    (r"otopark|parking", ['"amenity"="parking"']),
    (r"banka|bank\b", ['"amenity"="bank"']),
    (r"\batm\b|bankamatik", ['"amenity"="atm"']),
    (r"spor salonu|gym|fitness", ['"leisure"="fitness_centre"']),
    (r"\bpark\b|parks", ['"leisure"="park"']),
    (r"kuaför|berber|hairdresser|barber", ['"shop"="hairdresser"']),
    (r"güzellik|beauty", ['"shop"="beauty"']),
    (r"giyim|clothes|butik|boutique", ['"shop"="clothes"']),
    (r"ayakkabı|shoe", ['"shop"="shoes"']),
    (r"elektronik|electronics|telefon", ['"shop"="electronics"', '"shop"="mobile_phone"']),
    (r"kitap|book", ['"shop"="books"']),
    (r"okul|school", ['"amenity"="school"']),
    (r"üniversite|university", ['"amenity"="university"']),
    (r"müze|museum", ['"tourism"="museum"']),
    (r"sinema|cinema", ['"amenity"="cinema"']),
    (r"cami|mosque", ['"amenity"="place_of_worship"]["religion"="muslim"']),
    (r"oto ?servis|car repair|tamirci", ['"shop"="car_repair"']),
    (r"oto galeri|car dealer|bayi", ['"shop"="car"']),
    (r"veteriner|veterinary", ['"amenity"="veterinary"']),
    (r"çiçek|florist", ['"shop"="florist"']),
    (r"mobilya|furniture", ['"shop"="furniture"']),
]

_NOMI_LOCK = asyncio.Lock()
_NOMI_LAST = [0.0]
_CACHE: dict[str, tuple[float, object]] = {}
CACHE_SECONDS = 1800


def _cached(key: str):
    hit = _CACHE.get(key)
    return hit[1] if hit and time.monotonic() - hit[0] < CACHE_SECONDS else None


def _remember(key: str, value):
    _CACHE[key] = (time.monotonic(), value)
    if len(_CACHE) > 300:
        _CACHE.pop(next(iter(_CACHE)))
    return value


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


async def _nominatim(c: httpx.AsyncClient, path: str, params: dict) -> list | dict:
    """Nominatim allows one request a second: requests are spaced out and cached."""
    key = path + json.dumps(params, sort_keys=True)
    if (hit := _cached(key)) is not None:
        return hit
    async with _NOMI_LOCK:
        wait = _NOMI_LAST[0] + 1.1 - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await c.get(f"{NOMINATIM}/{path}", params={**params, "format": "jsonv2"}, headers={"User-Agent": UA})
        finally:
            _NOMI_LAST[0] = time.monotonic()
    r.raise_for_status()
    return _remember(key, r.json())


async def geocode(c: httpx.AsyncClient, place: str, lang: str = "tr") -> dict | None:
    """'lat,lon' or an address/place name -> {lat, lon, name}."""
    if m := re.fullmatch(r"\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*", place or ""):
        return {"lat": float(m[1]), "lon": float(m[2]), "name": place.strip()}
    rows = await _nominatim(c, "search", {"q": place, "limit": 1, "accept-language": lang, "addressdetails": 0})
    if not rows:
        return None
    return {"lat": float(rows[0]["lat"]), "lon": float(rows[0]["lon"]), "name": rows[0].get("display_name", place),
            "box": rows[0].get("boundingbox")}


def _tags_for(query: str) -> list[str]:
    q = query.lower()
    return [t for pattern, tags in CATEGORIES if re.search(pattern, q) for t in tags]


def _osm_address(t: dict) -> str:
    parts = [t.get("addr:street", ""), t.get("addr:housenumber", "")]
    line = " ".join(p for p in parts if p).strip()
    return ", ".join(p for p in (line, t.get("addr:neighbourhood") or t.get("addr:suburb"), t.get("addr:district"),
                                 t.get("addr:city")) if p)


async def _overpass(c: httpx.AsyncClient, query: str, center: dict, radius: int, limit: int) -> list[dict]:
    tags = _tags_for(query)
    lat, lon = center["lat"], center["lon"]
    if tags:
        parts = "".join(f"nwr(around:{radius},{lat},{lon})[{t}];" for t in tags)
    else:  # no known kind of place: match the name instead
        name = re.sub(r'["\\\\]', "", query.strip())[:60]
        parts = f'nwr(around:{radius},{lat},{lon})["name"~"{re.escape(name)}",i];'
    ql = f"[out:json][timeout:25];({parts});out center tags {max(limit * 4, 40)};"
    key = "overpass" + ql
    if (hit := _cached(key)) is None:
        errors: list[str] = []

        async def ask(url: str) -> list:
            try:
                r = await c.post(url, data={"data": ql}, headers={"User-Agent": UA}, timeout=12)
            except httpx.HTTPError as e:
                errors.append(str(e) or type(e).__name__)
                raise
            if r.status_code != 200:
                errors.append(f"HTTP {r.status_code}")
                raise RuntimeError(r.status_code)
            return r.json().get("elements", [])

        # The public instances are often busy: ask them all at once, the first answer wins.
        tasks = [asyncio.create_task(ask(u)) for u in OVERPASS]
        try:
            for done in asyncio.as_completed(tasks):
                try:
                    hit = _remember(key, await done)
                    break
                except Exception:
                    continue
        finally:
            for t in tasks:
                t.cancel()
        if hit is None:
            raise RuntimeError(f"OpenStreetMap Overpass is busy ({', '.join(errors[:3])})")
    out = []
    for e in hit:
        t = e.get("tags") or {}
        if not t.get("name"):
            continue
        plat = e.get("lat") or (e.get("center") or {}).get("lat")
        plon = e.get("lon") or (e.get("center") or {}).get("lon")
        if plat is None:
            continue
        kind = next((t[k] for k in ("amenity", "shop", "tourism", "leisure") if t.get(k)), "")
        out.append({"name": t["name"], "category": kind + (f" ({t['cuisine']})" if t.get("cuisine") else ""),
                    "address": _osm_address(t), "lat": plat, "lon": plon,
                    "phone": t.get("phone") or t.get("contact:phone", ""),
                    "website": t.get("website") or t.get("contact:website", ""),
                    "opening_hours": t.get("opening_hours", ""), "rating": None, "reviews": None, "price": "",
                    "maps_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}", "source": "OpenStreetMap"})
    return out


async def _nominatim_places(c: httpx.AsyncClient, query: str, center: dict, radius: int, limit: int,
                            lang: str) -> list[dict]:
    """Fallback when Overpass is busy: Nominatim's search bounded to the area (category word or name)."""
    tags = _tags_for(query)
    word = tags[0].split("=")[1].strip('"]').split('"')[0].replace("_", " ") if tags else query
    d = radius / 111000
    box = f"{center['lon'] - d * 1.3},{center['lat'] + d},{center['lon'] + d * 1.3},{center['lat'] - d}"
    rows = await _nominatim(c, "search", {"q": word, "viewbox": box, "bounded": 1, "limit": min(limit * 2, 40),
                                          "extratags": 1, "addressdetails": 1, "accept-language": lang})
    out = []
    for x in rows:
        t, a = x.get("extratags") or {}, x.get("address") or {}
        name = (x.get("name") or "").strip()
        if not name:  # an unnamed place would get a street name or a house number instead
            continue
        out.append({"name": name, "category": x.get("type", ""),
                    "address": ", ".join(p for p in (" ".join(filter(None, (a.get("road"), a.get("house_number")))),
                                                     a.get("suburb") or a.get("neighbourhood"), a.get("town") or a.get("city_district"),
                                                     a.get("city") or a.get("province")) if p),
                    "lat": float(x["lat"]), "lon": float(x["lon"]), "phone": t.get("phone") or t.get("contact:phone", ""),
                    "website": t.get("website") or t.get("contact:website", ""), "opening_hours": t.get("opening_hours", ""),
                    "rating": None, "reviews": None, "price": "",
                    "maps_url": f"https://www.openstreetmap.org/{x.get('osm_type', 'node')}/{x.get('osm_id', '')}",
                    "source": "OpenStreetMap"})
    return out


async def _osm(c: httpx.AsyncClient, query: str, center: dict, radius: int, limit: int, lang: str) -> list[dict]:
    try:
        return await _overpass(c, query, center, radius, limit)
    except RuntimeError:
        return await _nominatim_places(c, query, center, radius, limit, lang)


async def _google(c: httpx.AsyncClient, key: str, query: str, near: str, center: dict | None, radius: int,
                  limit: int, lang: str) -> list[dict]:
    """Google Places API (New), Text Search: ratings, review counts, price level, hours, phone, website."""
    fields = ("places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,"
              "places.priceLevel,places.nationalPhoneNumber,places.websiteUri,places.regularOpeningHours.weekdayDescriptions,"
              "places.googleMapsUri,places.primaryTypeDisplayName,places.businessStatus")
    body: dict = {"textQuery": f"{query} {near}".strip() if not center else query, "languageCode": lang,
                  "maxResultCount": min(limit, 20)}
    if center:
        body["locationBias"] = {"circle": {"center": {"latitude": center["lat"], "longitude": center["lon"]},
                                           "radius": float(min(radius, 50000))}}
    r = await c.post("https://places.googleapis.com/v1/places:searchText", json=body,
                     headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": fields})
    r.raise_for_status()
    out = []
    for p in r.json().get("places", []):
        loc = p.get("location") or {}
        out.append({"name": (p.get("displayName") or {}).get("text", ""),
                    "category": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
                    "address": p.get("formattedAddress", ""), "lat": loc.get("latitude"), "lon": loc.get("longitude"),
                    "phone": p.get("nationalPhoneNumber", ""), "website": p.get("websiteUri", ""),
                    "opening_hours": "; ".join((p.get("regularOpeningHours") or {}).get("weekdayDescriptions", [])),
                    "rating": p.get("rating"), "reviews": p.get("userRatingCount"),
                    "price": (p.get("priceLevel") or "").replace("PRICE_LEVEL_", "").lower(),
                    "status": p.get("businessStatus", ""), "maps_url": p.get("googleMapsUri", ""), "source": "Google"})
    return out


async def _yandex(c: httpx.AsyncClient, key: str, query: str, near: str, center: dict | None, radius: int,
                  limit: int, lang: str) -> list[dict]:
    """Yandex Places API (search-maps.yandex.ru, type=biz): businesses with categories, hours, phones, website."""
    params = {"apikey": key, "text": f"{query} {near}".strip() if not center else query, "type": "biz",
              "lang": "tr_TR" if lang == "tr" else "en_US", "results": min(limit, 50)}
    if center:
        span = radius / 111000 * 2
        params.update(ll=f"{center['lon']},{center['lat']}", spn=f"{span:.4f},{span:.4f}", rspn=1)
    r = await c.get("https://search-maps.yandex.ru/v1/", params=params)
    r.raise_for_status()
    out = []
    for f in r.json().get("features", []):
        meta = (f.get("properties") or {}).get("CompanyMetaData") or {}
        lon, lat = (f.get("geometry") or {}).get("coordinates", [None, None])
        out.append({"name": meta.get("name", ""), "category": ", ".join(x.get("name", "") for x in meta.get("Categories", [])),
                    "address": meta.get("address", ""), "lat": lat, "lon": lon,
                    "phone": ", ".join(x.get("formatted", "") for x in meta.get("Phones", [])), "website": meta.get("url", ""),
                    "opening_hours": (meta.get("Hours") or {}).get("text", ""), "rating": None, "reviews": None,
                    "price": "", "maps_url": f"https://yandex.com.tr/maps/?ll={lon},{lat}&z=17&text={meta.get('name', '')}",
                    "source": "Yandex"})
    return out


async def find_places(query: str, near: str = "", radius: int = 1500, limit: int = 10, lang: str = "tr",
                      provider: str = "") -> dict:
    """Venues matching query near a place. Returns {provider, center, results, notes}."""
    radius = max(100, min(int(radius or 1500), 30000))
    limit = max(1, min(int(limit or 10), 30))
    notes: list[str] = []
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as c:
        center = await geocode(c, near, lang) if near else None
        if near and not center:
            notes.append(f"'{near}' could not be found on the map; searching by text only.")
        order = []
        if (key := get_secret("google_maps_key")) and provider in ("", "google"):
            order.append(("Google", lambda: _google(c, key, query, near, center, radius, limit, lang)))
        if (key := get_secret("yandex_maps_key")) and provider in ("", "yandex"):
            order.append(("Yandex", lambda: _yandex(c, key, query, near, center, radius, limit, lang)))
        if center and provider in ("", "osm", "openstreetmap"):
            order.append(("OpenStreetMap", lambda: _osm(c, query, center, radius, limit, lang)))
        results, used = [], ""
        for name, fn in order:
            try:
                results = await fn()
            except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as e:
                notes.append(f"{name}: {str(e)[:160] or type(e).__name__}")
                continue
            if results:
                used = name
                break
        if not results and not center and not order:
            notes.append("Give a place (district, address or 'lat,lon') with near=..., or set a Google/Yandex Places key.")
    if center:
        for r in results:
            if r.get("lat") is not None:
                r["distance_m"] = distance_m(center["lat"], center["lon"], float(r["lat"]), float(r["lon"]))
        if used == "OpenStreetMap":
            results.sort(key=lambda r: r.get("distance_m", 1 << 30))
    return {"provider": used or "-", "center": center, "results": results[:limit], "notes": notes}


def format_places(res: dict, lang: str = "tr") -> str:
    rows = res["results"]
    head = f"Provider: {res['provider']}" + (f"; center: {res['center']['name']}" if res.get("center") else "")
    lines = [head] + [f"Note: {n}" for n in res.get("notes", [])]
    if not rows:
        return "\n".join(lines + ["No places found. Try a wider radius, another word, or another district."])
    lines.append("| # | Name | Category | Rating | Distance | Address | Phone | Hours | Web |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        rating = f"{r['rating']} ({r.get('reviews') or 0})" if r.get("rating") else "-"
        dist = f"{r['distance_m']} m" if r.get("distance_m") is not None else "-"
        cell = lambda v: str(v or "-").replace("|", "/")[:90]  # noqa: E731
        lines.append(f"| {i} | {cell(r['name'])} | {cell(r['category'])} | {rating} | {dist} | {cell(r['address'])} | "
                     f"{cell(r['phone'])} | {cell(r['opening_hours'])} | {cell(r['website'])} |")
    lines.append("Map links: " + "; ".join(f"{r['name']}: {r['maps_url']}" for r in rows[:10] if r.get("maps_url")))
    return "\n".join(lines)


# The interactive map page (Leaflet + OpenStreetMap tiles): a filterable, sortable list of detail cards and numbered
# pins; directions start at the user's position when the search was "near me".
MAP_TEMPLATE = Path(__file__).with_name("map_page.html")
LABELS = {
    "tr": {"places": "yer", "you": "Buradasınız", "approx": "Yaklaşık konum (IP)", "away": "uzakta", "route": "Yol tarifi",
           "call": "Ara", "web": "Web", "open": "Haritada", "filter": "Bu listede ara…", "by_dist": "Mesafeye göre",
           "by_rating": "Puana göre", "by_name": "Ada göre", "all": "Tümü", "none": "Eşleşen yer yok.", "other": "diğer",
           "days": ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]},
    "en": {"places": "places", "you": "You are here", "approx": "Approximate location (IP)", "away": "away", "route": "Directions",
           "call": "Call", "web": "Website", "open": "On map", "filter": "Search this list…", "by_dist": "By distance",
           "by_rating": "By rating", "by_name": "By name", "all": "All", "none": "No matching places.", "other": "other",
           "days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]},
}


def _clean(r: dict) -> dict:
    """Map data is shown as text only: no markup from a provider reaches the page."""
    out = {k: (escape(v) if isinstance(v, str) else v) for k, v in r.items()}
    for k in ("website", "maps_url"):
        if out.get(k) and not str(out[k]).startswith(("http://", "https://")):
            out[k] = ""
    return out


def write_map(path: Path, title: str, res: dict, lang: str = "tr") -> None:
    data = {"center": _clean(res["center"]) if res.get("center") else None, "results": [_clean(r) for r in res["results"]],
            "provider": res.get("provider") if res.get("provider") not in (None, "-") else ""}
    js = lambda v: json.dumps(v, ensure_ascii=False).replace("</", "<\\/")  # noqa: E731  (no </script> inside data)
    page = (MAP_TEMPLATE.read_text(encoding="utf-8").replace("__LANG__", lang).replace("__TITLE__", escape(title))
            .replace("__DATA__", js(data)).replace("__LABELS__", js(LABELS.get(lang, LABELS["en"]))))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
