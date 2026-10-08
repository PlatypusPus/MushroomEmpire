"""Dedicated peak-time model: when, within the next 24 h, does the stage peak? (given that a high-water event occurs)

Run from backend/: uv run python -m scripts.sf_peak [--save]
Truth: an event is >= 3 consecutive hours above the gauge's train-only q95; the peak hour is the MEDIAN hour among those within
0.05 stage units of the maximum (plain argmax is arbitrary on flat peaks). Train S_5 (issues every 3 h), select/early-stop on
S_6, report on S_7. Models are trained on event rows only (a timing model is conditional on an event). Compared with trivial
baselines: a fixed hour, and an issue-hour prior (empirical peak distribution for the same hour of day).
Feature groups: base12 (the served features), clock (hour, month), tide (predicted astronomical tide timing: hours to the next
high and low tide and the predicted tide shape; known in advance, from NOAA), geo (gauge lat/lon).
Writes data/processed/metrics_peak.json (+ models_store/peak_v1.joblib with --save).
"""
import json
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from app.models.lightgbm_model import FEATURES as BASE12
from scripts import sf_tide_experiment as TE
from scripts.sf_train import TRAIN_END, VAL_END, build

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
KS = np.arange(1, 25)
NEAR = 0.05  # stage units: hours this close to the maximum count as "at the peak"


def truth(df):
    """Per-row 24 h stage above the mark; returns T (n,24) float32."""
    h = pd.read_parquet(PROC / "sf_hourly.parquet", columns=["station", "var", "ts", "interp"])
    I = h[h["var"] == "WATER"].pivot(index="ts", columns="station", values="interp").sort_index()
    thr = I[I.index < TRAIN_END].quantile(0.95)
    Iw = (I - thr).to_numpy(dtype="float32")
    tpos = {t: i for i, t in enumerate(I.index)}
    col = {s: j for j, s in enumerate(I.columns)}
    ti = np.array([tpos[t] for t in df.index])
    cj = np.array([col[s] for s in df.station])
    idx = ti[:, None] + KS[None, :]
    ok = idx.max(axis=1) < Iw.shape[0]
    T = np.full((len(df), 24), np.nan, dtype="float32")
    T[ok] = Iw[idx[ok], cj[ok][:, None]]
    return T


def summarise(T):
    pos = T > 0
    run3 = pos[:, :-2] & pos[:, 1:-1] & pos[:, 2:]
    ev = run3.any(axis=1) & ~np.isnan(T).any(axis=1)
    mx = np.nanmax(np.where(np.isnan(T), -np.inf, T), axis=1)
    near = (T >= (mx - NEAR)[:, None]) & ~np.isnan(T)
    cs = near.cumsum(axis=1)
    peak = (cs >= (cs[:, -1:] / 2)).argmax(axis=1) + 1  # median hour among the near-max hours
    return ev, peak


def tide_timing(df):
    """Hours to the next two predicted high tides and next low tide, plus the predicted tide shape over the next 24 h."""
    st = pd.read_csv(PROC / "sf_subset_stations.csv").query("`var` == 'WATER'").set_index("station")
    near = {n: min(TE.STATIONS, key=lambda s: (TE.STATIONS[s][0] - r.lat) ** 2 + (TE.STATIONS[s][1] - r.lon) ** 2) for n, r in st.iterrows()}
    cols = ["hi1", "hi2", "lo1"] + [f"tide_rel_{k}" for k in (3, 6, 9, 12, 15, 18, 21, 24)]
    out = pd.DataFrame(np.nan, index=range(len(df)), columns=cols)
    T = TE.tide_frames()
    for sid, (_, p) in T.items():
        idx = pd.date_range(p.index.min(), p.index.max(), freq="h")
        p = p.reindex(idx).interpolate(limit=3)
        v = p.to_numpy()
        hi = np.where((v[1:-1] > v[:-2]) & (v[1:-1] >= v[2:]))[0] + 1
        lo = np.where((v[1:-1] < v[:-2]) & (v[1:-1] <= v[2:]))[0] + 1
        fwd = p[::-1].rolling(24, min_periods=12).mean()[::-1].shift(-1).to_numpy()  # mean of t+1 .. t+24
        m = (df.station.map(near) == sid).to_numpy()
        pos = idx.get_indexer(df.index[m])
        good = pos >= 0
        pos_ = np.where(good, pos, 0)
        j = np.searchsorted(hi, pos_ + 1)
        jl = np.searchsorted(lo, pos_ + 1)
        rows = np.where(m)[0]
        vals = {"hi1": np.where(j < len(hi), hi[np.minimum(j, len(hi) - 1)] - pos_, np.nan),
                "hi2": np.where(j + 1 < len(hi), hi[np.minimum(j + 1, len(hi) - 1)] - pos_, np.nan),
                "lo1": np.where(jl < len(lo), lo[np.minimum(jl, len(lo) - 1)] - pos_, np.nan)}
        for k in (3, 6, 9, 12, 15, 18, 21, 24):
            vals[f"tide_rel_{k}"] = np.where(pos_ + k < len(v), v[np.minimum(pos_ + k, len(v) - 1)] - fwd[pos_], np.nan)
        for c, a in vals.items():
            out.loc[rows[good], c] = a[good]
    out.index = df.index
    return out


