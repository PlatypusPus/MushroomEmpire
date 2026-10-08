"""Ranking agent: transparent weighted sum. Recommends an order, never dispatches."""

from app.schemas import ExposureItem, RiskOutput, Weights

SEVERITY_SCORE = {"low": 0.0, "moderate": 0.33, "high": 0.67, "severe": 1.0}
LABELS = {
    "probability": "high probability",
    "severity": "expected severity",  # neutral wording: the zone's actual class (moderate, severe) is shown beside it
    "urgency": "early onset",
    "exposure": "many exposed assets",
    "vulnerable": "hospital or shelter in zone",
    "uncertainty": "wide timing uncertainty",
}


def terms(risk: RiskOutput, exp: list[ExposureItem], max_exp: int, max_vul: int) -> dict[str, float]:
    vul = sum(e.type in ("hospital", "shelter") for e in exp)
    if risk.onset:
        lead_h = (risk.onset.likely - risk.issue_ts).total_seconds() / 3600
        urgency = 1 / (1 + max(lead_h, 0) / 6)
        width = (risk.onset.latest - risk.onset.earliest).total_seconds() / 3600 / risk.horizon_h
    else:
        urgency = width = 0.0
    return {
        "probability": risk.probability,
        "severity": SEVERITY_SCORE[risk.severity],
        "urgency": urgency,
        "exposure": len(exp) / max_exp if max_exp else 0.0,
        "vulnerable": vul / max_vul if max_vul else 0.0,
        "uncertainty": width,
    }


def rank(zones: list[tuple[RiskOutput, list[ExposureItem]]], w: Weights) -> list[tuple[str, float, str]]:
    """-> [(zone_id, score, reason)] best first."""
    max_exp = max((len(e) for _, e in zones), default=0)
    max_vul = max((sum(x.type in ("hospital", "shelter") for x in e) for _, e in zones), default=0)
    wd = w.model_dump()
    out = []
    for risk, exp in zones:
        parts = {k: wd[k] * v for k, v in terms(risk, exp, max_exp, max_vul).items()}
        top = [LABELS[k] for k, v in sorted(parts.items(), key=lambda kv: -kv[1]) if v > 0][:2]
        out.append((risk.zone_id, sum(parts.values()), ", ".join(top).capitalize() or "No risk factors"))
    return sorted(out, key=lambda x: -x[1])
