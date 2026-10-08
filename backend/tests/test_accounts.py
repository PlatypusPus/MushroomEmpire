"""Accounts: pure alert planning, mail outbox, tokens and the endpoints that answer before touching the database."""
import asyncio
import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
    for k in ("google_client_id", "google_client_secret", "github_client_id", "github_client_secret"):
        monkeypatch.setattr(settings, k, "")


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


def client():
    return TestClient(app, follow_redirects=False)


@pytest.fixture(params=["google", "github"])
def prov(request, secret, monkeypatch):
    monkeypatch.setattr(settings, f"{request.param}_client_secret", "s")
    monkeypatch.setattr(settings, f"{request.param}_client_id", "cid")
    return request.param


def test_start_redirects_to_the_provider_with_pkce_state_and_a_signed_httponly_cookie(prov):
    r = client().get(f"/api/auth/{prov}/start")
    assert r.status_code == 302
    u = urlparse(r.headers["location"])
    q = parse_qs(u.query)
    assert u.netloc == {"google": "accounts.google.com", "github": "github.com"}[prov] and q["response_type"] == ["code"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == [f"http://localhost:5173/api/auth/{prov}/callback"]
    tx = A.jwt.decode(r.cookies[A.TX_COOKIE], settings.jwt_secret, algorithms=["HS256"])
    assert tx["s"] == q["state"][0] and tx["p"] == prov
    assert base64.urlsafe_b64encode(hashlib.sha256(tx["v"].encode()).digest()).rstrip(b"=").decode() == q["code_challenge"][0]  # challenge matches the verifier
    assert "httponly" in r.headers["set-cookie"].lower()


def test_callback_success_signs_up_and_returns_our_token_in_the_fragment(prov, monkeypatch):
    c = client()
    state = parse_qs(urlparse(c.get(f"/api/auth/{prov}/start").headers["location"]).query)["state"][0]
    seen = {}

    async def fake_identity(provider, code, verifier):
        seen.update(provider=provider, code=code, verifier=verifier)
        return {"sub": f"{provider}:1", "email": "a@b.co", "name": "A"}

    async def fake_login(info):
        return type("U", (), {"id": 42})(), True
    monkeypatch.setattr(A, "identity", fake_identity)
    monkeypatch.setattr(A, "login_user", fake_login)
    r = c.get(f"/api/auth/{prov}/callback?code=abc&state={state}")
    loc = r.headers["location"]
    assert r.status_code == 302 and loc.startswith("http://localhost:5173/account#token=") and loc.endswith("&new=1")
    assert A.jwt.decode(parse_qs(urlparse(loc).fragment)["token"][0], settings.jwt_secret, algorithms=["HS256"])["sub"] == "42"
    assert seen["provider"] == prov and seen["code"] == "abc" and len(seen["verifier"]) > 40  # the PKCE verifier from the cookie reached the exchange


def test_callback_rejects_wrong_state_missing_cookie_cancel_and_a_cookie_from_another_provider(prov, monkeypatch):
    called = []

    async def ident(provider, code, verifier):
        called.append(1)
        return {}
    monkeypatch.setattr(A, "identity", ident)
    c = client()
    c.get(f"/api/auth/{prov}/start")
    assert c.get(f"/api/auth/{prov}/callback?code=abc&state=forged").headers["location"].endswith("/account?error=signin_failed")
    assert client().get(f"/api/auth/{prov}/callback?code=abc&state=s").headers["location"].endswith("/account?error=signin_failed")  # no cookie
    assert c.get(f"/api/auth/{prov}/callback?error=access_denied").headers["location"].endswith("/account?error=cancelled")
    other = "github" if prov == "google" else "google"
    monkeypatch.setattr(settings, f"{other}_client_secret", "s")
    monkeypatch.setattr(settings, f"{other}_client_id", "cid")
    state = parse_qs(urlparse(c.get(f"/api/auth/{prov}/start").headers["location"]).query)["state"][0]
    assert c.get(f"/api/auth/{other}/callback?code=abc&state={state}").headers["location"].endswith("/account?error=signin_failed")  # flow started for another provider
    assert called == []  # a forged, cancelled or mismatched callback never reaches the provider


def test_callback_rejects_an_identity_the_provider_cannot_verify(prov, monkeypatch):
    c = client()
    state = parse_qs(urlparse(c.get(f"/api/auth/{prov}/start").headers["location"]).query)["state"][0]

    async def bad(provider, code, verifier):
        raise ValueError("no verified primary email")
    monkeypatch.setattr(A, "identity", bad)
    assert c.get(f"/api/auth/{prov}/callback?code=abc&state={state}").headers["location"].endswith("/account?error=signin_failed")


def test_github_identity_needs_a_verified_primary_email(monkeypatch):
    class R:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    def run(emails):
        class C:
            def __init__(self, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def get(self, path):
                return R({"id": 7, "login": "octo", "name": None} if path == "/user" else emails)
        monkeypatch.setattr(A.httpx, "AsyncClient", C)
        return asyncio.run(A.github_identity("tok"))
    assert run([{"email": "x@y.co", "primary": False, "verified": True}, {"email": "me@y.co", "primary": True, "verified": True}]) == {"sub": "github:7", "email": "me@y.co", "name": "octo"}
    with pytest.raises(ValueError):
        run([{"email": "me@y.co", "primary": True, "verified": False}])  # an unverified address could belong to someone else


def test_config_lists_only_configured_providers(secret, monkeypatch):
    assert client().get("/api/auth/config").json() == {"enabled": False, "providers": []}
    monkeypatch.setattr(settings, "github_client_id", "cid")
    monkeypatch.setattr(settings, "github_client_secret", "s")
    assert client().get("/api/auth/config").json() == {"enabled": True, "providers": [{"id": "github", "label": "GitHub", "login_url": "/api/auth/github/start"}]}
    assert client().get("/api/auth/google/start").status_code == 503 and client().get("/api/auth/gitlab/start").status_code == 404
    monkeypatch.setattr(settings, "jwt_secret", "")
    assert client().get("/api/auth/github/start").status_code == 503