def rps(P, y):
    """Ranked probability score of a 24-class distribution against the realised hour (lower is better)."""
    cdf = P.cumsum(axis=1)
    obs = (np.arange(24)[None, :] >= (y[:, None] - 1)).astype(float)
    return ((cdf - obs) ** 2).sum(axis=1) / 23


def quantile_from_p(P, q):
    return (P.cumsum(axis=1) >= q).argmax(axis=1) + 1


def prior_table(train_peak, train_hour):
    pri = {}
    for h in range(24):
        pk = train_peak[train_hour == h]
        pri[h] = np.bincount(pk - 1, minlength=24).astype(float) + 0.5  # light smoothing
        pri[h] /= pri[h].sum()
    return pri


def main():
    save = "--save" in sys.argv
    df = build()
    df["hour"], df["month"] = df.index.hour, df.index.month
    st = pd.read_csv(PROC / "sf_subset_stations.csv").query("`var` == 'WATER'").set_index("station")
    df["lat"], df["lon"] = df.station.map(st.lat).values, df.station.map(st.lon).values
    idx = df.index
    sets = {"train": df[(idx < TRAIN_END) & (idx.hour % 3 == 0)], "val": df[(idx >= TRAIN_END) & (idx < VAL_END) & (idx.hour % 3 == 0)],
            "test": df[(idx >= VAL_END) & (idx.hour % 3 == 0)]}
    data = {}
    for name, d in sets.items():
        d = pd.concat([d, tide_timing(d)], axis=1)
        T = truth(d)
        ev, peak = summarise(T)
        data[name] = dict(d=d[ev], peak=peak[ev], T=T[ev], n_rows=len(d))
        print(name, "rows", len(d), "events", int(ev.sum()), flush=True)
    clock = ["hour", "month"]
    tide = ["hi1", "hi2", "lo1"] + [f"tide_rel_{k}" for k in (3, 6, 9, 12, 15, 18, 21, 24)]
    geo = ["lat", "lon"]
    groups = {"base12": BASE12, "base12+clock": BASE12 + clock, "base12+clock+tide": BASE12 + clock + tide, "base12+clock+tide+geo": BASE12 + clock + tide + geo,
              "clock+tide only": clock + tide}
    tr, va, te = data["train"], data["val"], data["test"]
    pri = prior_table(tr["peak"], tr["d"].hour.values)
    glob = int(np.median(tr["peak"]))
    res = {"events": {k: int(len(v["peak"])) for k, v in data.items()}, "peak_definition": f"median hour among hours within {NEAR} of the max", "variants": {}}

    def evaluate(P, peak, hour, label):
        lik = quantile_from_p(P, 0.5)
        lo, hi = quantile_from_p(P, 0.1), quantile_from_p(P, 0.9)
        return dict(label=label, mae_h=float(np.abs(lik - peak).mean()), median_ae_h=float(np.median(np.abs(lik - peak))), within_3h=float((np.abs(lik - peak) <= 3).mean()),
                    window80_coverage=float(((peak >= lo) & (peak <= hi)).mean()), window80_width_h_median=float(np.median(hi - lo + 1)), rps=float(rps(P, peak).mean()))
    for name, v in (("val", va), ("test", te)):
        hr = v["d"].hour.values
        Pprior = np.stack([pri[h] for h in hr])
        res["variants"].setdefault("baseline_fixed_hour", {})[name] = dict(mae_h=float(np.abs(glob - v["peak"]).mean()), fixed_hour=glob)
        res["variants"].setdefault("baseline_issue_hour_prior", {})[name] = evaluate(Pprior, v["peak"], hr, "prior")
    best = None
    for gname, feats in groups.items():
        m = lgb.LGBMClassifier(objective="multiclass", n_estimators=400, learning_rate=0.06, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1,
                               colsample_bytree=0.8, verbose=-1)
        m.fit(tr["d"][feats], tr["peak"] - 1, eval_set=[(va["d"][feats], va["peak"] - 1)], callbacks=[lgb.early_stopping(25, verbose=False)])
        out = {}
        for name, v in (("val", va), ("test", te)):
            P = np.zeros((len(v["peak"]), 24))
            P[:, m.classes_] = m.predict_proba(v["d"][feats])
            out[name] = evaluate(P, v["peak"], v["d"].hour.values, gname)
            if name == "test":
                below = v["d"].level.values < 0
                for tag, mask in (("starting_below", below), ("already_above", ~below)):
                    out[f"test_{tag}"] = evaluate(P[mask], v["peak"][mask], v["d"].hour.values[mask], gname)
                    out[f"test_{tag}"]["rows"] = int(mask.sum())
                days = np.asarray(v["d"].index.date)
                Pp = np.stack([pri[h] for h in v["d"].hour.values])
                rng = np.random.default_rng(0)
                ud = np.unique(days)
                rows = {d: np.where(days == d)[0] for d in ud}
                diffs = []
                lik = quantile_from_p(P, 0.5)
                lik0 = quantile_from_p(Pp, 0.5)
                e1, e0 = np.abs(lik - v["peak"]), np.abs(lik0 - v["peak"])
                for _ in range(300):
                    ii = np.concatenate([rows[d] for d in rng.choice(ud, len(ud))])
                    diffs.append(e1[ii].mean() - e0[ii].mean())
                out["test"]["mae_diff_vs_prior_ci95"] = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
        out["trees"] = int(m.best_iteration_ or m.n_estimators)
        res["variants"][gname] = out
        print(gname, {k: round(v, 3) if isinstance(v, float) else v for k, v in out["val"].items() if k != "label"}, flush=True)
        out["_model"] = (m, feats)
    # choose the SIMPLEST variant within 0.1 h of the best validation MAE (gauge lat/lon can act as a fingerprint and need zone coordinates at serving)
    order = list(groups)
    top = min(res["variants"][g]["val"]["mae_h"] for g in order)
    chosen = next(g for g in order if res["variants"][g]["val"]["mae_h"] <= top + 0.1 and g != "clock+tide only")
    m, feats = res["variants"][chosen].pop("_model")
    best = (res["variants"][chosen]["val"]["mae_h"], chosen, m, feats)
    for g in order:
        res["variants"][g].pop("_model", None)
    res["best_on_val"] = chosen
    # window: symmetric central interval tuned on VAL to cover 80%, then reported on TEST
    def window(P, a):
        return quantile_from_p(P, a), quantile_from_p(P, 1 - a)
    Pv = np.zeros((len(va["peak"]), 24)); Pv[:, m.classes_] = m.predict_proba(va["d"][feats])
    Pt = np.zeros((len(te["peak"]), 24)); Pt[:, m.classes_] = m.predict_proba(te["d"][feats])
    alphas = np.arange(0.05, 0.31, 0.01)
    cov = [((va["peak"] >= window(Pv, a)[0]) & (va["peak"] <= window(Pv, a)[1])).mean() for a in alphas]
    a_star = float(alphas[int(np.argmin(np.abs(np.array(cov) - 0.80)))])
    lo, hi = window(Pt, a_star)
    res["window"] = dict(alpha=a_star, val_coverage=float(min(cov, key=lambda c: abs(c - 0.80))), test_coverage=float(((te["peak"] >= lo) & (te["peak"] <= hi)).mean()),
                         test_width_h_median=float(np.median(hi - lo + 1)))
    (PROC / "metrics_peak.json").write_text(json.dumps(res, indent=1))
    if save:
        joblib.dump({"model": best[2], "features": best[3], "name": best[1], "classes": best[2].classes_, "window_alpha": a_star}, ROOT / "backend" / "models_store" / "peak_v1.joblib")
    show = ["baseline_fixed_hour", "baseline_issue_hour_prior"] + list(groups)
    rows_ = []
    for k in show:
        v = res["variants"][k]["test"]
        rows_.append({"variant": k, **{a: round(b, 3) for a, b in v.items() if isinstance(b, float) and a != "fixed_hour"}})
    print(pd.DataFrame(rows_).to_string(index=False))
    print("chosen (simplest within 0.1 h of best on val):", best[1], "| window:", res["window"])
    print("test MAE diff vs prior (95% CI), best:", res["variants"][best[1]]["test"].get("mae_diff_vs_prior_ci95"))
    print("starting below:", {k: round(v, 3) for k, v in res["variants"][best[1]]["test_starting_below"].items() if isinstance(v, float)})
    print("already above :", {k: round(v, 3) for k, v in res["variants"][best[1]]["test_already_above"].items() if isinstance(v, float)})


if __name__ == "__main__":
    main()
