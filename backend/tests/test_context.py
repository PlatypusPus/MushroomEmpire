"""Live hazard context: parsers on SAVED REAL responses (tests/fixtures), the level, agreement flag, cache/staleness, endpoints, assistant."""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_backend import T0, synthetic_snapshot

from app import assistant as A
from app import context as C
from app import replay
from app.llm.client import ChatResult, LLMUnavailable
from app.main import app
from app.pipeline import run_tick

FX = Path(__file__).parent / "fixtures"
ALERTS = json.loads((FX / "nws_alerts_real.json").read_text())
STORMS = json.loads((FX / "nhc_storms_real.json").read_text())
RSS = (FX / "nhc_rss_real.xml").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)


def alert(event, same="012086", status="Actual", msg="Alert", ends=None, headline=""):
    return {"properties": {"event": event, "status": status, "messageType": msg, "severity": "Severe", "certainty": "Likely", "effective": "2026-10-08T12:00:00-04:00",
                           "ends": ends or "2026-10-09T12:00:00-04:00", "headline": headline, "geocode": {"SAME": [same]}}}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    f = Path(__file__).parent / "_ctx_test_cache.json"  # not tmp_path: pytest's temp base is not writable in every environment
    f.unlink(missing_ok=True)
    C._cache.clear()
    monkeypatch.setattr(C, "CACHE_FILE", f)
    yield
    C._cache.clear()
    f.unlink(missing_ok=True)


def test_real_alert_fixture_parses_and_only_relevant_products_survive():
    out = C.parse_alerts(ALERTS, now=NOW)
    flat = [a for v in out.values() for a in v]
    assert all(a["event"].lower() in C.EVENT_LEVEL for a in flat)  # rip current statements etc. are dropped
    assert all(a["level"] in (1, 2, 3, 4) for a in flat)


def test_levels_counties_expiry_status_and_flash_flood_emergency():
    feats = [alert("Flood Warning"), alert("Flood Watch", same="012011"), alert("Coastal Flood Advisory", ends="2026-10-08T10:00:00+00:00"),  # expired
             alert("Hurricane Warning", status="Test"), alert("Flood Warning", msg="Cancel"), alert("Hurricane Warning", same="012045"),  # wrong county
             alert("Rip Current Statement"), alert("Flash Flood Warning", headline="FLASH FLOOD EMERGENCY for Miami")]
    out = C.parse_alerts({"features": feats}, now=NOW)
    assert sorted(a["level"] for a in out["Miami-Dade"]) == [3, 4] and [a["level"] for a in out["Broward"]] == [2]
    assert out["Miami-Dade"][0]["level"] == 4  # sorted most severe first


def test_real_storm_fixture_distance_basin_and_heading():
    s = C.parse_storms(STORMS)
    assert s["other_basin_count"] == 2 and [x["name"] for x in s["storms"]] == ["Isaias"]
    assert 900 < s["storms"][0]["distance_km"] < 1200 and s["storms"][0]["heading_toward_region"] is True


@pytest.mark.parametrize("dist,toward,expect", [(200, False, 3), (500, True, 2), (500, False, 1), (1200, True, 1), (2500, True, 0)])
def test_cyclone_level_rule(dist, toward, expect):
    st = [{"classification": "HU", "name": "X", "distance_km": dist, "heading_toward_region": toward}]
    assert C.cyclone_level(st)[0] == expect
    assert C.cyclone_level([{**st[0], "classification": "LO"}])[0] == 0  # not a tropical cyclone


def test_bulletins_keep_official_links_only_and_strip_markup():
    items = C.parse_bulletins(RSS)
    assert items and all(i["link"].startswith("https://www.nhc.noaa.gov/") for i in items)
    evil = RSS.replace("</channel>", "<item><title>&lt;b&gt;bold&lt;/b&gt;</title><link>https://evil.example/x</link></item></channel>")
    assert all("evil" not in i["link"] for i in C.parse_bulletins(evil, limit=50))
    assert C.clean("<script>alert(1)</script>Hello\x00\n  world" + "x" * 500, 40) == "alert(1) Hello world" + "x" * 20


def test_forecast_summary_uses_the_next_hours_only():
    base = NOW.replace(minute=0)
    times = [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(-5, 72)]
    f = C.parse_forecast({"hourly": {"time": times, "precipitation": [1.0] * len(times), "pressure_msl": [1010.0 - i * 0.1 for i in range(len(times))],
                                     "wind_gusts_10m": [30.0 + i for i in range(len(times))]}, "hourly_units": {}}, now=NOW)
    assert f["rain_next_24h_mm"] == 24.0 and f["rain_next_72h_mm"] == 72.0 and f["max_gust_next_48h_kmh"] > 30


def test_unknown_is_never_none():
    lv = C.hazard_level(None, None)
    assert lv["level"] is None and "unavailable" in lv["label"] and all(c["level"] is None for c in lv["counties"].values())
    ok = C.hazard_level({"Miami-Dade": [], "Broward": []}, {"storms": [], "other_basin_count": 0})
    assert ok["level"] == 0 and ok["label"] == "none"


