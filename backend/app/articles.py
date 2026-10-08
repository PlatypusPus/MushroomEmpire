"""Live hazard reading list: the official texts behind the hazard level, with a preview image each.

Sources, all US government products that can be shown in full (checked reachable 2026-10-08):
  NWS alerts API              the warning / watch / statement text and instructions for Miami-Dade and Broward
  NHC Atlantic RSS            public advisories, summaries, forecast discussions and the Tropical Weather Outlook
  NWS Miami (MFL) AFD         the forecaster's Area Forecast Discussion for South Florida
News outlets are deliberately not copied: their article text is copyrighted, and they are not an input to a flood tool.

Everything fetched is untrusted: tags and control characters are stripped, length is capped, links must be on official hosts,
images only from an allowlist of NOAA hosts. Nothing here is a flood-model input and nothing is fed to an LLM.
"""
import asyncio
import html
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from defusedxml import ElementTree as ET

from app.context import COUNTY_SAME, EVENT_LEVEL, UA, URL, _t, clean

IMG_HOSTS = {"www.nhc.noaa.gov", "radar.weather.gov", "cdn.star.nesdis.noaa.gov"}
LINK_HOSTS = {"www.nhc.noaa.gov", "www.weather.gov", "forecast.weather.gov"}
AFD_LIST = "https://api.weather.gov/products/types/AFD/locations/MFL"
TTL_S = 300
BODY_CAP = 9000
RADAR = "https://radar.weather.gov/ridge/standard/KAMX_0.gif"  # NWS Miami radar, latest frame
GOES = "https://cdn.star.nesdis.noaa.gov/GOES16/ABI/SECTOR/se/GEOCOLOR/600x600.jpg"  # GOES-East GeoColor, Southeast US
OUTLOOK = "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png"
STORM_WORD = re.compile(r"(?:Hurricane|Tropical Storm|Tropical Depression|Post-Tropical Cyclone|Potential Tropical Cyclone)\s+([A-Z][A-Za-z-]+)")

_cache: dict[str, Any] = {}
_lock = asyncio.Lock()


