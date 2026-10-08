"""Critical re-review of the forecasting evaluation and the explainability agent.

Run from backend/: uv run python -m scripts.sf_review
 A. Real flood reports vs the served zone-level agent (the only non-proxy evidence we have)
 B. Day-cluster bootstrap CIs and how concentrated the events are
 C. A stronger baseline than the fixed-spread persistence used so far
 D. Do imputed (interpolated) hours in the target window flatter the metrics?
 E. Explanation checks: phrase validity, strength shares, static-vs-dynamic share
Writes data/processed/metrics_review.json.
"""
import asyncio
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from app import calibration
from app.models.lightgbm_model import FEATURES, LEADS, Forecaster
from scripts import sf_validate as V
from scripts.sf_train import TRAIN_END, VAL_END, build

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"


def s7_arrays(F, df, split="S_7"):
    """Daily rows with truth, WIDENED trajectories and calibrated probability, exactly as the agent serves them."""
    data = V.rows_and_truth(df)
    r, T = data[split]
    Q = V.trajectories(F, r[FEATURES])
    w = calibration.widen(V.KS, LEADS)
    Q = Q + np.array([-w, 0 * w, w])[:, None, :]
    pred = V.predict_summary(Q)
    c = calibration.load()
    pred["prob_raw"] = pred["prob"].copy()
    pred["prob"] = np.interp(pred["prob"], c["iso_x"], c["iso_y"])
    return r, T, Q, pred, V.truth_summary(T), Q


async def section_a_async():
    """Reports (positives only) against the zone-level alerts the dashboard would have shown."""
    from app.orchestrator import run_tick
    from app.store import from_db

    obs = pd.read_csv(PROC / "sf_flood_obs.csv", parse_dates=["date"])
    obs = obs[obs.place_id.notna() & obs.date.between("2020-01-01", "2023-12-31")].copy()
    obs["zone_id"] = obs.place_id.astype("Int64").astype(str)
    tau = calibration.alert_threshold()
    events = await _events()
    alerts, rows = {}, []  # (zone, date) -> max probability over the issue times that cover that date
    for ev in events:
        snap = await from_db(ev["id"])
        t = ev["start_ts"].replace(hour=0, minute=0)
        while t <= ev["end_ts"]:
            for z in run_tick(snap, t):
                if z.probability is not None:
                    rows.append((z.zone_id, t, z.probability, z.onset is not None))
            t += dt.timedelta(hours=12)
    f = pd.DataFrame(rows, columns=["zone_id", "issue", "p", "has_onset"])
    f["date"] = f.issue.dt.tz_localize(None).dt.normalize()
    # a report on date D is covered by issues at D-1 12:00, D 00:00 and D 12:00 (24 h look-ahead each)
    def cover(zone, d):
        m = (f.zone_id == zone) & (f.issue.dt.tz_localize(None) >= d - pd.Timedelta(hours=12)) & (f.issue.dt.tz_localize(None) <= d + pd.Timedelta(hours=12))
        return f[m]
    out = {"alert_threshold": tau, "event_windows": [e["name"] for e in events]}
    res = []
    for r in obs.itertuples():
        c = cover(r.zone_id, r.date)
        res.append(dict(zone=r.zone_id, date=r.date, exact_date=not r.date_is_collection, event=r.EVENT_NAME, assessable=len(c) > 0,
                        alert=bool((c.p >= tau).any()) if len(c) else None, pmax=float(c.p.max()) if len(c) else None))
    R = pd.DataFrame(res)
    in_event = R[R.event.isin([e["name"] for e in events])]
    out["reports_in_holdout_places"] = int(len(R))
    out["reports_in_modelled_event_windows"] = int(len(in_event))
    out["not_assessable_no_usable_gauge_or_outside_window"] = int((~in_event.assessable).sum())
    a = in_event[in_event.assessable]
    # base rate: share of all zone-issue cells in those same windows that are alerted (reports are positives only, so this is the comparison)
    f["alert"] = f.p >= tau
    base = float(f.alert.mean())
    out["assessable_reports"] = int(len(a))
    out["share_of_reports_with_an_alert_covering_them"] = float(a.alert.mean())
    out["share_of_all_zone_issues_alerted_in_same_windows"] = base
    out["lift_vs_all_zone_issues"] = float(a.alert.mean() / base) if base else None
    ex = a[a.exact_date]
    out["exact_date_reports"] = int(len(ex))
    out["exact_date_share_alerted"] = float(ex.alert.mean()) if len(ex) else None
    out["by_event"] = {k: dict(n=int(len(g)), alerted=float(g.alert.mean())) for k, g in a.groupby("event")}
    # a zone-day with a report is a zone-DAY; compare with zone-days (not issues) in the same windows
    zd = f.assign(d=f.issue.dt.tz_localize(None).dt.normalize()).groupby(["zone_id", "d"]).alert.max()
    out["share_of_all_zone_days_alerted_in_same_windows"] = float(zd.mean())
    from sklearn.metrics import roc_auc_score
    pd_ = f.assign(d=f.issue.dt.tz_localize(None).dt.normalize()).groupby(["zone_id", "d"]).p.max()
    rep = {(r.zone_id if hasattr(r, "zone_id") else r.zone, r.date) for r in a.itertuples()} if "zone" in a else set()
    rep = {(z, d) for z, d in zip(a.zone, a.date)}
    lab = np.array([(z, d) in rep for z, d in pd_.index])
    out["zone_day_ranking_auc_reported_vs_not"] = float(roc_auc_score(lab, pd_.values))
    out["zone_days_reported"] = int(lab.sum())
    out["zone_days_in_windows"] = int(len(lab))
    out["median_pmax_reported_vs_not"] = [float(np.median(pd_.values[lab])), float(np.median(pd_.values[~lab]))]
    return out


