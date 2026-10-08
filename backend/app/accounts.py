"""Accounts: Google OAuth sign-in, zone subscriptions, alert emails.

* Sign-in and sign-up are one flow: OAuth 2.0 authorization code + PKCE. /auth/google/start redirects to Google,
  /auth/google/callback exchanges the code server-side (client secret never reaches the browser), verifies the signed ID token
  (signature, audience, verified email), creates the user on first sign-in, and hands the browser our own short-lived JWT.
  Sign-in is on only when the client id and secret are set. No passwords are stored.
* Alerts, two kinds, always labelled so a replay is never mistaken for a live warning:
    replay: a zone the user follows crossed the validated alert threshold in a (historical, simulated) replay session
    live:   an official NWS/NHC watch or warning is active for the county of a zone the user follows (not from the model)
* (user, key) is unique, so polling and replay scrubbing never notify twice. New alerts for a user go out as ONE email per run.
* No SMTP configured: the mail is written to backend/outbox/ and recorded as status "outbox".
"""
import asyncio
import base64
import hashlib
import logging
import secrets
import smtplib
import time
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db.models import AlertDelivery, Subscription, User, Zone
from app.db.session import SessionLocal

log = logging.getLogger("coastguard.accounts")
router = APIRouter()
OUTBOX = Path(__file__).resolve().parent.parent / "outbox"
MIN_LIVE_LEVEL = 2  # official watch or warning (levels: 1 advisory, 2 watch, 3 warning, 4 emergency)


PROVIDERS = {
    "google": {"label": "Google", "auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token",
               "scope": "openid email profile", "extra": {"prompt": "select_account"}},
}  # ponytail: one provider; the routes already take {provider}, so another is one entry here plus an identity() branch


def _creds(provider: str) -> tuple[str, str]:
    return getattr(settings, f"{provider}_client_id"), getattr(settings, f"{provider}_client_secret")


def provider_on(provider: str) -> bool:
    return provider in PROVIDERS and bool(settings.jwt_secret and all(_creds(provider)))


def enabled() -> bool:
    return any(provider_on(p) for p in PROVIDERS)


# ------------------------------------------------------------------ sessions
def issue_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_ttl_h)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def verify_google(credential: str) -> dict:
    from google.auth.transport import requests as grequests
    from google.oauth2 import id_token

    info = id_token.verify_oauth2_token(credential, grequests.Request(), settings.google_client_id)
    if not info.get("email_verified"):
        raise ValueError("email not verified")
    return info


async def current_user(authorization: Annotated[str | None, Header()] = None) -> User:
    if not settings.jwt_secret:
        raise HTTPException(503, "accounts are not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing token")
    try:
        uid = int(jwt.decode(authorization[7:], settings.jwt_secret, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "invalid or expired token")
    async with SessionLocal() as db:
        user = await db.get(User, uid)
    if user is None:
        raise HTTPException(401, "unknown user")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def _user_json(u: User, zone_ids: list[str]) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "email_alerts": u.email_alerts, "zone_ids": zone_ids}


async def _zone_ids(db, uid: int) -> list[str]:
    return sorted((await db.execute(select(Subscription.zone_id).where(Subscription.user_id == uid))).scalars())


class ZoneList(BaseModel):
    zone_ids: list[str] = Field(max_length=120)


class Prefs(BaseModel):
    email_alerts: bool


TX_COOKIE = "shroomcast_oauth"


def _redirect_uri(provider: str) -> str:
    return f"{settings.app_origin.rstrip('/')}/api/auth/{provider}/callback"


def _back(path: str) -> RedirectResponse:
    r = RedirectResponse(f"{settings.app_origin.rstrip('/')}{path}", status_code=302)
    r.delete_cookie(TX_COOKIE, path="/api/auth")
    return r


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(404, "unknown provider")
    if not provider_on(provider):
        raise HTTPException(503, f"{provider} sign-in is not configured")
    return provider