# ------------------------------------------------------------------ untrusted text -> safe plain text
def text_of(raw: Any, cap: int = BODY_CAP) -> str:
    """HTML or plain text -> plain text with line structure kept: line breaks from <br>/<p>/<pre>, no tags, no control characters."""
    t = re.sub(r"(?i)<\s*(br|/p|/pre|/div|/li)\s*/?>", "\n", str(raw or ""))
    t = html.unescape(re.sub(r"<[^>]*>", "", t))
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", t).replace("\r", "")
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) > cap:
        cut = t[:cap]
        t = cut[: cut.rfind("\n")] if "\n" in cut[cap // 2:] else cut
        t = t.rstrip() + "\n[text shortened, see the official source]"
    return t


def safe_image(url: str | None) -> str | None:
    u = urlparse(url or "")
    return url if u.scheme == "https" and u.hostname in IMG_HOSTS and u.path.lower().endswith((".png", ".jpg", ".gif")) else None


def safe_link(url: str | None) -> str | None:
    u = urlparse(url or "")
    return url if u.scheme == "https" and u.hostname in LINK_HOSTS else None


def image(url: str, alt: str, credit: str) -> dict | None:
    u = safe_image(url)
    return {"url": u, "alt": alt, "credit": credit} if u else None


def snippet(body: str, n: int = 240) -> str:
    """Short preview: the first sentence-ish run of prose, skipping all-caps headers and bulletin codes."""
    lines = [ln.strip() for ln in body.split("\n") if len(ln.strip()) > 40 and not ln.strip().isupper() and not re.match(r"^[A-Z0-9 ]{3,12}$", ln.strip())]
    return clean(" ".join(lines) or body, n)


# ------------------------------------------------------------------ parsers (pure, tested on saved real responses)
def parse_alert_articles(data: dict, now: datetime | None = None) -> list[dict]:
    """Active flood and tropical products that apply to Miami-Dade or Broward, one article per product (counties merged)."""
    now = now or datetime.now(timezone.utc)
    merged: dict[tuple, dict] = {}
    for f in data.get("features", []):
        p = f.get("properties", {})
        ev = clean(p.get("event"), 60)
        level = EVENT_LEVEL.get(ev.lower())
        if level is None or p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        end = _t(p.get("ends")) or _t(p.get("expires"))
        if end and end < now:
            continue
        same = (p.get("geocode") or {}).get("SAME") or []
        counties = [c for c, code in COUNTY_SAME.items() if code in same]
        if not counties:
            continue
        head = clean(p.get("headline"), 200)
        if ev.lower() == "flash flood warning" and "flash flood emergency" in head.lower():
            level = 4
        key = (ev, p.get("effective"), head)
        a = merged.setdefault(key, {"id": f"alert:{clean(p.get('id') or head, 120)}", "kind": "alert", "level": level, "source": clean(p.get("senderName"), 60) if clean(p.get("senderName"), 60).startswith("NWS") else f"NWS {clean(p.get('senderName'), 60) or 'alert'}",
                                    "title": ev, "headline": head, "issued": clean(p.get("effective"), 40) or None, "ends": clean(p.get("ends") or p.get("expires"), 40) or None,
                                    "url": "https://www.weather.gov/mfl/", "counties": [], "body_raw": (p.get("description"), p.get("instruction"))})
        a["counties"] = sorted({*a["counties"], *counties})
    out = []
    for a in merged.values():
        desc, instr = a.pop("body_raw")
        body = text_of(desc) + (f"\n\nWhat to do:\n{text_of(instr)}" if instr else "")
        a["title"] = f"{a['title']} for {', '.join(a['counties'])} County" if len(a["counties"]) == 1 else f"{a['title']} for {' and '.join(a['counties'])}"
        out.append({**a, "body": body.strip() or a["headline"], "summary": snippet(body) or a["headline"],
                    "image": image(RADAR, "NWS Miami radar, latest frame", "NOAA / NWS")})
    return sorted(out, key=lambda a: -a["level"])


def _kind(title: str) -> str:
    t = title.lower()
    return "outlook" if "outlook" in t else "advisory" if "public advisory" in t else "discussion" if "discussion" in t else "summary" if t.startswith("summary") else "technical"


def storm_graphic(storm_id: str, name: str) -> str:
    """NHC's stable per-storm graphic paths: al092026 -> .../storm_graphics/AT09/AL092026_<graphic>.png."""
    return f"https://www.nhc.noaa.gov/storm_graphics/AT{storm_id[2:4]}/{storm_id.upper()}_{name}.png"


def parse_nhc_articles(xml_text: str, storms: list[dict], limit: int = 6) -> list[dict]:
    """Newest first from the RSS; one of each kind per storm (the feed repeats older advisories)."""
    by_name = {s["name"].lower(): s for s in storms if s.get("name") and s.get("id")}
    out, seen = [], set()
    for it in ET.fromstring(xml_text).iter("item"):
        link = safe_link(clean(it.findtext("link"), 200))
        title = clean(it.findtext("title"), 140)
        if not link or not title:
            continue
        kind = _kind(title)
        m = STORM_WORD.search(title)
        storm = by_name.get(m.group(1).lower()) if m else None
        if (kind, storm["id"] if storm else None) in seen or (kind != "outlook" and not storm) or kind == "technical":  # keep only the outlook and items about an active Atlantic storm (the feed also carries local statements for other cities)
            continue
        seen.add((kind, storm["id"] if storm else None))
        body = text_of(it.findtext("description"))
        if not body:
            continue
        img = None
        if kind == "outlook":
            img = image(OUTLOOK, "NHC 7-day Atlantic tropical weather outlook", "NOAA / NHC")
        elif storm:
            g, alt = {"advisory": ("current_wind", "Current wind field"), "summary": ("key_messages", "Key messages"), "discussion": ("wind_probs_34_F120", "Chance of tropical-storm-force wind, next 5 days")}.get(kind, ("current_wind", "Current wind field"))
            img = image(storm_graphic(storm["id"], g), f"{alt}, {storm['name']}", "NOAA / NHC")
        try:
            issued = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            issued = None
        out.append({"id": f"nhc:{kind}:{storm['id'] if storm else 'at'}", "kind": kind, "level": None, "source": "NOAA National Hurricane Center", "title": title,
                    "headline": "", "issued": issued, "ends": None, "url": link, "counties": [], "body": body, "summary": snippet(body), "image": img,
                    "storm": storm["name"] if storm else None})
        if len(out) >= limit:
            break
    return out


def parse_afd(product: dict) -> dict | None:
    body = text_of(product.get("productText"))
    if not body:
        return None
    key = re.search(r"\.KEY MESSAGES[^\n]*\n(.*?)(?:\n\.[A-Z][A-Z /]+\.\.\.|\Z)", body, re.S)
    return {"id": f"afd:{clean(product.get('id'), 60)}", "kind": "forecast", "level": None, "source": f"NWS {clean(product.get('issuingOffice'), 10) or 'Miami'} forecast office",
            "title": "Area Forecast Discussion, NWS Miami", "headline": "", "issued": clean(product.get("issuanceTime"), 40) or None, "ends": None,
            "url": "https://forecast.weather.gov/product.php?site=MFL&issuedby=MFL&product=AFD", "counties": [],
            "body": body, "summary": snippet(key.group(1) if key else body), "image": image(GOES, "GOES-East GeoColor satellite view, Southeast US", "NOAA / NESDIS")}


# ------------------------------------------------------------------ fetching
async def _json(c: httpx.AsyncClient, url: str) -> Any:
    r = await c.get(url, headers=UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    return r.json()


async def _build() -> dict:
    async with httpx.AsyncClient() as c:
        async def alerts():
            return parse_alert_articles(await _json(c, URL["alerts"]))

        async def nhc():
            from app.context import parse_storms
            storms = parse_storms(await _json(c, URL["storms"]))["storms"]
            r = await c.get(URL["bulletins"], headers=UA, timeout=20, follow_redirects=True)
            r.raise_for_status()
            return parse_nhc_articles(r.text, storms)

        async def afd():
            first = (await _json(c, AFD_LIST))["@graph"][0]["@id"]
            if not first.startswith("https://api.weather.gov/products/"):
                raise ValueError("unexpected product link")
            return [a for a in [parse_afd(await _json(c, first))] if a]

        names = ("alerts", "nhc", "afd")
        res = await asyncio.gather(alerts(), nhc(), afd(), return_exceptions=True)
    articles, partial = [], []
    for n, r in zip(names, res):
        if isinstance(r, Exception):
            partial.append(n)
        else:
            articles += r
    return {"fetched_at": datetime.now(timezone.utc).isoformat(), "articles": articles, "partial": partial}


async def get_articles(force: bool = False) -> dict:
    """Cached for TTL_S. If a refresh fails entirely the last good list is returned, flagged stale, never shown as fresh."""
    async with _lock:
        c = _cache.get("v")
        if c and not force and time.time() - c["at"] < TTL_S:
            return c["data"]
        data = await _build()
        if not data["articles"] and c:  # everything failed: keep the last good copy, flagged
            return {**c["data"], "stale": True, "partial": data["partial"]}
        _cache["v"] = {"data": data, "at": time.time()}
        return data
