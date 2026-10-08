"""Do forecasts hold up at gauges the model never saw? 3-fold split BY GAUGE (still train S_5, early stop S_6, test S_7).

Run from backend/: uv run python -m scripts.sf_spatial
For each fold: train on 2/3 of the gauges, then compare on the held-out third (unseen gauges) with the shipped v2 model
(which trained on all gauges) on the same rows. Leads 1/6/24 h, one seed. Writes data/processed/metrics_spatial_v2.json.
"""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score

from app.agents.risk import p_exceed
from app.models.lightgbm_model import FEATURES, Forecaster
from scripts.sf_train import TRAIN_END, VAL_END, build, pinball

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"
LEADS = [1, 6, 24]


def fit(tr, va, lead):
    out = {}
    tr, va = tr.dropna(subset=[f"y{lead}"]), va.dropna(subset=[f"y{lead}"])
    for q in (0.1, 0.5, 0.9):
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=300, learning_rate=0.08, num_leaves=31, min_child_samples=100,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
        m.fit(tr[FEATURES], tr[f"y{lead}"], eval_set=[(va[FEATURES], va[f"y{lead}"])], callbacks=[lgb.early_stopping(25, verbose=False)])
        out[q] = m
    return out


def score(P, test):
    """P: {lead: (3, n)} -> pinball, 24 h MAE, any/onset PR-AUC of exceedance within the leads."""
    pin, n = 0.0, 0
    for k in LEADS:
        y = test[f"y{k}"].values
        ok = ~np.isnan(y)
        for i, q in enumerate((0.1, 0.5, 0.9)):
            d = y[ok] - P[k][i][ok]
            pin += np.maximum(q * d, (q - 1) * d).sum()
            n += ok.sum()
    prob = np.array([max(p_exceed(P[k][0][r], P[k][1][r], P[k][2][r]) for k in LEADS) for r in range(len(test))])
    e = (test[[f"y{k}" for k in LEADS]].max(axis=1) > 0).astype(int).values
    below = (test.level < 0).values
    y24 = test["y24"].values
    return dict(pinball=pin / n, mae24=float(np.nanmean(np.abs(y24 - P[24][1]))), any_pr_auc=float(average_precision_score(e, prob)),
                onset_pr_auc=float(average_precision_score(e[below], prob[below])), rows=int(len(test)))


def main():
    df = build()
    idx = df.index
    train = df[(idx < TRAIN_END) & (idx.hour % 12 == 0)]
    val = df[(idx >= TRAIN_END) & (idx < "2020-01-01") & (idx.hour % 12 == 0)]
    test = df[(idx >= "2020-01-01") & (idx.hour == 0)]
    gauges = np.array(sorted(df.station.unique()))
    rng = np.random.default_rng(0)
    folds = np.array_split(rng.permutation(gauges), 3)
    F = Forecaster.load()
    res = {"gauges": len(gauges), "folds": []}
    for i, held in enumerate(folds):
        held = set(held)
        tr, va = train[~train.station.isin(held)], val[~val.station.isin(held)]
        te = test[test.station.isin(held)]
        models = {k: fit(tr, va, k) for k in LEADS}
        P_unseen = {k: np.sort(np.stack([models[k][q].predict(te[FEATURES]) for q in (0.1, 0.5, 0.9)]), axis=0) for k in LEADS}
        full = F.predict_leads(te[FEATURES])  # shipped model, which trained on these gauges
        P_seen = {k: np.stack([full[q][:, [1, 6, 24].index(k) if False else {1: 0, 6: 2, 24: 5}[k]] for q in (0.1, 0.5, 0.9)]) for k in LEADS}
        r = dict(fold=i, held_out_gauges=len(held), unseen=score(P_unseen, te), shipped_seen=score(P_seen, te))
        res["folds"].append(r)
        print(json.dumps({k: (v if k == "fold" else {a: round(b, 4) for a, b in v.items()}) if isinstance(v, dict) else v for k, v in r.items()}), flush=True)
    for key in ("unseen", "shipped_seen"):
        res[f"mean_{key}"] = {m: float(np.mean([f[key][m] for f in res["folds"]])) for m in ("pinball", "mae24", "any_pr_auc", "onset_pr_auc")}
    (PROC / "metrics_spatial_v2.json").write_text(json.dumps(res, indent=1))
    print("mean unseen:", {k: round(v, 4) for k, v in res["mean_unseen"].items()})
    print("mean seen  :", {k: round(v, 4) for k, v in res["mean_shipped_seen"].items()})


if __name__ == "__main__":
    main()