@router.get("/auth/config")
async def auth_config() -> dict:
    """What the sign-in page needs: one button per configured provider."""
    return {"enabled": enabled(), "providers": [{"id": p, "label": PROVIDERS[p]["label"], "login_url": f"/api/auth/{p}/start"} for p in PROVIDERS if provider_on(p)]}


@router.get("/auth/{provider}/start")
async def oauth_start(provider: str) -> RedirectResponse:
    _provider(provider)
    cfg, (cid, _) = PROVIDERS[provider], _creds(provider)
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = urlencode({"client_id": cid, "redirect_uri": _redirect_uri(provider), "response_type": "code", "scope": cfg["scope"], "state": state,
                   "code_challenge": challenge, "code_challenge_method": "S256", **cfg["extra"]})
    r = RedirectResponse(f"{cfg['auth']}?{q}", status_code=302)
    # state, provider and the PKCE verifier travel in a short-lived signed HttpOnly cookie, so no server-side session store is needed
    tx = jwt.encode({"s": state, "v": verifier, "p": provider, "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.jwt_secret, algorithm="HS256")
    r.set_cookie(TX_COOKIE, tx, max_age=600, httponly=True, samesite="lax", secure=settings.app_origin.startswith("https"), path="/api/auth")
    return r


async def exchange_code(provider: str, code: str, verifier: str) -> dict:
    cid, secret = _creds(provider)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(PROVIDERS[provider]["token"], headers={"Accept": "application/json"},
                         data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "redirect_uri": _redirect_uri(provider),
                               "client_id": cid, "client_secret": secret})
    r.raise_for_status()
    return r.json()


async def identity(provider: str, code: str, verifier: str) -> dict:
    tok = await exchange_code(provider, code, verifier)
    info = await asyncio.to_thread(verify_google, tok["id_token"])
    return {"sub": f"google:{info['sub']}", "email": info["email"], "name": info.get("name") or ""}


async def login_user(info: dict) -> tuple[User, bool]:
    """Sign in, or sign up on first use. Returns (user, created)."""
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.oauth_sub == info["sub"]))).scalar_one_or_none()
        if user is not None:
            return user, False
        user = User(oauth_sub=info["sub"], email=info["email"].lower(), name=info["name"][:120], email_alerts=True, created_at=datetime.now(timezone.utc))
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:  # same email under another provider or account: never merge accounts silently
            raise ValueError("this email is already registered")
        return user, True


@router.get("/auth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    _provider(provider)
    if error or not code or not state:  # user pressed cancel, or a forged hit on this URL
        return _back("/account?error=cancelled")
    try:
        tx = jwt.decode(request.cookies.get(TX_COOKIE, ""), settings.jwt_secret, algorithms=["HS256"])
        if tx["p"] != provider or not secrets.compare_digest(tx["s"], state):
            raise ValueError("state mismatch")  # CSRF: the response does not belong to a flow this browser started
        user, created = await login_user(await identity(provider, code, tx["v"]))
    except Exception as e:
        log.info("%s sign-in rejected: %s", provider, type(e).__name__)
        return _back("/account?error=signin_failed")
    # fragment, not query: it is never sent to any server or logged; the page moves it to storage and clears it
    return _back(f"/account#token={issue_token(user.id)}&new={int(created)}")


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    async with SessionLocal() as db:
        return _user_json(user, await _zone_ids(db, user.id))


@router.put("/me/zones")
async def set_zones(req: ZoneList, user: CurrentUser) -> dict:
    ids = sorted(set(req.zone_ids))
    async with SessionLocal() as db:
        known = set((await db.execute(select(Zone.id).where(Zone.id.in_(ids)))).scalars()) if ids else set()
        if known != set(ids):
            raise HTTPException(422, f"unknown zones: {sorted(set(ids) - known)}")
        await db.execute(delete(Subscription).where(Subscription.user_id == user.id))
        db.add_all([Subscription(user_id=user.id, zone_id=z) for z in ids])
        await db.commit()
    return {"zone_ids": ids}


@router.put("/me/prefs")
async def set_prefs(req: Prefs, user: CurrentUser) -> dict:
    async with SessionLocal() as db:
        u = await db.get(User, user.id)
        u.email_alerts = req.email_alerts
        await db.commit()
    return {"email_alerts": req.email_alerts}


@router.get("/me/alerts")
async def my_alerts(user: CurrentUser, limit: int = 50) -> list[dict]:
    """In-app inbox: everything we told this user about, including alerts not emailed because they muted email."""
    async with SessionLocal() as db:
        rows = (await db.execute(select(AlertDelivery).where(AlertDelivery.user_id == user.id)
                                 .order_by(AlertDelivery.created_at.desc()).limit(min(max(limit, 1), 200)))).scalars()
        return [{"id": r.id, "kind": r.kind, "zone_id": r.zone_id, "title": r.title, "body": r.body, "created_at": r.created_at, "status": r.status}
                for r in rows]


_last_test: dict[int, float] = {}
TEST_COOLDOWN_S = 60


@router.post("/me/test-email")
async def test_email(user: CurrentUser) -> dict:
    """Send the signed-in user a test message so they can confirm alerts will reach them. One per minute per user."""
    now = time.monotonic()
    wait = TEST_COOLDOWN_S - (now - _last_test.get(user.id, -1e9))
    if wait > 0:
        raise HTTPException(429, f"wait {int(wait) + 1}s before sending another test")
    _last_test[user.id] = now
    status = await send_email(user.email, "SHROOMCAST test email", "This is a test email from SHROOMCAST. Flood alerts for the places you follow will arrive at this address.")
    return {"status": status, "to": user.email}


@router.delete("/me", status_code=204)
async def delete_me(user: CurrentUser) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == user.id))  # subscriptions and deliveries cascade
        await db.commit()