async def _events():
    from sqlalchemy import text

    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        return [dict(r._mapping) for r in (await s.execute(text("select id, name, start_ts, end_ts from events order by id")))]


def boot_ci(fn, days, reps=300, seed=0):
    rng = np.random.default_rng(seed)
    ud = np.unique(days)
    rows = {d: np.where(days == d)[0] for d in ud}
    vals = []
    for _ in range(reps):
        idx = np.concatenate([rows[d] for d in rng.choice(ud, len(ud))])
        vals.append(fn(idx))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def section_bcd(F, df):
    r, T, Q, pred, tru, _ = s7_arrays(F, df)
    tau = calibration.alert_threshold()
    days = np.asarray(r.index.date)
    below = r.level.values < 0
    det = pred["prob"] >= tau
    ev = tru["event"]
    out = {}
    # B: concentration and cluster-bootstrap CIs
    ed = pd.Series(ev).groupby(days).sum()
    out["B_event_days"] = dict(distinct_days=int(len(ed)), days_with_events=int((ed > 0).sum()),
                               top10_days_share_of_events=float(ed.sort_values(ascending=False).head(10).sum() / ed.sum()))

    def rec(idx, m):
        d, e, b = det[idx], ev[idx], m[idx]
        return (d & e & b).sum() / max((e & b).sum(), 1)

    def prec(idx, m):
        d, e, b = det[idx], ev[idx], m[idx]
        return (d & e & b).sum() / max((d & b).sum(), 1)

    for name, m in (("starting_below_mark", below), ("all", np.ones(len(ev), bool))):
        out[f"B_{name}"] = dict(recall=float(rec(np.arange(len(ev)), m)), recall_ci95=boot_ci(lambda i: rec(i, m), days),
                                precision=float(prec(np.arange(len(ev)), m)), precision_ci95=boot_ci(lambda i: prec(i, m), days))
    h = det & ev & pred["has_onset"]
    out["B_timing_hits"] = dict(n=int(h.sum()),
                                onset_mae_h=float(np.abs(pred["on_likely"][h] - tru["onset"][h]).mean()),
                                peak_mae_h=float(np.abs(pred["pk_likely"][h] - tru["peak_k"][h]).mean()),
                                peak_mae_ci95=boot_ci(lambda i: np.abs(pred["pk_likely"][i][h[i]] - tru["peak_k"][i][h[i]]).mean(), days, reps=150))
    # peak-time reference: always guessing the middle of the window and always guessing "now"
    out["B_timing_hits"]["peak_mae_if_always_hour_12"] = float(np.abs(12 - tru["peak_k"][h]).mean())
    out["B_timing_hits"]["peak_mae_if_always_hour_1"] = float(np.abs(1 - tru["peak_k"][h]).mean())
    out["B_timing_hits"]["onset_mae_if_always_hour_1"] = float(np.abs(1 - tru["onset"][h]).mean())
    # C: a fair baseline: persistence with EMPIRICAL residual quantiles from the training split (not a fixed tiny spread)
    tr = df[(df.index < TRAIN_END) & (df.index.hour % 6 == 0)]
    pb = np.zeros(len(r))
    for k in LEADS:
        base_tr = tr.level + tr.trend * min(k, 6)
        res = (tr[f"y{k}"] - base_tr).dropna()
        qs = res.quantile([0.1, 0.5, 0.9]).values
        b = r.level.values + r.trend.values * min(k, 6)
        pb = np.maximum(pb, V.p_exceed_v(b + qs[0], b + qs[1], b + qs[2]))
    rule = ((r.level.values > 0) | (r.max_24h.values > 0)).astype(float)  # "alert if the gauge is, or today was, above its mark"
    for name, score in (("model_calibrated", pred["prob"]), ("persistence_empirical_spread", pb), ("rule_above_mark_now_or_today", rule)):
        out.setdefault("C_baselines", {})[name] = dict(
            any_pr_auc=float(average_precision_score(ev, score)), onset_pr_auc=float(average_precision_score(ev[below], score[below])),
            recall_below_at_same_alert_rate=None)
    # match alert rate: choose each score's threshold so that it alerts the same share of 'below' rows as the model does at tau
    rate = det[below].mean()
    for name, score in (("persistence_empirical_spread", pb), ("rule_above_mark_now_or_today", rule)):
        thr = np.quantile(score[below], 1 - rate) if rate > 0 else 1
        d = score[below] >= thr if thr > 0 else score[below] > 0
        out["C_baselines"][name]["recall_below_at_same_alert_rate"] = float((d & ev[below]).sum() / max(ev[below].sum(), 1))
        out["C_baselines"][name]["precision_below_at_same_alert_rate"] = float((d & ev[below]).sum() / max(d.sum(), 1))
    out["C_baselines"]["model_calibrated"]["recall_below_at_same_alert_rate"] = float((det[below] & ev[below]).sum() / max(ev[below].sum(), 1))
    out["C_baselines"]["model_calibrated"]["precision_below_at_same_alert_rate"] = float((det[below] & ev[below]).sum() / max(det[below].sum(), 1))
    out["C_baselines"]["alert_rate_below_rows"] = float(rate)
    # F1: how much onset skill is a NEW rise vs a gauge re-crossing a mark it was above in the last 72 h?
    fresh = below & ~(r.max_72h.values > 0)
    for name, m in (("fresh_no_exceedance_in_last_72h", fresh), ("re_entry_was_above_in_last_72h", below & ~fresh)):
        e_, d_ = ev & m, det & m
        out.setdefault("F1_onset_split", {})[name] = dict(rows=int(m.sum()), events=int(e_.sum()), recall=float((d_ & e_).sum() / max(e_.sum(), 1)),
                                                          precision=float((d_ & e_).sum() / max(d_.sum(), 1)), event_rate=float(e_.sum() / max(m.sum(), 1)))
    # F2: peak-time estimators; pick on S_6, report on S_7
    def peak_estimators(Q_):
        q50 = Q_[1]
        pos = np.clip(q50, 0, None)
        k = V.KS[None, :]
        com = np.where(pos.sum(1) > 0, (pos * k).sum(1) / np.maximum(pos.sum(1), 1e-12), q50.argmax(1) + 1)
        near = q50 >= (q50.max(axis=1, keepdims=True) - 0.05 * np.abs(q50.max(axis=1, keepdims=True)) - 1e-9)
        return {"argmax_q50": q50.argmax(1) + 1, "centre_of_mass_of_positive_q50": np.round(com), "first_within_5pct_of_max": near.argmax(1) + 1,
                "last_within_5pct_of_max": 24 - near[:, ::-1].argmax(1), "fixed_hour_12": np.full(len(q50), 12)}
    r6, T6, Q6, pred6, tru6, _ = s7_arrays(F, df, "S_6")
    h6 = (pred6["prob"] >= tau) & tru6["event"]
    E6, E7 = peak_estimators(Q6), peak_estimators(Q)
    sel = {n: float(np.abs(v[h6] - tru6["peak_k"][h6]).mean()) for n, v in E6.items()}
    h7 = det & ev
    out["F2_peak_estimators"] = {"S_6_mae_h": sel, "S_7_mae_h": {n: float(np.abs(v[h7] - tru["peak_k"][h7]).mean()) for n, v in E7.items()},
                                 "best_on_S_6": min(sel, key=sel.get), "hits_S_7": int(h7.sum())}
    # D: imputed hours inside the 24 h target window
    h = pd.read_parquet(PROC / "sf_hourly.parquet", columns=["station", "var", "ts", "value"])
    Vw = h[h["var"] == "WATER"].pivot(index="ts", columns="station", values="value").sort_index()
    miss = Vw.isna().to_numpy()
    tpos = {t: i for i, t in enumerate(Vw.index)}
    col = {s: j for j, s in enumerate(Vw.columns)}
    ti = np.array([tpos[t] for t in r.index])
    cj = np.array([col[s] for s in r.station])
    idx = np.minimum(ti[:, None] + V.KS[None, :], miss.shape[0] - 1)
    imp = miss[idx, cj[:, None]].any(axis=1)
    out["D_imputed_in_target_window"] = dict(share_of_rows=float(imp.mean()))
    clean = ~imp
    d, e = det[clean], ev[clean]
    out["D_imputed_in_target_window"].update(
        recall_clean=float((d & e).sum() / max(e.sum(), 1)), precision_clean=float((d & e).sum() / max(d.sum(), 1)),
        recall_all=float((det & ev).sum() / max(ev.sum(), 1)), precision_all=float((det & ev).sum() / max(det.sum(), 1)),
        onset_pr_auc_clean=float(average_precision_score(e[below[clean]], pred["prob"][clean][below[clean]])))
    return out, r, pred, tru


