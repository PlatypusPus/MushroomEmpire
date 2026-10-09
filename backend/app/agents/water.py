"""Water agent: where flood water may spread. An indicator from the map and ground height, not a hydraulic model.

Spread: places whose boundaries touch (within ~200 m) a place forecast to flood may get its water, more likely when they sit
lower (HAND, height above the nearest drainage). Score = the flooding neighbour's chance, halved when this place sits higher.
For the maps, each flooding place also gets a "spill zone": its outline grown by up to ~1.5 km with severity.
"""

from shapely.geometry import mapping, shape
from shapely.strtree import STRtree

from app.schemas import ZonePayload
from app.store import Snapshot

TOUCH_DEG = 0.002  # ~200 m: Census places often leave thin gaps between neighbours
SPILL_DEG = {"moderate": 0.004, "high": 0.009, "severe": 0.014}  # how far the spill zone reaches (~0.4, 1, 1.5 km)
FLOODING = ("high", "severe")
HIGHER_BY_M = 0.3  # a neighbour this much higher (HAND) gets half the score


_nb: dict = {}


def neighbours(snap: Snapshot) -> dict[str, list[str]]:
    """Touching places, computed once per event snapshot (zones never change within one)."""
    key = snap.event["id"]
    if key in _nb:
        return _nb[key]
    ids = [z["id"] for z in snap.zones]
    geoms = [shape(z["geometry"]) for z in snap.zones]
    tree = STRtree(geoms)
    out: dict[str, list[str]] = {}
    for i, g in enumerate(geoms):
        near = tree.query(g.buffer(TOUCH_DEG), predicate="intersects")
        out[ids[i]] = [ids[j] for j in near if j != i]
    _nb[key] = out
    return out


def spread(snap: Snapshot, payloads: list[ZonePayload]) -> dict:
    """Which places may get water from a flooding neighbour, plus spill-zone shapes for the map."""
    by = {p.zone_id: p for p in payloads}
    hand = {z["id"]: z.get("hand_m") for z in snap.zones}
    nb = neighbours(snap)
    affected = {}
    for zid, ns in nb.items():
        src = [n for n in ns if by.get(n) and by[n].severity in FLOODING and by[n].probability is not None]
        if not src:
            continue
        def score(n):
            higher = hand.get(zid) is not None and hand.get(n) is not None and hand[zid] > hand[n] + HIGHER_BY_M
            return by[n].probability * (0.5 if higher else 1.0)
        src.sort(key=score, reverse=True)
        affected[zid] = {"score": round(score(src[0]), 2), "from": src[:3],
                         "lower": not (hand.get(zid) is not None and hand.get(src[0]) is not None and hand[zid] > hand[src[0]] + HIGHER_BY_M)}
    feats = []
    for z in snap.zones:
        p = by.get(z["id"])
        if p and p.severity in SPILL_DEG and p.probability is not None:
            g = shape(z["geometry"])
            ring = g.buffer(SPILL_DEG[p.severity]).difference(g)
            feats.append({"type": "Feature", "geometry": mapping(ring.simplify(0.0005)),
                          "properties": {"zone_id": z["id"], "severity": p.severity, "probability": p.probability}})
    return {"affected": affected, "spill_geo": {"type": "FeatureCollection", "features": feats}}