# ------------------------------------------------------------------ what to tell people (pure, tested without a database)
def plan_replay(feed: list[dict], subs: dict[str, list[int]], names: dict[str, str], event_id: int, event_name: str) -> list[dict]:
    """Alert-feed items -> one delivery per (subscriber, fired alert). subs: zone_id -> user ids."""
    out = []
    for a in feed:
        for uid in subs.get(a["zone_id"], []):
            p = a.get("probability")
            out.append({"user_id": uid, "kind": "replay", "zone_id": a["zone_id"],
                        "key": f"replay:{event_id}:{a['zone_id']}:{a['issue_ts'].isoformat()}",
                        "title": f"[Simulated replay] {names.get(a['zone_id'], a['zone_id'])}: flood alert",
                        "body": f"{a['alert_text']}\n(Replay of {event_name}, flood chance {p:.0%}. This is a practice replay of a past storm, not a live warning.)"
                                if p is not None else f"{a['alert_text']}\n(Replay of {event_name}. Practice replay of a past storm, not a live warning.)"})
    return out


def plan_live(alerts: dict[str, list[dict]] | None, user_zones: dict[int, list[tuple[str, str, str]]]) -> list[dict]:
    """Official alerts per county -> deliveries. user_zones: user id -> [(zone_id, zone name, county)]. None (feed down) -> nothing, never 'all clear'."""
    out = []
    for county, items in (alerts or {}).items():
        for al in items:
            if al["level"] < MIN_LIVE_LEVEL:
                continue
            for uid, zones in user_zones.items():
                mine = [n for _, n, c in zones if c == county]
                if not mine:
                    continue
                until = f", until {al['ends']}" if al.get("ends") else ""
                out.append({"user_id": uid, "kind": "live", "zone_id": None, "key": f"live:{county}:{al['event']}:{al['effective']}",
                            "title": f"[Official NWS] {al['event']} for {county} County",
                            "body": f"{al['headline'] or al['event']}{until}.\nYour followed places in {county}: {', '.join(sorted(mine))}.\n"
                                    "This is an official National Weather Service warning. It is separate from the SHROOMCAST flood forecast."})
    return out