def section_e(F, df, r, pred):
    """Explanation checks on the alerted S_7 rows, using the peak-lead attribution the agent now uses."""
    tau = calibration.alert_threshold()
    alert = pred["prob"] >= tau
    A = r[FEATURES][alert]
    lead = np.array([min(LEADS, key=lambda L: abs(L - k)) for k in pred["pk_likely"][alert]])
    C = pd.DataFrame(0.0, index=A.index, columns=FEATURES)
    for L in np.unique(lead):
        m = lead == L
        C.iloc[np.where(m)[0]] = F.models[(int(L), 0.5)].predict(A[m], pred_contrib=True)[:, :-1]
    from app.agents.explain import THEME
    out = {"alerted_rows": int(alert.sum())}
    th = {f: THEME.get(f if f not in ("level", "trend") else {"level": "level_m", "trend": "level_trend"}[f], f) for f in FEATURES}
    th = {f: THEME.get({"level": "level_m", "trend": "level_trend", "change_6h": "level_change_6h", "change_24h": "level_change_24h", "max_24h": "level_max_24h",
                        "max_72h": "level_max_72h", "std_24h": "level_std_24h"}.get(f, f), f) for f in FEATURES}
    T = C.T.groupby(th).sum().T  # theme contributions (net of negatives)
    pos = T.clip(lower=0)
    share_pos = pos.div(pos.sum(axis=1), axis=0)
    # E1 'close to its usual mark': how far below the mark is the gauge when that phrase would be used?
    lvl_main = share_pos["level"] >= 0.5
    close = lvl_main & (A.level <= 0) & ~(A.max_24h > 0) & ~(A.max_72h > 0)
    out["E1_close_to_mark_phrase"] = dict(rows=int(close.sum()), level_median=float(A.level[close].median()) if close.any() else None,
                                          level_p10=float(A.level[close].quantile(0.1)) if close.any() else None,
                                          share_more_than_half_unit_below=float((A.level[close] < -0.5).mean()) if close.any() else None)
    # E2 strength words: positive-only shares vs net shares (negatives ignored by the agent)
    net = T.clip(lower=0).sum(axis=1)
    neg = (-T.clip(upper=0)).sum(axis=1)
    out["E2_negatives_ignored"] = dict(median_negative_to_positive_ratio=float((neg / net.replace(0, np.nan)).median()),
                                       share_rows_where_negatives_exceed_half_of_positives=float((neg > 0.5 * net).mean()),
                                       share_main_reason_pos_only=float((share_pos.max(axis=1) >= 0.5).mean()),
                                       share_main_reason_if_negatives_count=float(((T.clip(lower=0).max(axis=1) / (net + neg)) >= 0.5).mean()))
    # E3 static vs dynamic: how much of the terrain theme is the same every day for a gauge (a standing vulnerability, not a "why now")?
    g = r.station[alert]
    terr = T["terrain"]
    within = terr.groupby(g.values).transform(lambda x: x - x.mean())
    out["E3_terrain_between_gauge_variance_share"] = float(1 - within.var() / terr.var()) if terr.var() > 0 else None
    out["E3_terrain_share_of_positive_total_median"] = float(share_pos["terrain"].median())
    # E4 reason count
    out["E4_themes_over_5pct_per_row_median"] = float((share_pos >= 0.05).sum(axis=1).median())
    return out


def main():
    F = Forecaster.load()
    df = build()
    out = {}
    out["BCD"], r, pred, tru = section_bcd(F, df)
    out["E"] = section_e(F, df, r, pred)
    out["A"] = asyncio.run(section_a_async())
    (PROC / "metrics_review.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
