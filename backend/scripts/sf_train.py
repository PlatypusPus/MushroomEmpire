"""Train and evaluate the LightGBM quantile forecaster; compare with the persistence baseline on identical rows.

Run from backend/: uv run python -m scripts.sf_train
Split by time, never by row: train S_5 (2010-2014), early stopping on S_6 (2015-2019), test S_7 (2020-2023, holdout).
Thresholds (train-only q95 per gauge) are computed from S_5 only. Writes models_store/lightgbm_v1.joblib and
data/processed/metrics_lightgbm_v1.json.
"""
import asyncio
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sklearn.metrics import average_precision_score, brier_score_loss

from app.agents.risk import p_exceed
from app.config import settings
from app.models.lightgbm_model import FEATURES, LEADS, QUANTILES, VERSION, Forecaster

ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"
TRAIN_END, VAL_END = pd.Timestamp("2015-01-01"), pd.Timestamp("2020-01-01")
SPREAD = 0.03  # app.agents.forecast.SPREAD_M: the baseline's fixed interval half-width at 1 h, grows with sqrt(lead)


async def links():
    eng = create_async_engine(settings.database_url)
    async with eng.connect() as c:
        zs = pd.DataFrame((await c.execute(text("select zone_id, station_id, var, distance_km from zone_stations"))).mappings().all())
        st = pd.DataFrame((await c.execute(text("select id as station_id, name, var from stations"))).mappings().all())
        z = pd.DataFrame((await c.execute(text("select id as zone_id, hand_depth_m as hand_m, elevation_m from zones"))).mappings().all())
    await eng.dispose()
    return zs.merge(st, on=["station_id", "var"]), z


def build():
    zs, zones = asyncio.run(links())
    h = pd.read_parquet(ROOT / "sf_hourly.parquet", columns=["station", "var", "ts", "value", "interp"])
    V = h[h["var"] == "WATER"].pivot(index="ts", columns="station", values="value").sort_index()
    I = h[h["var"] == "WATER"].pivot(index="ts", columns="station", values="interp").sort_index()
    R = h[h["var"] == "RAIN"].pivot(index="ts", columns="station", values="value").sort_index().fillna(0)
    assert V.index.is_monotonic_increasing and (V.index.to_series().diff().dropna() == pd.Timedelta("1h")).all()
    thr = I[I.index < TRAIN_END].quantile(0.95)  # per gauge, train only
    ffV = V.ffill(limit=6)  # ingestion treats a gauge silent for more than 6 h as stale
    level = ffV.shift(1) - thr  # a reading is visible one hour after its timestamp
    trend = (ffV.shift(1) - ffV.shift(4)) / 3
    rain = {w: R.rolling(w).sum().shift(1) for w in (6, 24, 72)}
    # each gauge borrows the zone where it is closest (zone HAND, elevation and that zone's rain gauges)
    water = zs[zs["var"] == "WATER"].sort_values("distance_km").drop_duplicates("station_id").merge(zones, on="zone_id")
    rain_of = zs[zs["var"] == "RAIN"].groupby("zone_id").name.apply(list)
    frames = []
    for r in water.itertuples():
        if r.name not in V.columns:
            continue
        rg = [x for x in rain_of.get(r.zone_id, []) if x in R.columns]
        f = pd.DataFrame({"level": level[r.name], "trend": trend[r.name]})
        for w in (6, 24, 72):
            f[f"rain_{w}h"] = rain[w][rg].mean(axis=1) if rg else np.nan
        f["hand_m"], f["elevation_m"] = r.hand_m, r.elevation_m
        for k in LEADS:  # the stage k hours after the issue time, relative to the gauge threshold
            f[f"y{k}"] = I[r.name].shift(-k) - thr[r.name]
        f["station"] = r.name
        frames.append(f)
    return pd.concat(frames).dropna(subset=["level", "trend"])


async def record(metrics):
    """One model_runs row per version (replaced on retrain); the metrics endpoint reads it."""
    eng = create_async_engine(settings.database_url)
    async with eng.begin() as c:
        await c.execute(text("delete from model_runs where model_name = :n and version = :v"), {"n": "lightgbm-quantile", "v": "v1"})
        await c.execute(text("insert into model_runs (model_name, version, region_id, trained_on_splits, metrics_json) values (:n, :v, 1, cast(:s as json), cast(:m as json))"),
                        {"n": "lightgbm-quantile", "v": "v1", "s": json.dumps(["S_5"]), "m": json.dumps(metrics)})
    await eng.dispose()


