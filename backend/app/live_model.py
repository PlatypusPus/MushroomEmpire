"""Live forecasts at any US water-level gauge, and a model that keeps learning from new live readings.

Forecast: a clicked point -> nearest active USGS gauge (gage height, 00065) -> the same 12 features the model was trained on
(level relative to the gauge's own q95, the 3 h trend rule and app.agents.ingestion.history, rain sums in inches) -> forecaster.
Units line up with SF2Bench: USGS gage height is feet, and SF2Bench rain was checked to be inches (Nicole peak hour 0.40).
HAND is not looked up for live gauges (None; LightGBM routes missing values), and the q95 comes from the last 12 months,
not a multi-year train split. So live output is always "experimental": validated only on SF2Bench replays.

Learning: once a day, for the tracked gauges (South Florida's, plus every gauge someone clicked), rebuild rows from the
last ~90 days. The label is simply the level the gauge reached k hours later, so live data labels itself. Continue boosting
from the current model (LightGBM init_model), hold out the newest 14 days (rows whose target falls in them are purged from
training), and promote the new model only if its quantile loss there beats the current one by 1%. One model per region
("sf", "us"); the SF2Bench model used by the replays is never changed.
"""
import asyncio
import json
from bisect import bisect_left, bisect_right
from itertools import accumulate
import logging
import time
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import quantiles

import httpx
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from app.agents.ingestion import STALE_AFTER, history
from app.agents.risk import derive
from app.context import UA, clean
from app.models.lightgbm_model import FEATURES, LEADS, QUANTILES, VERSION, Forecaster, to_row
from app.schemas import FeatureVector

log = logging.getLogger("coastguard.live_model")
DIR = Path(__file__).resolve().parents[1] / "cache" / "live"  # backend/cache is git-ignored: learned models stay local
IV = "https://waterservices.usgs.gov/nwis/iv/"
SITES = "https://waterservices.usgs.gov/nwis/site/"
METEO = "https://api.open-meteo.com/v1"
SF_BBOX = (-80.9, 25.1, -79.9, 26.6)  # lon/lat box around the South Florida places
SEARCH_KM = 30
STEP_H = 3  # one training row every 3 h per gauge
EVAL_DAYS = 14
ROUNDS = 60  # extra boosting rounds per live update
MIN_ROWS = 500  # below this the update is skipped, not forced
PROMOTE_IF = 0.99  # new loss must be at most 99% of the current one
MAX_TRACKED = 120
MM_PER_IN = 25.4
_sem = asyncio.Semaphore(4)  # be polite to USGS
_mem: dict[tuple, tuple[float, object]] = {}


def km(lat1, lon1, lat2, lon2) -> float:
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def region_of(lat: float, lon: float) -> str:
    x0, y0, x1, y1 = SF_BBOX
    return "sf" if x0 <= lon <= x1 and y0 <= lat <= y1 else "us"


def _read(name: str, default):
    try:
        return json.loads((DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / name).write_text(json.dumps(data, default=str), encoding="utf-8")


async def _cached(key: tuple, ttl_s: float, fetch):
    hit = _mem.get(key)
    if hit and time.monotonic() - hit[0] < ttl_s:
        return hit[1]
    val = await fetch()
    _mem[key] = (time.monotonic(), val)
    return val


# ------------------------------------------------------------------ sources
def hourly(points: list[tuple[datetime, float]]) -> list[dict]:
    """15-minute readings -> hourly means (SF2Bench series are hourly). Sorted, UTC."""
    by: dict[datetime, list[float]] = {}
    for t, v in points:
        by.setdefault(t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0), []).append(v)
    return [{"ts": t, "value": sum(v) / len(v)} for t, v in sorted(by.items())]


async def sites_near(c: httpx.AsyncClient, lat: float, lon: float, radius_km: float = SEARCH_KM) -> list[dict]:
    """Active USGS gauges reporting gage height near a point, nearest first."""
    d = radius_km / 111
    bbox = f"{lon - d / cos(radians(lat)):.4f},{lat - d:.4f},{lon + d / cos(radians(lat)):.4f},{lat + d:.4f}"

    async def fetch():
        r = await c.get(SITES, params={"format": "rdb", "bBox": bbox, "parameterCd": "00065", "siteStatus": "active", "hasDataTypeCd": "iv"})
        if r.status_code == 404:  # USGS answers 404 for "no sites here"
            return []
        r.raise_for_status()
        rows = [ln.split("\t") for ln in r.text.splitlines() if ln and not ln.startswith("#")]
        if len(rows) < 3:
            return []
        h = rows[0]
        out = []
        for row in rows[2:]:  # rows[1] is the column-width line
            x = dict(zip(h, row))
            try:
                out.append({"id": x["site_no"], "name": clean(x["station_nm"], 80), "lat": float(x["dec_lat_va"]), "lon": float(x["dec_long_va"])})
            except (KeyError, ValueError):
                continue
        return out

    found = await _cached(("sites", bbox), 86400, fetch)
    for s in found:
        s["km"] = round(km(lat, lon, s["lat"], s["lon"]), 1)
    return sorted((s for s in found if s["km"] <= radius_km), key=lambda s: s["km"])


