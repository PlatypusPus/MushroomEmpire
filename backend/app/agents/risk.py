"""Risk derivation agent: probability, severity, onset and peak from ONE trajectory. No ML."""

from app.schemas import DepthTrajectory, RiskOutput, Severity, TimeWindow

# ponytail: uncalibrated placeholders; lane B replaces with values fitted on the validation split (S_6)
TAIL_P = 0.05
SEVERITY_M = [(0.15, "moderate"), (0.45, "high")]  # peak q50 above threshold, metres; above last = severe
MIN_P_FOR_SEVERITY = 0.3


def p_exceed(q10: float, q50: float, q90: float, x: float = 0.0) -> float:
    """P(level > x) from three quantiles, piecewise-linear CDF, clamped tails."""
    if x <= q10:
        return 1 - TAIL_P
    if x >= q90:
        return TAIL_P
    lo, hi, plo, phi = (q10, q50, 0.1, 0.5) if x <= q50 else (q50, q90, 0.5, 0.9)
    cdf = plo + (phi - plo) * (x - lo) / (hi - lo) if hi > lo else phi
    return 1 - cdf


def severity_of(peak: float, p: float) -> Severity:
    if p < MIN_P_FOR_SEVERITY or peak <= 0:
        return "low"
    for limit, name in SEVERITY_M:
        if peak < limit:
            return name
    return "severe"


def derive(traj: DepthTrajectory) -> RiskOutput:
    s = traj.steps
    q = [(st.depth_m.q10, st.depth_m.q50, st.depth_m.q90) for st in s]
    prob = max(p_exceed(*x) for x in q)
    peak_i = max(range(len(s)), key=lambda i: q[i][1])
    peak_level = q[peak_i][1]

    def first(cond):
        return next((st.t for st, x in zip(s, q) if cond(x)), None)

    onset = peak = None
    likely = first(lambda x: x[1] > 0)
    if likely:
        onset = TimeWindow(
            earliest=first(lambda x: x[2] > 0),
            likely=likely,
            latest=first(lambda x: x[0] > 0) or s[-1].t,  # q10 never crosses: by end of horizon
        )
        near = [st.t for st, x in zip(s, q) if x[2] >= peak_level]
        peak = TimeWindow(earliest=near[0], likely=s[peak_i].t, latest=near[-1])

    return RiskOutput(
        zone_id=traj.zone_id,
        issue_ts=traj.issue_ts,
        probability=round(prob, 2),
        severity=severity_of(peak_level, prob),
        onset=onset,
        peak=peak,
        peak_level_m=round(peak_level, 2),
        horizon_h=round((s[-1].t - traj.issue_ts).total_seconds() / 3600),
    )
