"""Is the explanation true? Audit of the model's driver contributions against what the plain-language phrases claim.

Run from backend/: uv run python -m scripts.sf_explain_audit
S_7 daily rows, shipped v2 model, median forecast at leads 6 and 24 h. Writes data/processed/metrics_explain_audit.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from app.agents.risk import p_exceed
from app.models.lightgbm_model import FEATURES, Forecaster
from scripts.sf_train import TRAIN_END, VAL_END, build

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"


def contrib(F, X, lead):
    return F.models[(lead, 0.5)].predict(X, pred_contrib=True)[:, :-1]  # last column is the bias


def main():
    F = Forecaster.load()
    df = build()
    train = df[(df.index < TRAIN_END) & (df.index.hour % 12 == 0)]
    test = df[(df.index >= VAL_END) & (df.index.hour == 0)]
    X = test[FEATURES]
    med = train[FEATURES].median()
    out = {"rows": int(len(test))}
    # alerted rows: probability from the 24 h-window trajectory at or above the validated threshold (raw, uncalibrated, close enough here)
    P = F.predict_leads(X)
    prob = np.array([max(p_exceed(P[0.1][r, i], P[0.5][r, i], P[0.9][r, i]) for i in range(P[0.5].shape[1])) for r in range(len(test))])
    alert = prob >= 0.3
    out["alerted_rows"] = int(alert.sum())

    for lead in (24, 6):
        C = pd.DataFrame(contrib(F, X, lead), columns=FEATURES, index=test.index)
        res = {}
        for f in FEATURES:
            v = X[f]
            ok = v.notna()
            rho = spearmanr(v[ok], C.loc[ok, f]).statistic if ok.sum() > 100 and v[ok].nunique() > 2 else None
            Ca = C[alert]
            pos = Ca.clip(lower=0)
            top1 = pos.idxmax(axis=1)
            res[f] = dict(spearman_value_vs_contribution=None if rho is None else round(float(rho), 3), mean_abs_contribution=round(float(C[f].abs().mean()), 4),
                          top1_share_alerted=round(float((top1 == f).mean()), 3),
                          in_top3_positive_share_alerted=round(float((pos.rank(axis=1, ascending=False, method="first")[f] <= 3).mean() * (pos[f] > 0).mean()), 3),
                          missing_share=round(float(v.isna().mean()), 3),
                          positive_contribution_while_value_missing=round(float(((C[f] > 0) & v.isna()).sum() / max(v.isna().sum(), 1)), 3))
        out[f"lead_{lead}"] = res
    # direction of the static terrain features: does a higher HAND / elevation lower or raise the predicted stage?
    # faithfulness by ablation: set the top positive driver (or a random feature) to its training median and see how much the prediction falls
    rng = np.random.default_rng(0)
    A = X[alert]
    C24 = pd.DataFrame(contrib(F, A, 24), columns=FEATURES, index=A.index)
    base = F.models[(24, 0.5)].predict(A)
    drops = {"top1": [], "top3_together": [], "random_feature": []}
    top = C24.clip(lower=0).rank(axis=1, ascending=False, method="first")
    for name in drops:
        Z = A.copy()
        if name == "top1":
            cols = [C24.columns[i] for i in C24.clip(lower=0).values.argmax(axis=1)]
            for i, c in enumerate(cols):
                Z.iat[i, Z.columns.get_loc(c)] = med[c]
        elif name == "top3_together":
            for c in FEATURES:
                m = (top[c] <= 3).values & (C24[c] > 0).values
                Z.loc[m, c] = med[c]
        else:
            cols = rng.choice(FEATURES, len(A))
            for i, c in enumerate(cols):
                Z.iat[i, Z.columns.get_loc(c)] = med[c]
        drops[name] = base - F.models[(24, 0.5)].predict(Z)
    out["ablation_drop_in_24h_median_stage"] = {k: dict(mean=round(float(np.mean(v)), 4), share_positive=round(float((np.asarray(v) > 0).mean()), 3)) for k, v in drops.items()}
    out["mean_stage_above_mark_predicted_alerted"] = round(float(base.mean()), 4)
    # stability: do lead 6 and lead 24 name the same top-3?
    C6 = pd.DataFrame(contrib(F, A, 6), columns=FEATURES, index=A.index)
    t6 = C6.clip(lower=0).rank(axis=1, ascending=False, method="first") <= 3
    t24 = top <= 3
    out["top3_overlap_lead6_vs_lead24"] = round(float(((t6 & t24).sum(axis=1) / 3).mean()), 3)
    (PROC / "metrics_explain_audit.json").write_text(json.dumps(out, indent=1))
    print("alerted rows:", out["alerted_rows"], "of", out["rows"])
    print(pd.DataFrame(out["lead_24"]).T.to_string())
    print("\nablation (mean drop in predicted 24h stage when the driver is set to its training median):")
    print(json.dumps(out["ablation_drop_in_24h_median_stage"]), "| mean predicted stage above mark:", out["mean_stage_above_mark_predicted_alerted"])
    print("top-3 overlap lead 6 vs 24:", out["top3_overlap_lead6_vs_lead24"])


if __name__ == "__main__":
    main()