def test_level_combines_alerts_and_cyclone_proximity():
    al = {"Miami-Dade": [{"event": "Flood Watch", "level": 2}], "Broward": []}
    st = {"storms": [{"classification": "HU", "name": "Isaias", "distance_km": 250, "heading_toward_region": True}]}
    lv = C.hazard_level(al, st)
    assert lv["counties"]["Miami-Dade"]["level"] == 3 and lv["counties"]["Broward"]["level"] == 3 and lv["level"] == 3
    assert any("Isaias" in d for d in lv["counties"]["Broward"]["drivers"])


@pytest.mark.parametrize("level,p,code", [(None, 0.9, "context_unavailable"), (4, None, "no_model_data"), (3, 0.9, "agree_warning"), (2, 0.9, "model_with_watch"),
                                          (1, 0.9, "model_only"), (3, 0.05, "official_only"), (2, 0.05, "official_watch_only"), (0, 0.05, "none")])
def test_agreement_matrix(level, p, code):
    assert C.agreement(level, p, 0.27)["code"] == code


def patch_fetch(monkeypatch, fail=()):
    calls = []

    async def fake(client, name):
        calls.append(name)
        if name in fail:
            raise ConnectionError("no network")
        return {"alerts": ALERTS, "storms": STORMS, "bulletins": RSS, "forecast": {"hourly": {"time": [], "precipitation": [], "pressure_msl": [], "wind_gusts_10m": []}}}[name]

    monkeypatch.setattr(C, "_fetch", fake)
    return calls


def test_context_caches_within_ttl_and_refreshes_on_force(monkeypatch):
    calls = patch_fetch(monkeypatch)
    a = asyncio.run(C.get_context())
    asyncio.run(C.get_context())
    assert a["level"] is not None and a["partial"] == [] and len(calls) == 4
    asyncio.run(C.get_context(force=True))
    assert len(calls) == 8


def test_offline_gives_level_none_not_zero_and_recovers(monkeypatch):
    patch_fetch(monkeypatch, fail=("alerts", "storms", "bulletins", "forecast"))
    c = asyncio.run(C.get_context())
    assert c["level"] is None and set(c["partial"]) == {"alerts", "storms", "bulletins", "forecast"} and c["sources"]["alerts"]["error"]
    patch_fetch(monkeypatch)
    assert asyncio.run(C.get_context(force=True))["level"] is not None


def test_alert_data_that_is_too_old_is_not_trusted(monkeypatch):
    patch_fetch(monkeypatch)
    first = asyncio.run(C.get_context())
    assert first["level"] is not None
    patch_fetch(monkeypatch, fail=("alerts",))
    C._cache["alerts"]["at"] = time.time() - C.TTL["alerts"] * C.STALE_FACTOR - 5
    c = asyncio.run(C.get_context(force=True))
    assert c["level"] is None and "alerts" in c["partial"] and c.get("last_recorded")  # last recorded level is shown as recorded, never as live


def test_endpoints_and_agreement(monkeypatch):
    patch_fetch(monkeypatch)
    replay._snaps[996] = synthetic_snapshot()
    c = TestClient(app)
    ctx = c.get("/api/context").json()
    assert ctx["live"] is True and "Miami-Dade" in ctx["counties"] and ctx["cyclones"][0]["name"] == "Isaias"
    z = c.get("/api/zones/A/context?event_id=996").json()
    assert z["agreement"] is None  # replay is historical: no agreement unless a live probability is supplied
    z2 = c.get("/api/zones/A/context?event_id=996&model_probability=0.9").json()
    assert z2["agreement"]["code"] in ("agree_warning", "model_with_watch", "model_only")
    assert c.get("/api/zones/NOPE/context?event_id=996").status_code == 404


def ask(q, ctx, llm, monkeypatch):
    async def fn():
        return ctx
    snap = synthetic_snapshot()
    monkeypatch.setattr(A, "chat", llm)
    return asyncio.run(A.ask(q, run_tick(snap, T0), snap.zones, [], None, fn))


def test_assistant_answers_alert_questions_from_live_context(monkeypatch):
    patch_fetch(monkeypatch)
    ctx = asyncio.run(C.get_context())

    async def down(messages, *, system=None, **kwargs):
        raise LLMUnavailable("down")
    r = ask("Are there any cyclones or warnings?", ctx, down, monkeypatch)
    assert r["intent"] == "context" and r["source"] == "template"
    assert "Isaias" in r["answer"] and "separate from the flood model" in r["answer"]


def test_assistant_never_says_no_warnings_when_data_is_unavailable(monkeypatch):
    async def liar(messages, *, system=None, **kwargs):
        return ChatResult(text="There are no active warnings.", model="fake")
    r = ask("Are there any warnings?", {"level": None, "counties": {}, "last_recorded": None}, liar, monkeypatch)
    assert r["source"] == "template" and "unavailable" in r["answer"]
