"""Live model: hourly resampling, train/live feature parity, no look-ahead, self-labelled rows, and the promote-only-if-better update."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app import live_model as L
from app.agents.ingestion import ingest
from app.models.lightgbm_model import FEATURES, LEADS, Forecaster
from tests.test_backend import T0, synthetic_snapshot

UTC = timezone.utc


def test_hourly_averages_quarter_hours_in_utc():
    t = datetime(2026, 10, 9, 14, 0, tzinfo=timezone(timedelta(hours=-4)))
    rs = L.hourly([(t, 1.0), (t + timedelta(minutes=15), 2.0), (t + timedelta(minutes=45), 3.0), (t + timedelta(hours=1), 9.0)])
    assert [r["value"] for r in rs] == [2.0, 9.0] and rs[0]["ts"] == datetime(2026, 10, 9, 18, tzinfo=UTC)


def test_live_features_match_the_training_features_and_ignore_the_future():
    snap = synthetic_snapshot()
    replay_fv = ingest(snap, "B", T0)  # zone B: one water gauge (station 2, q95 1.4), no rain gauge
    rows = [{"ts": r["ts"], "value": r["value"]} for r in snap.rows if r["station_id"] == 2]
    live = L.features("B", rows, {}, 1.4, T0 - timedelta(hours=1), None)  # replay sees a row one hour after its timestamp
    for k in ("level_m", "level_trend_m_per_h", "level_change_6h", "level_change_24h", "level_max_24h", "level_max_72h", "level_std_24h"):
        assert abs(getattr(live, k) - getattr(replay_fv, k)) < 1e-9, k
    assert live.rain_24h is None  # no rain data is None, never 0
    future = rows + [{"ts": T0 + timedelta(hours=30), "value": 99.0}]
    assert L.features("B", future, {}, 1.4, T0 - timedelta(hours=1), None) == live  # a later reading changes nothing
    assert L.features("B", rows, {}, 1.4, T0 + timedelta(hours=40), None) is None  # silent gauge: no forecast, not "low"


def _series(hours=24 * 40, start=datetime(2026, 8, 1, tzinfo=UTC), shift=0.0):
    t = [start + timedelta(hours=i) for i in range(hours)]
    lv = [{"ts": x, "value": 1.0 + 0.5 * np.sin(i / 9) + shift} for i, x in enumerate(t)]
    rain = {x: (0.05 if i % 50 < 3 else 0.0) for i, x in enumerate(t)}
    return lv, rain


def test_training_rows_are_labelled_by_what_the_gauge_did_later():
    lv, rain = _series(hours=24 * 6)
    df = L.training_rows("g", lv, rain, thr=1.2, elev=2.0)
    at = {r["ts"]: r["value"] for r in lv}
    r = df.iloc[0]
    for k in LEADS:
        assert abs(r[f"y{k}"] - (at[r["t"] + timedelta(hours=k)] - 1.2)) < 1e-9
    assert (df["t"] - df["t"].min()).dt.total_seconds().mod(3 * 3600).eq(0).all()  # one row every 3 h
    assert df["t"].max() + timedelta(hours=max(LEADS)) <= lv[-1]["ts"]  # every label exists


def test_update_promotes_only_a_better_model_and_never_trains_on_the_test_window():
    base = Forecaster.load().models
    lv, rain = _series(shift=2.0)  # a regime the SF2Bench model never saw: levels sit 2 ft higher
    df = L.training_rows("g", lv, rain, thr=1.0, elev=1.0)
    now = lv[-1]["ts"]
    cut = now - timedelta(days=L.EVAL_DAYS)
    small = L.update(base, df.iloc[:50], now)
    assert not small["promoted"] and small["reason"] == "not enough live rows yet"  # too little data: keep the current model
    big = pd.concat([df.assign(site=f"g{i}") for i in range(4)], ignore_index=True)  # four gauges' worth of rows
    res = L.update(base, big, now)
    assert res["n_train"] >= L.MIN_ROWS and res["promoted"] and res["loss_new"] < res["loss_current"]
    assert set(res["models"]) == set(base)
    tr = big[big["t"] + timedelta(hours=max(LEADS)) < cut]
    assert len(tr) == res["n_train"] and (tr["t"] + timedelta(hours=24) < cut).all()
    assert list(FEATURES) == list(df.columns[: len(FEATURES)])
