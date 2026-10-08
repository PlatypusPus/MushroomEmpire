"""Validation of the forecasting agent: timing error, misses and false alarms, calibration, severity.

Run from backend/: uv run python -m scripts.sf_validate
Fit set = S_6 (validation, also used for early stopping), report set = S_7 (holdout, daily issues, 24 h window).
Everything chosen on S_6 (alert threshold, isotonic map, interval widening, severity cuts) is only EVALUATED on S_7.
Truth = the actual stage above the gauge's train-only q95 over the next 24 h; an "event" is >= 3 consecutive hours above it
(ESL rule). Writes models_store/calibration_v2.json and data/processed/metrics_validation_v2.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss

from app.agents.risk import TAIL_P, p_exceed
from app.models.lightgbm_model import FEATURES, LEADS, Forecaster
from scripts.sf_train import TRAIN_END, VAL_END, build

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
KS = np.arange(1, 25)
SEV = ["low", "moderate", "high", "severe"]


def interp_matrix():
    return np.stack([np.interp(KS, LEADS, np.eye(len(LEADS))[j]) for j in range(len(LEADS))], axis=1)  # (24, 6)


def trajectories(F, X):
    P = F.predict_leads(X)
    W = interp_matrix()
    return np.stack([P[q] @ W.T for q in (0.1, 0.5, 0.9)])  # (3, n, 24), already ordered q10<=q50<=q90 at the trained leads


def p_exceed_v(q10, q50, q90, x=0.0):
    lo = np.where(x <= q50, q10, q50)
    hi = np.where(x <= q50, q50, q90)
    plo = np.where(x <= q50, 0.1, 0.5)
    phi = np.where(x <= q50, 0.5, 0.9)
    with np.errstate(divide="ignore", invalid="ignore"):
        cdf = np.where(hi > lo, plo + (phi - plo) * (x - lo) / (hi - lo), phi)
    return np.where(x <= q10, 1 - TAIL_P, np.where(x >= q90, TAIL_P, 1 - cdf))


def first_true(mask):
    """1-based index of the first True per row, 0 if none."""
    return np.where(mask.any(axis=1), mask.argmax(axis=1) + 1, 0)


def predict_summary(Q):
    q10, q50, q90 = Q
    prob = p_exceed_v(q10, q50, q90).max(axis=1)
    on_likely = first_true(q50 > 0)
    on_early = first_true(q90 > 0)
    on_late = np.where(on_likely > 0, np.where(first_true(q10 > 0) > 0, first_true(q10 > 0), 24), 0)
    pk = q50.argmax(axis=1)
    pk_level = q50.max(axis=1)
    near = q90 >= pk_level[:, None]
    pk_early = first_true(near)
    pk_late = 24 - near[:, ::-1].argmax(axis=1)
    return dict(prob=prob, on_likely=on_likely, on_early=on_early, on_late=on_late, pk_likely=pk + 1, pk_early=pk_early, pk_late=pk_late,
                pk_level=pk_level, has_onset=on_likely > 0)


def truth_summary(T):
    pos = T > 0
    run3 = pos[:, :-2] & pos[:, 1:-1] & pos[:, 2:]
    ev = run3.any(axis=1)
    onset = np.where(ev, run3.argmax(axis=1) + 1, 0)
    peak_excess = np.where(ev, np.nanmax(np.where(pos, T, -np.inf), axis=1), 0.0)
    peak_k = np.where(ev, np.nanargmax(np.where(np.isnan(T), -np.inf, T), axis=1) + 1, 0)
    return dict(event=ev, onset=onset, peak_excess=peak_excess, peak_k=peak_k)


def ece(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean() for b in range(bins) if (idx == b).any()))


def rows_and_truth(df):
    """Daily issue rows for S_6 and S_7 plus the next-24 h stage above the mark for each (gauge, issue)."""
    h = pd.read_parquet(PROC / "sf_hourly.parquet", columns=["station", "var", "ts", "interp"])
    I = h[h["var"] == "WATER"].pivot(index="ts", columns="station", values="interp").sort_index()
    thr = I[I.index < TRAIN_END].quantile(0.95)
    Iw = (I - thr).to_numpy()
    tpos = {t: i for i, t in enumerate(I.index)}
    col = {s: j for j, s in enumerate(I.columns)}
    out = {}
    for name, lo, hi in (("S_6", TRAIN_END, VAL_END), ("S_7", VAL_END, pd.Timestamp("2100-01-01"))):
        r = df[(df.index >= lo) & (df.index < hi) & (df.index.hour == 0)]
        ti = np.array([tpos[t] for t in r.index])
        cj = np.array([col[s] for s in r.station])
        idx = ti[:, None] + KS[None, :]
        ok = idx.max(axis=1) < Iw.shape[0]
        T = np.full((len(r), 24), np.nan)
        T[ok] = Iw[np.minimum(idx[ok], Iw.shape[0] - 1), cj[ok][:, None]]
        r = r.assign(_ok=ok & ~np.isnan(T).any(axis=1))
        out[name] = (r[r._ok].drop(columns="_ok"), T[r._ok.values])
    return out


def timing_block(pred, tru, tau, mask, label):
    """Event detection and timing errors on the rows selected by `mask`."""
    detected = pred["prob"] >= tau
    ev = tru["event"]
    tp, fn, fp, tn = (detected & ev & mask).sum(), (~detected & ev & mask).sum(), (detected & ~ev & mask).sum(), (~detected & ~ev & mask).sum()
    out = dict(rows=int(mask.sum()), events=int((ev & mask).sum()), hits=int(tp), misses=int(fn), false_alarms=int(fp), correct_quiet=int(tn),
               precision=float(tp / max(tp + fp, 1)), recall=float(tp / max(tp + fn, 1)), false_alarm_rate=float(fp / max(fp + tn, 1)))
    h = detected & ev & mask & pred["has_onset"]
    if h.sum():
        e_on = pred["on_likely"][h] - tru["onset"][h]
        inside_on = (tru["onset"][h] >= pred["on_early"][h]) & (tru["onset"][h] <= pred["on_late"][h])
        e_pk = pred["pk_likely"][h] - tru["peak_k"][h]
        inside_pk = (tru["peak_k"][h] >= pred["pk_early"][h]) & (tru["peak_k"][h] <= pred["pk_late"][h])
        out.update(onset_err_h_median=float(np.median(e_on)), onset_err_h_mae=float(np.abs(e_on).mean()), onset_err_h_p90_abs=float(np.percentile(np.abs(e_on), 90)),
                   onset_bias_h=float(e_on.mean()), onset_window_coverage=float(inside_on.mean()), onset_window_width_h_median=float(np.median(pred["on_late"][h] - pred["on_early"][h])),
                   peak_err_h_median=float(np.median(e_pk)), peak_err_h_mae=float(np.abs(e_pk).mean()), peak_err_h_p90_abs=float(np.percentile(np.abs(e_pk), 90)),
                   peak_window_coverage=float(inside_pk.mean()), peak_window_width_h_median=float(np.median(pred["pk_late"][h] - pred["pk_early"][h])), timing_n=int(h.sum()))
    return {label: out}


def main():
    F = Forecaster.load()
    df = build()
    data = rows_and_truth(df)
    res = {"note": "S_6 fits, S_7 reports; event = >=3 consecutive hours above the gauge mark within 24 h"}
    S = {}
    for name, (r, T) in data.items():
        Q = trajectories(F, r[FEATURES])
        S[name] = dict(r=r, T=T, Q_raw=Q, tru=truth_summary(T), y=truth_summary(T)["event"].astype(int))
        print(name, "rows", len(r), "events", int(S[name]["y"].sum()), flush=True)

    # --- interval widening (split conformal on S_6 raw quantiles), then everything downstream uses the WIDENED trajectory
    widen = {}
    s6r = S["S_6"]
    for k in LEADS:
        y = s6r["T"][:, k - 1]
        score = np.maximum(s6r["Q_raw"][0][:, k - 1] - y, y - s6r["Q_raw"][2][:, k - 1])
        widen[k] = float(max(0.0, np.quantile(score, 0.8)))  # smallest widening giving 80% q10-q90 coverage on S_6
    wk = np.interp(KS, LEADS, [widen[k] for k in LEADS])
    for v in S.values():
        v["Q"] = v["Q_raw"] + np.array([-wk, 0 * wk, wk])[:, None, :]
        v["pred"] = predict_summary(v["Q"])

    # --- vectorised summary == the Risk agent's derive() on the same trajectories (guards the numpy re-implementation)
    from datetime import datetime, timedelta, timezone
    from app.agents.risk import derive
    from app.schemas import DepthQuantiles, DepthStep, DepthTrajectory
    s7 = S["S_7"]
    t0 = datetime(2022, 1, 1, tzinfo=timezone.utc)
    rng = np.random.default_rng(0)
    for i in rng.choice(len(s7["r"]), 150, replace=False):
        q10, q50, q90 = s7["Q"][:, i]
        tr = DepthTrajectory(zone_id="z", issue_ts=t0, model="m", is_simulated=False, drivers=[],
                             steps=[DepthStep(t=t0 + timedelta(hours=int(k)), depth_m=DepthQuantiles(q10=q10[k - 1], q50=q50[k - 1], q90=q90[k - 1])) for k in KS])
        d = derive(tr)
        pr = s7["pred"]
        assert abs(d.probability - round(pr["prob"][i], 2)) <= 0.011, ("prob", i, d.probability, pr["prob"][i])
        assert (d.onset is None) == (not pr["has_onset"][i])
        if d.onset:
            assert int((d.onset.likely - t0).total_seconds() / 3600) == pr["on_likely"][i] and int((d.peak.likely - t0).total_seconds() / 3600) == pr["pk_likely"][i]
    print("vectorised summary matches risk.derive on 150 random trajectories", flush=True)

    # --- fit on S_6: probability map, alert threshold, interval widening, severity cuts
    s6 = S["S_6"]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(s6["pred"]["prob"], s6["y"])
    cal6 = iso.predict(s6["pred"]["prob"])
    ts = np.linspace(0.05, 0.95, 91)
    f1 = []
    for t in ts:
        d = cal6 >= t
        tp = (d & (s6["y"] == 1)).sum()
        f1.append(2 * tp / max(d.sum() + s6["y"].sum(), 1))
    tau = float(ts[int(np.argmax(f1))])
    ev6 = s6["tru"]["event"]
    c1, c2 = np.quantile(s6["tru"]["peak_excess"][ev6], [0.5, 0.9])
    pos6 = cal6 >= tau
    d1, d2 = np.quantile(s6["pred"]["pk_level"][pos6], [0.5, 0.9])
    cal = dict(alert_threshold=tau, iso_x=[float(x) for x in iso.X_thresholds_], iso_y=[float(y) for y in iso.y_thresholds_],
               widen={str(k): v for k, v in widen.items()}, severity_cuts_pred=[float(d1), float(d2)], severity_cuts_true=[float(c1), float(c2)],
               fitted_on="S_6", rows=int(len(s6["y"])))
    (ROOT / "backend" / "models_store" / "calibration_v2.json").write_text(json.dumps(cal, indent=1))
    res["fitted_on_S_6"] = {k: v for k, v in cal.items() if k not in ("iso_x", "iso_y")}

    # --- report on S_7
    prob7 = s7["pred"]["prob"]
    cal7 = iso.predict(prob7)
    y7 = s7["y"]
    res["probability"] = dict(
        base_rate=float(y7.mean()), pr_auc=float(average_precision_score(y7, prob7)),
        brier_raw=float(brier_score_loss(y7, prob7)), brier_calibrated=float(brier_score_loss(y7, cal7)),
        ece_raw=ece(prob7, y7), ece_calibrated=ece(cal7, y7),
        reliability_calibrated=[dict(bin=f"{lo:.1f}-{lo + .1:.1f}", n=int(m.sum()), predicted=float(cal7[m].mean()), observed=float(y7[m].mean()))
                                for lo in np.arange(0, 1, .1) if (m := (cal7 >= lo) & (cal7 < lo + .1 + (lo > .85) * 1e-9)).sum() > 0])
    # detection and timing with the calibrated probability as the decision score
    pred7 = dict(s7["pred"], prob=cal7)
    below = s7["r"].level.values < 0
    res["detection_and_timing"] = {}
    for label, mask in (("all", np.ones(len(y7), bool)), ("starting_below_mark", below), ("already_above_mark", ~below)):
        res["detection_and_timing"].update(timing_block(pred7, s7["tru"], tau, mask, label))
    byband = {}
    for lo, hi in ((1, 6), (7, 12), (13, 24)):
        m = below & s7["tru"]["event"] & (s7["tru"]["onset"] >= lo) & (s7["tru"]["onset"] <= hi)
        byband[f"true_onset_{lo}-{hi}h"] = dict(events=int(m.sum()), detected=int((m & (cal7 >= tau)).sum()), recall=float((m & (cal7 >= tau)).sum() / max(m.sum(), 1)))
    res["recall_by_true_onset_band_(starting_below)"] = byband
    # interval coverage before/after widening, per lead
    cov = {}
    for k in LEADS:
        y = s7["T"][:, k - 1]
        q10, q90 = s7["Q_raw"][0][:, k - 1], s7["Q_raw"][2][:, k - 1]
        cov[str(k)] = dict(raw=float(((y >= q10) & (y <= q90)).mean()), widened=float(((y >= q10 - widen[k]) & (y <= q90 + widen[k])).mean()), widen=widen[k])
    res["interval_coverage_q10_q90"] = cov
    # severity: true class by S_6 event-peak quantiles, predicted class by S_6 predicted-peak quantiles
    te = s7["tru"]
    true_cls = np.where(~te["event"], 0, np.where(te["peak_excess"] < c1, 1, np.where(te["peak_excess"] < c2, 2, 3)))
    det = cal7 >= tau
    pk = s7["pred"]["pk_level"]
    pred_cls = np.where(~det, 0, np.where(pk < d1, 1, np.where(pk < d2, 2, 3)))
    conf = pd.crosstab(pd.Categorical([SEV[i] for i in true_cls], SEV), pd.Categorical([SEV[i] for i in pred_cls], SEV), rownames=["true"], colnames=["pred"])
    per = {}
    for i, name in enumerate(SEV):
        tp = int(((true_cls == i) & (pred_cls == i)).sum())
        per[name] = dict(true_n=int((true_cls == i).sum()), pred_n=int((pred_cls == i).sum()), precision=float(tp / max((pred_cls == i).sum(), 1)), recall=float(tp / max((true_cls == i).sum(), 1)))
    res["severity"] = dict(confusion=conf.values.tolist(), per_class=per, within_one_class=float((np.abs(true_cls - pred_cls) <= 1).mean()), exact=float((true_cls == pred_cls).mean()),
                           old_placeholder_cuts_pred_share=float(((pk >= 0.15) & det).mean()))
    (PROC / "metrics_validation_v2.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("fitted_on_S_6", "probability")}, indent=1)[:1800])
    for k in ("detection_and_timing", "recall_by_true_onset_band_(starting_below)", "interval_coverage_q10_q90"):
        print("\n" + k)
        print(pd.DataFrame(res[k]).T.round(3).to_string())
    print("\nseverity confusion (rows true, cols pred):\n", conf.to_string())
    print(pd.DataFrame(per).T.round(3).to_string(), "\nwithin one class:", round(res["severity"]["within_one_class"], 3), "exact:", round(res["severity"]["exact"], 3))


if __name__ == "__main__":
    main()
