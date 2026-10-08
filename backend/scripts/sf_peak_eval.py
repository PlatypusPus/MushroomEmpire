"""Served-condition evaluation of the peak: alerted (calibrated probability >= threshold) AND a real event, S_7, issues at 00:00 and 12:00.

Run from backend/: uv run python -m scripts.sf_peak_eval   -> data/processed/metrics_peak_eval.json
Compares: new peak model, the old trajectory argmax, an issue-hour prior, and a fixed hour; truth = plateau-median peak (sf_peak.summarise).
"""
import json

import joblib
import numpy as np
import pandas as pd

from app import calibration
from app.models.lightgbm_model import FEATURES, LEADS, Forecaster
from app.models.peak_model import MODEL_PATH
from scripts import sf_peak as SP
from scripts import sf_validate as V
from scripts.sf_train import TRAIN_END, VAL_END, build


def main():
    F = Forecaster.load()
    bundle = joblib.load(MODEL_PATH)
    df = build()
    df["hour"], df["month"] = df.index.hour, df.index.month
    train = df[(df.index < TRAIN_END) & (df.index.hour % 3 == 0)]
    test = df[(df.index >= VAL_END) & (df.index.hour.isin([0, 12]))]
    test = pd.concat([test, SP.tide_timing(test)], axis=1)
    T = SP.truth(test)
    ev, peak = SP.summarise(T)
    # alert decision exactly as served
    Q = V.trajectories(F, test[FEATURES])
    w = calibration.widen(V.KS, LEADS)
    Q = Q + np.array([-w, 0 * w, w])[:, None, :]
    pred = V.predict_summary(Q)
    c = calibration.load()
    prob = np.interp(pred["prob"], c["iso_x"], c["iso_y"])
    hits = ev & (prob >= calibration.alert_threshold()) & pred["has_onset"]  # the served peak exists only when the median crosses
    print("S_7 rows", len(test), "events", int(ev.sum()), "alerted events with a served peak", int(hits.sum()), flush=True)
    # train-only baselines (same event definition)
    Ttr = SP.truth(train)
    evt, pkt = SP.summarise(Ttr)
    hr = train.index.hour.values[evt]
    pri = SP.prior_table(pkt[evt], hr)
    glob = int(np.median(pkt[evt]))
    P = np.zeros((len(test), 24))
    P[:, bundle["classes"]] = bundle["model"].predict_proba(test[bundle["features"]])
    cdf = P.cumsum(axis=1)
    a = bundle["window_alpha"]
    new_lik = (cdf >= 0.5).argmax(axis=1) + 1
    lo, hi = (cdf >= a).argmax(axis=1) + 1, (cdf >= 1 - a).argmax(axis=1) + 1
    prior_lik = np.array([int((np.cumsum(pri[h]) >= 0.5).argmax() + 1) for h in test.index.hour])
    methods = {"new_peak_model": new_lik, "old_trajectory_argmax": pred["pk_likely"], "issue_hour_prior": prior_lik, "fixed_hour": np.full(len(test), glob)}
    days = np.asarray(test.index.date)
    ud = np.unique(days)
    rows = {d: np.where(days == d)[0] for d in ud}
    rng = np.random.default_rng(0)
    out = {"alerted_events": int(hits.sum()), "fixed_hour": glob, "methods": {}}
    for name, lik in methods.items():
        e = np.abs(lik - peak)
        out["methods"][name] = dict(mae_h=float(e[hits].mean()), median_ae_h=float(np.median(e[hits])), within_3h=float((e[hits] <= 3).mean()))
    for name in ("old_trajectory_argmax", "issue_hour_prior", "fixed_hour"):
        d = np.abs(methods["new_peak_model"] - peak) - np.abs(methods[name] - peak)
        boots = [d[hits & np.isin(np.arange(len(test)), np.concatenate([rows[x] for x in rng.choice(ud, len(ud))]))].mean() for _ in range(1)]
        diffs = []
        for _ in range(200):
            ii = np.concatenate([rows[x] for x in rng.choice(ud, len(ud))])
            m = hits[ii]
            diffs.append(d[ii][m].mean())
        out["methods"]["new_peak_model"][f"mae_diff_vs_{name}_ci95"] = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    out["window"] = dict(alpha=a, coverage=float(((peak >= lo) & (peak <= hi))[hits].mean()), width_h_median=float(np.median((hi - lo + 1)[hits])),
                         old_window_width_h_median=float(np.median((pred["pk_late"] - pred["pk_early"] + 1)[hits])),
                         old_window_coverage=float(((peak >= pred["pk_early"]) & (peak <= pred["pk_late"]))[hits].mean()))
    below = test.level.values < 0
    out["new_by_start"] = {k: dict(rows=int((hits & m).sum()), mae_h=float(np.abs(new_lik - peak)[hits & m].mean()), prior_mae_h=float(np.abs(prior_lik - peak)[hits & m].mean()))
                           for k, m in (("starting_below", below), ("already_above", ~below))}
    by_hour = {}
    for h in (0, 12):
        m = hits & (test.index.hour.values == h)
        by_hour[str(h)] = dict(rows=int(m.sum()), new=float(np.abs(new_lik - peak)[m].mean()), prior=float(np.abs(prior_lik - peak)[m].mean()), old=float(np.abs(pred["pk_likely"] - peak)[m].mean()))
    out["by_issue_hour"] = by_hour
    (SP.PROC / "metrics_peak_eval.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
