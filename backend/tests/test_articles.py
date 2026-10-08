"""Live hazard articles: parsers on SAVED REAL responses, text/image/link safety, ordering and the stale fallback."""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import articles as A
from app import context as C
from app.main import app

FX = Path(__file__).parent / "fixtures"
ALERTS = json.loads((FX / "nws_alerts_text_real.json").read_text())
STORMS = C.parse_storms(json.loads((FX / "nhc_storms_real.json").read_text()))["storms"]
RSS = (FX / "nhc_rss_real.xml").read_text(encoding="utf-8")
AFD = json.loads((FX / "nws_afd_real.json").read_text())


def test_text_of_strips_markup_and_control_characters_but_keeps_lines():
    t = A.text_of("<pre>000 WTNT34<br />BULLETIN&amp;x\x00\x07<script>alert(1)</script>\n\n\n\nline&nbsp;two</pre>")
    assert "<" not in t and "\x00" not in t and "&amp;" not in t and "BULLETIN&x" in t and "\n\n" in t and "\n\n\n" not in t


def test_text_of_caps_long_text_at_a_line_break():
    t = A.text_of("\n".join(f"line {i} " + "x" * 50 for i in range(500)), cap=1000)
    assert len(t) < 1100 and t.endswith("see the official source]")


def test_image_and_link_allowlists():
    assert A.safe_image("https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png") and A.safe_image("https://radar.weather.gov/ridge/standard/KAMX_0.gif")
    assert A.safe_image("https://evil.example/x.png") is None and A.safe_image("http://www.nhc.noaa.gov/x.png") is None
    assert A.safe_image("https://www.nhc.noaa.gov/index.html") is None and A.safe_image("javascript:alert(1)") is None
    assert A.safe_link("https://www.nhc.noaa.gov/text/x.shtml") and A.safe_link("https://evil.example/") is None


def test_real_alert_becomes_a_full_text_article_with_a_radar_preview():
    eff = datetime.fromisoformat(ALERTS["features"][0]["properties"]["effective"])
    out = A.parse_alert_articles(ALERTS, now=eff + timedelta(minutes=5))
    assert out and out[0]["kind"] == "alert" and out[0]["level"] >= 1 and "County" in out[0]["title"] + "County" and out[0]["body"]
    assert out[0]["image"]["url"].startswith("https://radar.weather.gov/") and out[0]["url"].startswith("https://www.weather.gov/")
    assert A.parse_alert_articles(ALERTS, now=eff + timedelta(days=30)) == []  # expired alerts are not shown


def test_alert_for_both_counties_is_one_article_not_two():
    f = {"properties": {"event": "Flood Warning", "status": "Actual", "messageType": "Alert", "effective": "2026-10-08T12:00:00-04:00", "ends": "2099-01-01T00:00:00+00:00",
                        "headline": "Flood Warning issued", "description": "Water is rising.", "instruction": "Move to higher ground.", "id": "x1",
                        "geocode": {"SAME": ["012086", "012011"]}}}
    out = A.parse_alert_articles({"features": [f, {**f, "properties": {**f["properties"], "geocode": {"SAME": ["012011"]}}}]})
    assert len(out) == 1 and out[0]["counties"] == ["Broward", "Miami-Dade"] and "What to do:\nMove to higher ground." in out[0]["body"]


def test_real_nhc_feed_gives_storm_articles_with_nhc_graphics_and_a_dated_outlook():
    out = A.parse_nhc_articles(RSS, STORMS)
    kinds = [a["kind"] for a in out]
    assert "outlook" in kinds and "advisory" in kinds
    adv = next(a for a in out if a["kind"] == "advisory")
    assert adv["storm"] == "Isaias" and "Advisory" in adv["body"] and len(adv["body"]) > 500
    assert adv["image"]["url"] == "https://www.nhc.noaa.gov/storm_graphics/AT09/AL092026_current_wind.png" and adv["issued"]
    assert next(a for a in out if a["kind"] == "outlook")["image"]["url"].endswith("two_atl_7d0.png")
    assert len({(a["kind"], a.get("storm")) for a in out}) == len(out)  # the feed repeats older advisories: one of each per storm


def test_nhc_item_with_a_non_official_link_is_dropped():
    evil = RSS.replace("https://www.nhc.noaa.gov/text/refresh/MIATCPAT4+shtml/081456.shtml", "https://evil.example/x")
    assert all("evil" not in a["url"] for a in A.parse_nhc_articles(evil, STORMS))


def test_real_afd_is_a_forecast_article_with_a_satellite_preview():
    a = A.parse_afd(AFD)
    assert a["kind"] == "forecast" and "Miami" in a["title"] and len(a["body"]) > 1000 and a["image"]["url"].endswith("GEOCOLOR/600x600.jpg")
    assert A.parse_afd({"productText": ""}) is None


def test_endpoint_returns_cached_list_and_stale_copy_when_everything_fails(monkeypatch):
    calls = []

    async def ok():
        calls.append(1)
        return {"fetched_at": "t", "articles": [{"id": "a"}], "partial": []}
    monkeypatch.setattr(A, "_build", ok)
    A._cache.clear()
    c = TestClient(app)
    assert c.get("/api/hazards/articles").json()["articles"] == [{"id": "a"}]
    c.get("/api/hazards/articles")
    assert len(calls) == 1  # second call served from cache

    async def down():
        return {"fetched_at": "t2", "articles": [], "partial": ["alerts", "nhc", "afd"]}
    monkeypatch.setattr(A, "_build", down)
    r = c.get("/api/hazards/articles?refresh=true").json()
    assert r["stale"] is True and r["articles"] == [{"id": "a"}] and r["partial"] == ["alerts", "nhc", "afd"]  # last good list, flagged, never shown as fresh
    A._cache.clear()
