"""Skill at 48 and 72 h versus persistence (decides whether to extend the 24 h horizon).

Run from backend/: uv run python -m scripts.sf_horizons   (same split as the shipped model; leads 48 and 72 only)
Writes data/processed/metrics_horizons_v2.json.
"""
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

import scripts.sf_train as T
from app.agents.risk import p_exceed
from app.models.lightgbm_model import FEATURES
from scripts.sf_spatial import fit
from scripts.sf_train import TRAIN_END, VAL_END, pinball

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"
LEADS = [48, 72]
SPREAD = 0.03


def main():
    T.LEADS = LEADS  # build() creates y48 and y72 instead of the production leads
    df = T.build()
    idx = df.index
    train = df[(idx < TRAIN_END) & (idx.hour % 12 == 0)]
    val = df[(idx >= TRAIN_END) & (idx < VAL_END) & (idx.hour % 12 == 0)]
    test = df[(idx >= VAL_END) & (idx.hour == 0)]
    below = (test.level < 0).values
    res = {}
    for k in LEADS:
        m = fit(train, val, k)
        y = test[f"y{k}"].values
        ok = ~np.isnan(y)
        P = np.sort(np.stack([m[q].predict(test[FEATURES]) for q in (0.1, 0.5, 0.9)]), axis=0)
        base = (test.level + test.trend * 6).values
        s = SPREAD * k ** 0.5
        pm = np.array([p_exceed(P[0][r], P[1][r], P[2][r]) for r in range(len(test))])
        pb = np.array([p_exceed(base[r] - s, base[r], base[r] + s) for r in range(len(test))])
        ev = (y > 0).astype(int)
        sel = ok & below
        res[str(k)] = dict(
            pinball_model=float(np.mean([pinball(y[ok], P[i][ok], q) for i, q in enumerate((0.1, 0.5, 0.9))])),
            pinball_persistence=float(np.mean([pinball(y[ok], base[ok] + d, q) for q, d in zip((0.1, 0.5, 0.9), (-s, 0, s))])),
            mae_model=float(np.abs(y[ok] - P[1][ok]).mean()), mae_persistence=float(np.abs(y[ok] - base[ok]).mean()),
            coverage_q10_q90=float(((y[ok] >= P[0][ok]) & (y[ok] <= P[2][ok])).mean()),
            level_above_mark_at_lead_base_rate=float(ev[ok].mean()),
            onset_base_rate=float(ev[sel].mean()), onset_pr_auc_model=float(average_precision_score(ev[sel], pm[sel])),
            onset_pr_auc_persistence=float(average_precision_score(ev[sel], pb[sel])), rows=int(ok.sum()))
        print(k, {a: round(b, 4) for a, b in res[str(k)].items()}, flush=True)
    (PROC / "metrics_horizons_v2.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
