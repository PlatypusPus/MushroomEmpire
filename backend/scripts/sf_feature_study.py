"""Which features help? Add-one and drop-one ablations of feature groups, with day-cluster bootstrap CIs.

Run from backend/: uv run python -m scripts.sf_feature_study
Groups on top of the 7 serving features: hist (level history), struct (nearest gate + pump state), tide (NOAA), calendar.
Train S_5, early stopping S_6, test S_7 daily issues, leads 1/6/24 h, one model seed (bootstrap only covers test-set sampling).
Writes data/processed/metrics_feature_study.json.
"""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from app.agents.risk import p_exceed
from scripts.sf_tide_experiment import add_tide
from scripts.sf_train import TRAIN_END, VAL_END, build, pinball

ROOT = Path(__file__).resolve().parents[2] / "data"
RAW = ROOT / "raw/sf2bench/data/Processed_hour"
LEADS = [1, 6, 24]
BASE = ["level", "trend", "rain_6h", "rain_24h", "rain_72h", "hand_m", "elevation_m"]
GROUPS = {
    "hist": ["d6", "d24", "max24", "max72", "std24"],
    "struct": ["gate_now", "gate_6h", "gate_chg6", "pump_now", "pump_6h", "pump_chg6"],
    "tide": ["tide_now", "surge_now", "tide_pred_max24", "tide_pred_rng24"],
    "calendar": ["month", "hour"],
}
FT_KM = 0.0003048


def wide_series(var, names):
    """Hourly VALUE for each station, S_5..S_7 concatenated, as a time x station frame."""
    out = {}
    for n in names:
        out[n] = pd.concat([pd.read_csv(RAW / var / s / n / f"{n}.csv", parse_dates=["TIMESTAMP"], index_col="TIMESTAMP").VALUE for s in ("S_5", "S_6", "S_7")])
    return pd.DataFrame(out).sort_index()


def add_groups(df):
    """df: all hourly rows (index = issue time). Adds hist / struct / calendar columns, looked up from wide tables."""
    L = df.set_index("station", append=True)["level"].unstack("station")
    feats = {"d6": L - L.shift(6), "d24": L - L.shift(24), "max24": L.rolling(24, min_periods=12).max(), "max72": L.rolling(72, min_periods=36).max(),
             "std24": L.rolling(24, min_periods=12).std()}
    sub = pd.read_csv(ROOT / "processed/sf_subset_stations.csv")
    w = sub[sub["var"] == "WATER"].set_index("station")
    for var, tag in (("GATE", "gate"), ("PUMP", "pump")):
        s = sub[sub["var"] == var].set_index("station")
        near = {g: (lambda d: d.idxmin())(((s.lat - w.loc[g, "lat"]) ** 2 + (s.lon - w.loc[g, "lon"]) ** 2) ** 0.5) for g in L.columns if g in w.index}
        V = wide_series(var, sorted(set(near.values())))
        M = V[[near[g] for g in near]].set_axis(list(near), axis=1).reindex(L.index)
        feats[f"{tag}_now"] = M.shift(1)
        feats[f"{tag}_6h"] = M.shift(1).rolling(6, min_periods=3).mean()
        feats[f"{tag}_chg6"] = M.shift(1) - M.shift(7)
    long = {k: v.stack(future_stack=True) for k, v in feats.items()}
    key = pd.MultiIndex.from_arrays([df.index, df["station"]])
    for k, v in long.items():
        df[k] = v.reindex(key).values
    df["month"], df["hour"] = df.index.month, df.index.hour
    return df


def fit(train, val, feats, lead):
    tr, va = train.dropna(subset=[f"y{lead}"]), val.dropna(subset=[f"y{lead}"])
    ms = {}
    for q in (0.1, 0.5, 0.9):
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=300, learning_rate=0.08, num_leaves=31, min_child_samples=100,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
        m.fit(tr[feats], tr[f"y{lead}"], eval_set=[(va[feats], va[f"y{lead}"])], callbacks=[lgb.early_stopping(25, verbose=False)])
        ms[q] = m
    return ms


def evaluate(models, test, feats):
    P = {k: np.sort(np.stack([models[k][q].predict(test[feats]) for q in (0.1, 0.5, 0.9)]), axis=0) for k in LEADS}
    pin = np.zeros(len(test))
    n = np.zeros(len(test))
    for k in LEADS:
        y = test[f"y{k}"].values
        ok = ~np.isnan(y)
        for i, q in enumerate((0.1, 0.5, 0.9)):
            d = y - P[k][i]
            pin[ok] += np.maximum(q * d, (q - 1) * d)[ok]
        n[ok] += 3
    prob = np.array([max(p_exceed(P[k][0][r], P[k][1][r], P[k][2][r]) for k in LEADS) for r in range(len(test))])
    mae24 = np.abs(test["y24"].values - P[24][1])
    return pin / np.maximum(n, 1), prob, mae24, P