async def levels(c: httpx.AsyncClient, site: str, days: int) -> list[dict]:
    """Hourly gage height (ft) for the last `days` days. Long windows redirect to nwis.waterservices, so follow it."""
    async def fetch():
        end = datetime.now(timezone.utc)
        async with _sem:
            r = await c.get(IV, params={"format": "json", "sites": site, "parameterCd": "00065",
                                        "startDT": (end - timedelta(days=days)).strftime("%Y-%m-%dT%H:%MZ"), "endDT": end.strftime("%Y-%m-%dT%H:%MZ")})
        r.raise_for_status()
        pts = []
        for ts in r.json()["value"]["timeSeries"]:
            for v in ts["values"][0]["value"]:
                try:
                    x = float(v["value"])
                except (TypeError, ValueError):
                    continue
                if x > -999:  # USGS uses -999999 for "no value"
                    pts.append((datetime.fromisoformat(v["dateTime"]), x))
        return hourly(pts)

    return await _cached(("levels", site, days), 600 if days <= 4 else 3 * 3600, fetch)


async def threshold(c: httpx.AsyncClient, site: str) -> float | None:
    """The gauge's own q95 over the last 12 months (the model's "usual high mark"). Cached on disk for 30 days."""
    cache = _read("thresholds.json", {})
    hit = cache.get(site)
    if hit and time.time() - hit["at"] < 30 * 86400:
        return hit["q95"]
    rs = await levels(c, site, 365)
    if len(rs) < 24 * 60:  # under ~2 months of readings: no honest mark
        return None
    q95 = quantiles([r["value"] for r in rs], n=20)[-1]
    cache[site] = {"q95": q95, "at": time.time(), "n": len(rs)}
    _write("thresholds.json", cache)
    return q95


async def rain_in(c: httpx.AsyncClient, lat: float, lon: float) -> dict[datetime, float]:
    """Hourly precipitation in inches for the last 92 days (Open-Meteo model analysis, mm -> in)."""
    async def fetch():
        r = await c.get(f"{METEO}/forecast", params={"latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "hourly": "precipitation",
                                                      "past_days": 92, "forecast_days": 1, "timezone": "GMT"})
        r.raise_for_status()
        h = r.json()["hourly"]
        return {datetime.fromisoformat(t).replace(tzinfo=timezone.utc): (p or 0.0) / MM_PER_IN for t, p in zip(h["time"], h["precipitation"])}

    return await _cached(("rain", round(lat, 2), round(lon, 2)), 3600, fetch)


async def elevation_m(c: httpx.AsyncClient, lat: float, lon: float) -> float | None:
    async def fetch():
        r = await c.get(f"{METEO}/elevation", params={"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}"})
        r.raise_for_status()
        return float(r.json()["elevation"][0])

    try:
        return await _cached(("elev", round(lat, 3), round(lon, 3)), 30 * 86400, fetch)
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return None


# ------------------------------------------------------------------ features (same rules as app.agents.ingestion)
RainIndex = tuple[list[datetime], list[float]]  # sorted hours, running totals


def rain_index(rain: dict[datetime, float]) -> RainIndex:
    ts = sorted(rain)
    return ts, list(accumulate((rain[t] for t in ts), initial=0.0))