# ------------------------------------------------------------------ delivery
def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from or settings.smtp_user, to, subject
    msg.set_content(body)
    ssl = settings.smtp_port == 465  # implicit TLS; every other port (587, 25) upgrades with STARTTLS
    with (smtplib.SMTP_SSL if ssl else smtplib.SMTP)(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        if not ssl:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


def _write_outbox(to: str, subject: str, body: str) -> None:
    OUTBOX.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    (OUTBOX / f"{stamp}_{to.replace('@', '_at_')}.txt").write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")


async def send_email(to: str, subject: str, body: str) -> str:
    if not settings.smtp_host:
        await asyncio.to_thread(_write_outbox, to, subject, body)
        return "outbox"
    try:
        await asyncio.to_thread(_send_smtp, to, subject, body)
        return "sent"
    except Exception as e:
        log.warning("smtp send to user failed: %s", type(e).__name__)
        return "failed"


async def deliver(items: list[dict]) -> int:
    """Record new deliveries (skipping ones already recorded), then email each user once. Returns how many were new."""
    if not items:
        return 0
    now = datetime.now(timezone.utc)
    new_by_user: dict[int, list[dict]] = {}
    async with SessionLocal() as db:
        users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_({i["user_id"] for i in items})))).scalars()}
        seen = set((await db.execute(select(AlertDelivery.user_id, AlertDelivery.key).where(AlertDelivery.user_id.in_(users.keys()))
                                     )).all()) if users else set()
        for it in items:
            if it["user_id"] not in users or (it["user_id"], it["key"]) in seen:
                continue
            seen.add((it["user_id"], it["key"]))
            new_by_user.setdefault(it["user_id"], []).append(it)
        for uid, its in new_by_user.items():
            u = users[uid]
            status = "muted"
            if u.email_alerts:
                title = its[0]["title"] if len(its) == 1 else f"{len(its)} new flood alerts for your places"
                status = await send_email(u.email, title, "\n\n".join(f"{i['title']}\n{i['body']}" for i in its))
            for it in its:
                db.add(AlertDelivery(user_id=uid, key=it["key"], kind=it["kind"], zone_id=it["zone_id"], title=it["title"], body=it["body"],
                                     created_at=now, status=status))
        try:
            await db.commit()
        except IntegrityError:  # a concurrent run recorded the same alert first: its email already went out
            await db.rollback()
    return sum(len(v) for v in new_by_user.values())


async def _subscribers_by_zone(db) -> dict[str, list[int]]:
    subs: dict[str, list[int]] = {}
    for uid, zid in (await db.execute(select(Subscription.user_id, Subscription.zone_id))).all():
        subs.setdefault(zid, []).append(uid)
    return subs


async def notify_replay(feed: list[dict], event_id: int, event_name: str, names: dict[str, str]) -> int:
    if not settings.jwt_secret or not feed:
        return 0
    async with SessionLocal() as db:
        subs = await _subscribers_by_zone(db)
    return await deliver(plan_replay(feed, subs, names, event_id, event_name))


async def notify_live(alerts: dict[str, list[dict]] | None) -> int:
    if not settings.jwt_secret or not alerts:
        return 0
    async with SessionLocal() as db:
        rows = (await db.execute(select(Subscription.user_id, Zone.id, Zone.name, Zone.county).join(Zone, Zone.id == Subscription.zone_id))).all()
    user_zones: dict[int, list[tuple[str, str, str]]] = {}
    for uid, zid, name, county in rows:
        user_zones.setdefault(uid, []).append((zid, name, county))
    return await deliver(plan_live(alerts, user_zones))


_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    """Fire-and-forget that keeps a reference (so the task is not garbage collected) and logs failures instead of dropping them."""
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(lambda t: (_tasks.discard(t), t.cancelled() or t.exception() is None or log.warning("background task failed: %r", t.exception())))


async def live_alert_loop() -> None:
    """Background poller: official alerts for followed counties, every live_alert_poll_s. Failures never kill the loop."""
    from app import context

    while True:
        try:
            ctx = await context.get_context()
            n = await notify_live(ctx.get("alerts"))
            if n:
                log.info("live alerts: %d new deliveries", n)
        except Exception as e:
            log.warning("live alert poll failed: %s", type(e).__name__)
        await asyncio.sleep(settings.live_alert_poll_s)