def boot(ev, e, below, days, reps=200, seed=0):
    """Day-cluster bootstrap of onset PR-AUC, any PR-AUC, mean pinball."""
    rng = np.random.default_rng(seed)
    ud = np.unique(days)
    rows = {d: np.where(days == d)[0] for d in ud}
    out = []
    for _ in range(reps):
        idx = np.concatenate([rows[d] for d in rng.choice(ud, len(ud))])
        out.append((average_precision_score(e[idx][below[idx]], ev["prob"][idx][below[idx]]), average_precision_score(e[idx], ev["prob"][idx]), np.nanmean(ev["pin"][idx])))
    return np.array(out)


def main():
    df = build()
    df = add_groups(df)
    idx = df.index
    train = df[(idx < TRAIN_END) & (idx.hour % 12 == 0)]
    val = df[(idx >= TRAIN_END) & (idx < VAL_END) & (idx.hour % 12 == 0)]
    test = df[(idx >= VAL_END) & (idx.hour == 0)].copy()
    train, val, test = (add_tide(x.copy()) for x in (train, val, test))
    print(f"rows: train {len(train):,} val {len(val):,} test {len(test):,}", flush=True)
    e = (test[[f"y{k}" for k in LEADS]].max(axis=1) > 0).astype(int).values
    below = (test.level < 0).values
    days = np.asarray(test.index.date)
    names = {"base": BASE}
    for g, c in GROUPS.items():
        names[f"+{g}"] = BASE + c
    allf = BASE + sum(GROUPS.values(), [])
    names["all"] = allf
    for g, c in GROUPS.items():
        names[f"all-{g}"] = [f for f in allf if f not in c]
    res, evs, last = {}, {}, None
    for name, feats in names.items():
        models = {k: fit(train, val, feats, k) for k in LEADS}
        pin, prob, mae24, P = evaluate(models, test, feats)
        evs[name] = dict(pin=pin, prob=prob)
        res[name] = dict(n_features=len(feats), mean_pinball=float(np.nanmean(pin)), mae24=float(np.nanmean(mae24)),
                         onset_pr_auc=float(average_precision_score(e[below], prob[below])), any_pr_auc=float(average_precision_score(e, prob)),
                         trees24=int(models[24][0.5].best_iteration_ or 0))
        print(name, {k: round(v, 4) for k, v in res[name].items()}, flush=True)
        if name == "all":
            last = (models, feats)
    # bootstrap CIs of the difference to base (positive = better for PR-AUC, negative = better for pinball)
    B = {n: boot(evs[n], e, below, days) for n in names}
    for n in names:
        if n == "base":
            continue
        d = B[n] - B["base"]
        res[n].update(d_onset_pr_auc=[float(np.percentile(d[:, 0], 2.5)), float(np.percentile(d[:, 0], 97.5))],
                      d_any_pr_auc=[float(np.percentile(d[:, 1], 2.5)), float(np.percentile(d[:, 1], 97.5))],
                      d_pinball=[float(np.percentile(d[:, 2], 2.5)), float(np.percentile(d[:, 2], 97.5))])
    # permutation importance on the full model: rise in 24 h median MAE when one feature is shuffled
    models, feats = last
    rng = np.random.default_rng(0)
    base_mae = np.nanmean(np.abs(test["y24"].values - models[24][0.5].predict(test[feats])))
    perm = {}
    for f in feats:
        t = test[feats].copy()
        v = []
        for _ in range(3):
            t[f] = rng.permutation(t[f].values)
            v.append(np.nanmean(np.abs(test["y24"].values - models[24][0.5].predict(t))) - base_mae)
        perm[f] = float(np.mean(v))
    res["permutation_mae24_increase"] = dict(sorted(perm.items(), key=lambda kv: -kv[1]))
    (ROOT / "processed/metrics_feature_study.json").write_text(json.dumps(res, indent=1))
    print("\nvs base (95% CI of difference):")
    for n in names:
        if n != "base":
            r = res[n]
            print(f"{n:14} onset PR-AUC {r['onset_pr_auc'] - res['base']['onset_pr_auc']:+.3f} {np.round(r['d_onset_pr_auc'], 3)}  pinball {r['mean_pinball'] - res['base']['mean_pinball']:+.4f} {np.round(r['d_pinball'], 4)}")
    print("\npermutation importance (MAE24 increase):", {k: round(v, 4) for k, v in list(res['permutation_mae24_increase'].items())[:10]})


if __name__ == "__main__":
    main()