def pinball(y, q, a):
    d = y - q
    return float(np.mean(np.maximum(a * d, (a - 1) * d)))


def main():
    df = build()
    idx = df.index
    train = df[(idx < TRAIN_END) & (idx.hour % 6 == 0)]
    val = df[(idx >= TRAIN_END) & (idx < VAL_END) & (idx.hour % 12 == 0)]
    test = df[(idx >= VAL_END) & (idx.hour == 0)]  # daily issues, ESL cadence
    print(f"rows: train {len(train):,}  val {len(val):,}  test {len(test):,}")
    models = {}
    for k in LEADS:
        tr, va = train.dropna(subset=[f"y{k}"]), val.dropna(subset=[f"y{k}"])
        for q in QUANTILES:
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=400, learning_rate=0.05, num_leaves=31,
                                  min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
            m.fit(tr[FEATURES], tr[f"y{k}"], eval_set=[(va[FEATURES], va[f"y{k}"])], callbacks=[lgb.early_stopping(30, verbose=False)])
            models[(k, q)] = m.booster_
        print(f"lead {k:>2} h trained ({models[(k, 0.5)].num_trees()} trees at q50)")
    F = Forecaster(models)
    F.save()

    # ---- evaluation on the holdout, model vs the persistence baseline (same rows, same units) ----
    X = test[FEATURES]
    P = F.predict_leads(X)
    out = {"model": VERSION, "train": "S_5", "early_stopping": "S_6", "test": "S_7 daily issues", "rows": int(len(test)), "by_lead": {}}
    base_q50 = lambda k: test.level + test.trend * min(k, 6)
    for i, k in enumerate(LEADS):
        y = test[f"y{k}"]
        ok = y.notna()
        b50, s = base_q50(k)[ok], SPREAD * k ** 0.5
        out["by_lead"][k] = dict(
            mae_model=float(np.abs(y[ok] - P[0.5][ok.values, i]).mean()), mae_persistence=float(np.abs(y[ok] - b50).mean()),
            pinball_model=float(np.mean([pinball(y[ok].values, P[q][ok.values, i], q) for q in QUANTILES])),
            pinball_persistence=float(np.mean([pinball(y[ok].values, (b50 + d).values, q) for q, d in zip(QUANTILES, (-s, 0, s))])),
            coverage_q10_q90_model=float(((y[ok].values >= P[0.1][ok.values, i]) & (y[ok].values <= P[0.9][ok.values, i])).mean()),
            coverage_q10_q90_persistence=float(((y[ok] >= b50 - s) & (y[ok] <= b50 + s)).mean()))

    # exceedance within 24 h, probability derived from the trajectory as the Risk agent does (max over steps of p_exceed)
    ys = test[[f"y{k}" for k in LEADS]]
    event = (ys.max(axis=1) > 0).astype(int)
    pm = np.array([max(p_exceed(P[0.1][r, i], P[0.5][r, i], P[0.9][r, i]) for i in range(len(LEADS))) for r in range(len(test))])
    pb = np.array([max(p_exceed(b - SPREAD * k ** 0.5, b, b + SPREAD * k ** 0.5) for k in LEADS for b in [lv + tr * min(k, 6)]) for lv, tr in zip(test.level, test.trend)])
    below = (test.level < 0).values  # onset cases: gauge currently below its threshold
    for name, mask in (("any", np.ones(len(test), bool)), ("onset_from_below", below)):
        e = event.values[mask]
        out[f"exceed24h_{name}"] = dict(n=int(mask.sum()), base_rate=float(e.mean()),
            pr_auc_model=float(average_precision_score(e, pm[mask])), pr_auc_persistence=float(average_precision_score(e, pb[mask])),
            brier_model=float(brier_score_loss(e, pm[mask])), brier_persistence=float(brier_score_loss(e, pb[mask])))
    (ROOT / "metrics_lightgbm_v1.json").write_text(json.dumps(out, indent=1))
    asyncio.run(record(out))
    print(json.dumps({k: (v if k.startswith("exceed") else None) for k, v in out.items() if k.startswith("exceed")}, indent=1))
    print(pd.DataFrame(out["by_lead"]).T.round(3).to_string())


if __name__ == "__main__":
    main()
