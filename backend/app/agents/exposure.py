"""Exposure agent: assets lane A already joined to zones (OSM via Overpass)."""

from app.schemas import ExposureItem

STATUS = {"confirmed": "confirmed", "potential": "potentially_exposed"}


def exposure(zone_id: str, assets: list[dict]) -> list[ExposureItem]:
    return [
        ExposureItem(type=a["kind"], name=a["name"], status=STATUS[a["confidence"]])
        for a in assets
        if a["zone_id"] == zone_id
    ]