def features(site: str, rows: list[dict], rain: dict[datetime, float] | RainIndex, thr: float, t: datetime, elev: float | None) -> FeatureVector | None:
    """Feature vector at issue time t from readings at or before t only. None = gauge silent for more than 6 h.
    rows: hourly, sorted by ts. Binary search keeps building thousands of training rows fast."""
    cut = bisect_right(rows, t, key=lambda r: r["ts"])
    if not cut or rows[cut - 1]["ts"] < t - STALE_AFTER:
        return None
    now = rows[cut - 1]
    b = bisect_right(rows, now["ts"] - timedelta(hours=3), 0, cut, key=lambda r: r["ts"])
    trend = (now["value"] - rows[b - 1]["value"]) / 3 if b else 0.0
    seen = rows[bisect_left(rows, now["ts"] - timedelta(hours=73), 0, cut, key=lambda r: r["ts"]):cut]  # all history() reads
    ts, cum = rain if isinstance(rain, tuple) else rain_index(rain)

    def rsum(h):  # rain over (t - h, t]
        lo, hi = bisect_right(ts, t - timedelta(hours=h)), bisect_right(ts, t)
        return cum[hi] - cum[lo] if hi > lo else None

    return FeatureVector(zone_id=site, issue_ts=t, level_m=now["value"] - thr, level_trend_m_per_h=trend,
                         rain_6h=rsum(6), rain_24h=rsum(24), rain_72h=rsum(72), hand_m=None, elevation_m=elev,
                         is_simulated=False, **history(seen, thr))


def training_rows(site: str, rows: list[dict], rain: dict[datetime, float], thr: float, elev: float | None) -> pd.DataFrame:
    """Issue time every STEP_H hours; targets = level k hours later minus q95, for each trained lead. Rows lacking any target are dropped."""
    if not rows or not rain:
        return pd.DataFrame()
    at = {r["ts"]: r["value"] for r in rows}
    idx = rain_index(rain)
    start = max(rows[0]["ts"], idx[0][0]) + timedelta(hours=72)
    end = rows[-1]["ts"] - timedelta(hours=max(LEADS))
    out = []
    t = start
    while t <= end:
        fv = features(site, rows, idx, thr, t, elev)
        ys = [at.get(t + timedelta(hours=k)) for k in LEADS]
        if fv is not None and all(y is not None for y in ys):
            out.append([*to_row(fv).iloc[0].tolist(), *(y - thr for y in ys), t, site])
        t += timedelta(hours=STEP_H)
    return pd.DataFrame(out, columns=[*FEATURES, *(f"y{k}" for k in LEADS), "t", "site"])


# ------------------------------------------------------------------ models per region
def _model_path(region: str) -> Path:
    return DIR / f"model_{region}.joblib"


_models: dict[str, tuple[float, Forecaster, dict]] = {}


def champion(region: str) -> tuple[Forecaster, dict]:
    """The promoted live model for a region, else the SF2Bench base model."""
    p = _model_path(region)
    mtime = p.stat().st_mtime if p.exists() else 0.0
    hit = _models.get(region)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]
    if p.exists():
        f, meta = Forecaster(joblib.load(p)), _read(f"model_{region}.json", {})
    else:
        f, meta = Forecaster.load(), {"version": VERSION, "base": True}
    _models[region] = (mtime, f, meta)
    return f, meta


def pinball(models: dict, X: pd.DataFrame, Y: pd.DataFrame) -> float:
    """Mean quantile loss over every (lead, quantile) model: the number the promotion compares."""
    losses = []
    for (k, q), m in models.items():
        d = Y[f"y{k}"].to_numpy() - m.predict(X)
        losses.append(np.mean(np.maximum(q * d, (q - 1) * d)))
    return float(np.mean(losses))


def update(base: dict, df: pd.DataFrame, now: datetime) -> dict:
    """Continue boosting every base model on the live rows; evaluate on the newest EVAL_DAYS. Pure: no I/O."""
    cut = now - timedelta(days=EVAL_DAYS)
    ev = df[df["t"] >= cut]
    tr = df[df["t"] + timedelta(hours=max(LEADS)) < cut]  # purge: no training target may fall inside the evaluation window
    res = {"n_train": len(tr), "n_eval": len(ev), "gauges": int(df["site"].nunique()) if len(df) else 0, "promoted": False}
    if len(tr) < MIN_ROWS or len(ev) < MIN_ROWS // 5:
        res["reason"] = "not enough live rows yet"
        return res
    new = {}
    for (k, q), b in base.items():
        params = {**{p: v for p, v in b.params.items() if p not in ("num_iterations", "metric")}, "objective": "quantile", "alpha": q, "verbose": -1}
        new[(k, q)] = lgb.train(params, lgb.Dataset(tr[FEATURES], tr[f"y{k}"]), num_boost_round=ROUNDS, init_model=b, keep_training_booster=True)
    res["loss_current"], res["loss_new"] = pinball(base, ev[FEATURES], ev), pinball(new, ev[FEATURES], ev)
    res["promoted"] = res["loss_new"] <= res["loss_current"] * PROMOTE_IF
    res["models"] = new if res["promoted"] else None
    return res


# ------------------------------------------------------------------ tracking, learning loop
def tracked() -> dict:
    return _read("tracked.json", {})


