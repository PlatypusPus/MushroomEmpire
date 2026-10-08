"""Does NOAA tide help? Train the same quantile model with and without tide features, test on the S_7 holdout.

Run from backend/: uv run python -m scripts.sf_tide_experiment
Variants: base (7 features) | tide (+ tide_now, surge_now, predicted-tide max/range over the next 24 h)
          | tide_lead (+ predicted tide at the target hour itself). Predicted astronomical tide is known in advance,
          so using it at issue time is not leakage; OBSERVED tide and surge are only used up to t-1 h.
Needs data/raw/noaa/*.csv (scripts.fetch_all.tides) and the QC/zone_stations tables.
"""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from app.agents.risk import p_exceed
from scripts.sf_train import TRAIN_END, VAL_END, build, pinball

ROOT = Path(__file__).resolve().parents[2] / "data"
LEADS = [1, 6, 24]  # fewer leads than production: this is a comparison, not the shipped model
STATIONS = {"8723214": (25.7314, -80.1618), "8722956": (26.0817, -80.1167), "8722670": (26.6128, -80.0342)}  # lat, lon
TZ_SHIFT_H = -5  # SF2Bench clock minus NOAA GMT: fixed EST fits the lag analysis (r 0.97 at a 3-4 h shift, same in summer and winter); unverified
BASE = ["level", "trend", "rain_6h", "rain_24h", "rain_72h", "hand_m", "elevation_m"]


def tide_frames():
    out = {}
    for sid in STATIONS:
        o = pd.read_csv(ROOT / f"raw/noaa/{sid}_hourly_height.csv", usecols=["t", "v"]).assign(t=lambda d: pd.to_datetime(d.t), v=lambda d: pd.to_numeric(d.v, errors="coerce"))
        p = pd.read_csv(ROOT / f"raw/noaa/{sid}_predictions.csv", usecols=["t", "v"]).assign(t=lambda d: pd.to_datetime(d.t), v=lambda d: pd.to_numeric(d.v, errors="coerce"))
        o, p = o.set_index("t").v, p.set_index("t").v
        o.index, p.index = o.index + pd.Timedelta(hours=TZ_SHIFT_H), p.index + pd.Timedelta(hours=TZ_SHIFT_H)
        out[sid] = (o[~o.index.duplicated()], p[~p.index.duplicated()])
    return out


def add_tide(df):
    """Attach tide features per row from the nearest NOAA station. Index = issue time (SF2Bench clock)."""
    st = pd.read_csv(ROOT / "processed/sf_subset_stations.csv").query("`var` == 'WATER'").set_index("station")
    near = {n: min(STATIONS, key=lambda s: (STATIONS[s][0] - r.lat) ** 2 + (STATIONS[s][1] - r.lon) ** 2) for n, r in st.iterrows()}
    T = tide_frames()
    cols = {c: np.full(len(df), np.nan) for c in ["tide_now", "surge_now", "tide_pred_max24", "tide_pred_rng24"] + [f"tide_pred_lead{k}" for k in LEADS]}
    for sid, (o, p) in T.items():
        idx = pd.date_range(min(o.index.min(), p.index.min()), max(o.index.max(), p.index.max()), freq="h")
        o, p = o.reindex(idx), p.reindex(idx)
        surge = o - p
        f = pd.DataFrame({"tide_now": o.shift(1), "surge_now": surge.shift(1),
                          "tide_pred_max24": p[::-1].rolling(24, min_periods=12).max()[::-1],  # window [t, t+24h)
                          "tide_pred_rng24": p[::-1].rolling(24, min_periods=12).max()[::-1] - p[::-1].rolling(24, min_periods=12).min()[::-1]})
        for k in LEADS:
            f[f"tide_pred_lead{k}"] = p.shift(-k)
        m = df.station.map(near).eq(sid).values
        sub = f.reindex(df.index[m])
        for c in cols:
            cols[c][m] = sub[c].values
    return df.assign(**cols)


