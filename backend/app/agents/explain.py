"""Explainability agent: model contributions -> short plain-language reasons. No numbers, no invented facts.

The model's per-feature contributions (exact TreeSHAP from LightGBM) are grouped into themes, because several features
say the same thing (current level, today's max and the 3-day max are one story). Each phrase is then checked against the
feature value it describes, so the text can never claim "rising" for a falling gauge. Audit: scripts/sf_explain_audit.py.
"""

from app.schemas import Driver, FeatureVector, Reason

# legacy one-feature phrases: used when no FeatureVector is given (and by tests / the persistence baseline's drivers)
PHRASES = {
    "level_m": "water level is high now",
    "level_trend": "water rising fast",
    "rain_6h": "recent rain",
    "rain_24h": "recent rain",
    "rain_72h": "several days of rain",
    "hand_m": "low ground next to drainage",
    "elevation_m": "low elevation",
    "level_change_6h": "water rising fast",
    "level_change_24h": "water rising over the day",
    "level_max_24h": "water was high earlier today",
    "level_max_72h": "water was high in recent days",
    "level_std_24h": "unsettled water levels",
    "tide_m": "high tide",
    "gate": "flood gate operations",
    "pump": "pump operations",
}
THEME = {
    "level_m": "level", "level_max_24h": "level", "level_max_72h": "level",
    "level_trend": "rise", "level_change_6h": "rise", "level_change_24h": "rise",
    "level_std_24h": "swing", "hand_m": "terrain", "elevation_m": "terrain",
    "rain_6h": "rain", "rain_24h": "rain", "rain_72h": "rain",
}
ELEV_MEDIAN_M, HAND_MEDIAN_M = 3.7, 0.98  # medians over the 109 zones (ROOT_CONTEXT 2e): "low" / "high" ground is judged against these
CLOSE_UNITS = 0.3  # "close to" the mark means within this many stage units below it (audit: 16% of earlier uses were >0.5 below)
MIN_SHARE = 0.05  # themes below 5% of the total contribution are not mentioned


def _pos(x):
    return x is not None and x > 0


def _raising(theme: str, fv: FeatureVector | None) -> str | None:
    """Phrase for a theme that pushes risk UP, or None if the feature values do not support saying it."""
    if fv is None:
        return None
    if theme == "level":
        if fv.level_m > 0:
            return "water is already above its usual high mark"
        if _pos(fv.level_max_24h):
            return "water was above its usual high mark earlier today"
        if _pos(fv.level_max_72h):
            return "water was above its usual high mark in recent days"
        return "water is close to its usual high mark" if fv.level_m >= -CLOSE_UNITS else None  # far below: say nothing rather than something false
    if theme == "rise":
        if fv.level_trend_m_per_h > 0 or _pos(fv.level_change_6h):
            return "water rising"
        return "water higher than a day ago" if _pos(fv.level_change_24h) else None
    if theme == "swing":
        return "water levels going up and down a lot"
    if theme == "terrain":
        low = (fv.elevation_m is not None and fv.elevation_m < ELEV_MEDIAN_M) or (fv.hand_m is not None and fv.hand_m < HAND_MEDIAN_M)
        return "low-lying ground" if low else None
    if theme == "rain":  # rain contributes very little in this data and its direction is unreliable: say "recent", never "heavy"
        return "recent rain" if any(_pos(x) for x in (fv.rain_6h, fv.rain_24h, fv.rain_72h)) else None
    return None


def _protective(theme: str, fv: FeatureVector | None) -> str | None:
    """Phrase for a theme that pushes risk DOWN (used to say why a zone is not expected to be at risk)."""
    if fv is None:
        return None
    if theme == "level":
        return "water is well below its usual high mark" if fv.level_m < 0 else None
    if theme == "rise":
        return "water steady or falling" if fv.level_trend_m_per_h <= 0 and not _pos(fv.level_change_6h) else None
    if theme == "swing":
        return "calm water levels"
    if theme == "terrain":
        high = (fv.elevation_m is not None and fv.elevation_m >= ELEV_MEDIAN_M) or (fv.hand_m is not None and fv.hand_m >= HAND_MEDIAN_M)
        return "higher ground" if high else None
    return None


def explain_detail(drivers: list[Driver], fv: FeatureVector | None = None, at_risk: bool = True, top: int = 3) -> list[Reason]:
    score: dict[str, float] = {}
    for d in drivers:
        c = d.contribution if at_risk else -d.contribution
        if c > 0:
            score[THEME.get(d.feature, d.feature)] = score.get(THEME.get(d.feature, d.feature), 0.0) + c
    total = sum(score.values())
    out: list[Reason] = []
    for theme, s in sorted(score.items(), key=lambda kv: -kv[1]):
        share = s / total
        if share < MIN_SHARE and out:
            continue
        if fv is None:  # no values to check against: fall back to the single-feature phrase
            f = max((d for d in drivers if THEME.get(d.feature, d.feature) == theme), key=lambda d: d.contribution if at_risk else -d.contribution)
            phrase = PHRASES.get(f.feature, f.feature.replace("_", " "))
        else:
            phrase = (_raising if at_risk else _protective)(theme, fv)
        if phrase is None or any(r.phrase == phrase for r in out):
            continue
        strength = "standing factor" if theme == "terrain" else "main reason" if share >= 0.5 else "important" if share >= 0.2 else "minor"
        out.append(Reason(theme=theme, phrase=phrase, strength=strength))
    # terrain is the same every day for a zone (79% of its contribution varies only between gauges): it says why a zone is
    # vulnerable, not why now, so it goes after the dynamic reasons
    out.sort(key=lambda r: r.theme == "terrain")
    return out[:top]


def explain(drivers: list[Driver], top: int = 3, fv: FeatureVector | None = None, at_risk: bool = True) -> list[str]:
    """Plain phrases, strongest first. Same call as before; pass fv to get value-checked, de-duplicated reasons."""
    return [r.phrase for r in explain_detail(drivers, fv, at_risk, top)] or ["no strong drivers" if at_risk else "no strong protective factors"]


def explain_text(reasons: list[Reason], at_risk: bool) -> str:
    """One plain sentence for the UI. Strength words come from the share of the total contribution, never a number."""
    if not reasons:
        return "No single factor stands out."
    dynamic = [r for r in reasons if r.theme != "terrain"]
    ground = [r.phrase for r in reasons if r.theme == "terrain"]
    if not dynamic:  # only the standing terrain factor: be clear it is not a "why now"
        return (f"Nothing unusual in recent water levels. The zone has {ground[0]}, which raises its risk." if at_risk
                else f"Nothing unusual in recent water levels. The zone sits on {ground[0]}.")
    lead = "Main reason" if dynamic[0].strength == "main reason" else "Biggest factor"
    s = f"{lead}{'' if at_risk else ' for the low risk'}: {dynamic[0].phrase}."
    rest = [r.phrase for r in dynamic[1:]]
    if rest:
        s += f" Also: {', '.join(rest)}."
    if ground:
        s += f" Standing factor: {ground[0]}."
    return s


def explain_zone(drivers: list[Driver], fv: FeatureVector, risk) -> tuple[list[str], list[Reason], str]:
    """(phrases, reasons, sentence) for one zone. Risk-raising reasons if the zone is at risk, else why it is not."""
    from app import calibration

    at_risk = risk.onset is not None or risk.probability >= calibration.alert_threshold()
    reasons = explain_detail(drivers, fv, at_risk)
    phrases = [r.phrase for r in reasons] or ["no strong drivers" if at_risk else "no strong protective factors"]
    return phrases, reasons, explain_text(reasons, at_risk)