def track(site: dict) -> None:
    t = tracked()
    if site["id"] not in t and len(t) < MAX_TRACKED:
        t[site["id"]] = {"name": site["name"], "lat": site["lat"], "lon": site["lon"], "region": region_of(site["lat"], site["lon"])}
        _write("tracked.json", t)


async def seed_sf(c: httpx.AsyncClient) -> None:
    """Start tracking South Florida's own gauges: the focus region learns first."""
    x0, y0, x1, y1 = SF_BBOX
    for s in await sites_near(c, (y0 + y1) / 2, (x0 + x1) / 2, radius_km=95):
        if region_of(s["lat"], s["lon"]) == "sf":
            track(s)


async def learn(region: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=120, headers=UA, follow_redirects=True) as c:
        if region == "sf":
            await seed_sf(c)
        frames = []
        for sid, s in tracked().items():
            if s["region"] != region:
                continue
            try:
                thr = await threshold(c, sid)
                if thr is None:
                    continue
                rows, rain, elev = await levels(c, sid, 95), await rain_in(c, s["lat"], s["lon"]), await elevation_m(c, s["lat"], s["lon"])
                frames.append(await asyncio.to_thread(training_rows, sid, rows, rain, thr, elev))
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.info("live learn: gauge %s skipped (%s)", sid, type(e).__name__)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=[*FEATURES, "t", "site"])
    base, meta = champion(region)
    res = await asyncio.to_thread(update, base.models, df, now)
    if res["promoted"]:
        version = f"{VERSION}+live-{region}-{now:%Y%m%d}"
        DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(res["models"], _model_path(region))
        _write(f"model_{region}.json", {"version": version, "trained_at": now.isoformat(), "from": meta.get("version"),
                                        "n_train": res["n_train"], "gauges": res["gauges"], "loss_eval": res["loss_new"]})
        res["version"] = version
    res.pop("models", None)
    run = {"at": now.isoformat(), "region": region, **res}
    with (DIR / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, default=str) + "\n")
    log.info("live learn %s: %s", region, {k: v for k, v in run.items() if k != "at"})
    return run


async def learn_loop(every_h: float) -> None:
    """Background: one learning pass per region every `every_h` hours. Failures never stop the loop."""
    while True:
        for region in ("sf", "us"):
            try:
                await learn(region)
            except Exception as e:
                log.warning("live learn %s failed: %s", region, type(e).__name__)
        await asyncio.sleep(every_h * 3600)


def status() -> dict:
    runs = [json.loads(ln) for ln in (DIR / "runs.jsonl").read_text(encoding="utf-8").splitlines()] if (DIR / "runs.jsonl").exists() else []
    t = tracked()
    return {"regions": {r: {**champion(r)[1], "gauges_tracked": sum(1 for s in t.values() if s["region"] == r),
                            "last_run": next((x for x in reversed(runs) if x["region"] == r), None)} for r in ("sf", "us")}}


# ------------------------------------------------------------------ forecast at a point
async def forecast_at(lat: float, lon: float) -> dict | None:
    """Our experimental forecast at the nearest active USGS gauge, or None when no usable gauge is within SEARCH_KM."""
    async with httpx.AsyncClient(timeout=60, headers=UA, follow_redirects=True) as c:
        for site in (await sites_near(c, lat, lon))[:3]:  # nearest few: some report no recent data
            thr = await threshold(c, site["id"])
            if thr is None:
                continue
            rows = await levels(c, site["id"], 4)
            rain, elev = await rain_in(c, site["lat"], site["lon"]), await elevation_m(c, site["lat"], site["lon"])
            now = datetime.now(timezone.utc)
            fv = features(site["id"], rows, rain, thr, now, elev)
            if fv is None:
                continue
            region = region_of(site["lat"], site["lon"])
            model, meta = champion(region)
            risk = derive(model.forecast(fv.model_copy(update={"issue_ts": now})))
            track(site)  # people looked here: learn this gauge too
            return {
                "gauge": {"id": site["id"], "name": site["name"], "km": site["km"], "lat": site["lat"], "lon": site["lon"],
                          "url": f"https://waterdata.usgs.gov/monitoring-location/{site['id']}/"},
                "region": region, "validated": False, "model": meta.get("version", VERSION), "trained_at": meta.get("trained_at"),
                "level_vs_mark_ft": round(fv.level_m, 2), "probability": risk.probability, "severity": risk.severity,
                "onset": risk.onset.likely.isoformat() if risk.onset else None, "peak": risk.peak.likely.isoformat() if risk.peak else None,
                "issued": now.isoformat(),
            }
    return None