def fit_predict(train, val, test, feats, lead):
    tcol = f"tide_pred_lead{lead}"
    fs = [c for c in feats if not c.startswith("tide_pred_lead")] + ([tcol] if "LEAD" in feats else [])
    fs = [c for c in fs if c != "LEAD"]
    tr, va = train.dropna(subset=[f"y{lead}"]), val.dropna(subset=[f"y{lead}"])
    preds = {}
    for q in (0.1, 0.5, 0.9):
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=100,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
        m.fit(tr[fs], tr[f"y{lead}"], eval_set=[(va[fs], va[f"y{lead}"])], callbacks=[lgb.early_stopping(30, verbose=False)])
        preds[q] = m.predict(test[fs])
    P = np.sort(np.stack([preds[0.1], preds[0.5], preds[0.9]]), axis=0)
    return P, m


def main():
    df = add_tide(build())
    idx = df.index
    train = df[(idx < TRAIN_END) & (idx.hour % 6 == 0)]
    val = df[(idx >= TRAIN_END) & (idx < VAL_END) & (idx.hour % 12 == 0)]
    test = df[(idx >= VAL_END) & (idx.hour == 0)]
    tide_free = ["tide_now", "surge_now", "tide_pred_max24", "tide_pred_rng24"]
    variants = {"base": BASE, "tide": BASE + tide_free, "tide_lead": BASE + tide_free + ["LEAD"]}
    print(f"rows: train {len(train):,} val {len(val):,} test {len(test):,}; tide features missing in test: {test[tide_free].isna().any(axis=1).mean():.1%}")
    res, probs, imps = {}, {}, {}
    for name, feats in variants.items():
        P_all = {}
        for k in LEADS:
            P, m = fit_predict(train, val, test, feats, k)
            y = test[f"y{k}"].values
            ok = ~np.isnan(y)
            res[(name, k)] = dict(mae=float(np.abs(y[ok] - P[1][ok]).mean()), pinball=float(np.mean([pinball(y[ok], P[i][ok], q) for i, q in enumerate((0.1, 0.5, 0.9))])),
                                  coverage=float(((y[ok] >= P[0][ok]) & (y[ok] <= P[2][ok])).mean()))
            P_all[k] = P
            if k == 24:
                imps[name] = dict(zip(m.booster_.feature_name(), m.booster_.feature_importance("gain").round(0)))
        e = (test[[f"y{k}" for k in LEADS]].max(axis=1) > 0).astype(int).values
        pr = np.array([max(p_exceed(P_all[k][0][r], P_all[k][1][r], P_all[k][2][r]) for k in LEADS) for r in range(len(test))])
        below = (test.level < 0).values
        probs[name] = {m_: dict(pr_auc=float(average_precision_score(e[msk], pr[msk])), brier=float(brier_score_loss(e[msk], pr[msk])), base_rate=float(e[msk].mean()))
                       for m_, msk in (("any", np.ones(len(test), bool)), ("onset_from_below", below))}
        # storm window: Nicole 2022-11-08 .. 2022-11-13 (all test rows in that window, hourly issue times are not used, daily only)
        w = ((test.index >= "2022-11-07") & (test.index <= "2022-11-13"))
        probs[name]["nicole_week"] = dict(n=int(w.sum()), base_rate=float(e[w].mean()), pr_auc=float(average_precision_score(e[w], pr[w])) if e[w].any() else None,
                                          brier=float(brier_score_loss(e[w], pr[w])))
    out = {"leads": LEADS, "per_lead": {f"{n}/{k}h": v for (n, k), v in res.items()}, "exceed24h": probs}
    (ROOT / "processed/metrics_tide_experiment.json").write_text(json.dumps(out, indent=1))
    print(pd.DataFrame({f"{n}/{k}h": v for (n, k), v in res.items()}).T.round(3).to_string())
    for name, p in probs.items():
        print(name, {k: {a: round(b, 3) if b is not None else None for a, b in v.items()} for k, v in p.items()})
    for name, i in imps.items():
        top = sorted(i.items(), key=lambda kv: -kv[1])[:6]
        print("gain@24h", name, [(a, int(b)) for a, b in top])


if __name__ == "__main__":
    main()
