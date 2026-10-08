"""Accounts: pure alert planning, mail outbox, tokens and the endpoints that answer before touching the database."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import accounts as A
from app.config import settings
from app.main import app

TS = datetime(2022, 11, 9, 6, tzinfo=timezone.utc)
FEED = [{"issue_ts": TS, "zone_id": "z1", "alert_text": "High-water episode possible, Miami.", "probability": 0.89, "severity": "high", "is_simulated": True},
        {"issue_ts": TS, "zone_id": "z2", "alert_text": "Alert, Davie.", "probability": None, "severity": None, "is_simulated": True}]


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!!")
    monkeypatch.setattr(settings, "google_client_id", "client.apps.googleusercontent.com")


def test_replay_plan_only_notifies_followers_and_labels_it_simulated():
    out = A.plan_replay(FEED, {"z1": [7, 8]}, {"z1": "Miami"}, 5, "Hurricane Nicole")
    assert [o["user_id"] for o in out] == [7, 8] and all(o["kind"] == "replay" for o in out)
    assert "Simulated replay" in out[0]["title"] and "not a live warning" in out[0]["body"] and "89%" in out[0]["body"]
    assert out[0]["key"] == "replay:5:z1:" + TS.isoformat()
    assert A.plan_replay(FEED, {}, {}, 5, "x") == []


def al(event="Flood Warning", level=3, ends="2022-11-10T00:00Z"):
    return {"event": event, "level": level, "effective": "2022-11-09T00:00Z", "ends": ends, "headline": "Flood Warning issued for Miami-Dade"}


def test_live_plan_matches_county_skips_advisories_and_feed_down_sends_nothing():
    uz = {1: [("a", "Miami", "Miami-Dade")], 2: [("b", "Davie", "Broward")]}
    out = A.plan_live({"Miami-Dade": [al(), al("Coastal Flood Advisory", level=1)], "Broward": []}, uz)
    assert len(out) == 1 and out[0]["user_id"] == 1 and "Miami" in out[0]["body"] and "separate from the KADAL flood model" in out[0]["body"]
    assert A.plan_live(None, uz) == []  # unknown is never an all-clear, and never an alert either


def test_email_goes_to_outbox_without_smtp(monkeypatch):
    out = Path(__file__).parent / "_outbox_test"
    monkeypatch.setattr(A, "OUTBOX", out)
    monkeypatch.setattr(settings, "smtp_host", "")
    try:
        assert asyncio.run(A.send_email("a@b.co", "Subject", "Body")) == "outbox"
        f = next(out.glob("*.txt"))
        assert "Subject: Subject" in f.read_text(encoding="utf-8")
    finally:
        for f in out.glob("*"):
            f.unlink()
        out.rmdir()


def test_endpoints_reject_without_valid_token(secret):
    c = TestClient(app)
    assert c.get("/api/me").status_code == 401
    assert c.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    expired = A.jwt.encode({"sub": "1", "exp": 1}, settings.jwt_secret, algorithm="HS256")
    assert c.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = A.jwt.encode({"sub": "1"}, "another-secret-another-secret-another!!", algorithm="HS256")
    assert c.put("/api/me/zones", json={"zone_ids": []}, headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_google_login_rejects_unverifiable_credential_and_config_hides_client_id_when_off(secret, monkeypatch):
    def bad(_):
        raise ValueError("wrong audience")
    monkeypatch.setattr(A, "verify_google", bad)
    c = TestClient(app)
    assert c.post("/api/auth/google", json={"credential": "x" * 40}).status_code == 401
    assert c.get("/api/auth/config").json() == {"enabled": True, "google_client_id": "client.apps.googleusercontent.com"}
    monkeypatch.setattr(settings, "jwt_secret", "")
    assert c.get("/api/auth/config").json() == {"enabled": False, "google_client_id": ""}
    assert c.post("/api/auth/google", json={"credential": "x" * 40}).status_code == 503
