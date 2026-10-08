"""Leakage-safe helpers: visibility at an issue time, and ESL-protocol high-water episodes."""
import pandas as pd

AVAIL_LAG = pd.Timedelta(hours=1)  # an hourly mean is only known once the hour is over (assumed: TIMESTAMP = hour start)
MIN_HOURS, MERGE_GAP_H, QUANTILE = 3, 6, 0.95  # ROOT_CONTEXT section 13


def visible(df: pd.DataFrame, issue_ts: pd.Timestamp) -> pd.DataFrame:
    """Only rows whose availability_ts is at or before the issue time (the Ingestion agent's rule)."""
    return df[df["availability_ts"] <= issue_ts]


def threshold(train: pd.Series) -> float:
    """Exceedance threshold from TRAIN data only; never pass validation or holdout values."""
    return float(train.quantile(QUANTILE))


def episodes(series: pd.Series, thr: float) -> pd.DataFrame:
    """High-water episodes: >= MIN_HOURS consecutive hours above thr, gaps <= MERGE_GAP_H merged.

    ponytail: assumes a regular hourly index; SF2Bench has no gaps after interpolation.
    """
    above = series > thr
    runs = (above != above.shift()).cumsum()[above]
    spans = [(g.index[0], g.index[-1]) for _, g in series[above].groupby(runs)]
    merged: list[list[pd.Timestamp]] = []
    for s, e in spans:
        if merged and (s - merged[-1][1]) <= pd.Timedelta(hours=MERGE_GAP_H + 1):
            merged[-1][1] = e
        else:
            merged.append([s, e])
    rows = []
    for s, e in merged:
        seg = series[s:e]
        if len(seg) >= MIN_HOURS:  # duration counts the merged span
            rows.append({"start": s, "end": e, "peak_ts": seg.idxmax(), "peak": seg.max(), "hours": len(seg)})
    return pd.DataFrame(rows, columns=["start", "end", "peak_ts", "peak", "hours"])
