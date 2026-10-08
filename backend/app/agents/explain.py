"""Explainability agent: model contributions -> fixed plain-language phrases. No numbers."""

from app.schemas import Driver

PHRASES = {
    "level_m": "high water level now",
    "level_trend": "water rising fast",
    "rain_6h": "heavy recent rain",
    "rain_24h": "heavy recent rain",
    "rain_72h": "several days of rain",
    "hand_m": "low height above drainage",
    "elevation_m": "low elevation",
    "level_change_6h": "water rising fast",
    "level_change_24h": "water rising over the day",
    "level_max_24h": "high water earlier today",
    "level_max_72h": "high water over recent days",
    "level_std_24h": "unsettled water levels",
    "tide_m": "high tide",
    "gate": "flood gate operations",
    "pump": "pump operations",
}


def explain(drivers: list[Driver], top: int = 3) -> list[str]:
    out = []
    for d in sorted(drivers, key=lambda d: d.contribution, reverse=True):
        phrase = PHRASES.get(d.feature, d.feature.replace("_", " "))
        if d.contribution > 0 and phrase not in out:
            out.append(phrase)
    return out[:top] or ["no strong drivers"]
