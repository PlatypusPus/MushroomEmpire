import re
from datetime import datetime, timezone

from app.agents.explain import explain, explain_detail, explain_text
from app.schemas import Driver, FeatureVector


def fv(**kw):
    base = dict(zone_id="Z", issue_ts=datetime(2022, 11, 9, tzinfo=timezone.utc), level_m=0.5, level_trend_m_per_h=0.1, rain_6h=0.0, rain_24h=0.0,
                rain_72h=0.0, hand_m=1.0, elevation_m=3.0, is_simulated=False, level_change_6h=0.4, level_change_24h=0.3, level_max_24h=0.6,
                level_max_72h=0.6, level_std_24h=0.2)
    return FeatureVector(**{**base, **kw})


def drv(**c):
    return [Driver(feature=k, contribution=v) for k, v in c.items()]


def test_three_level_features_become_one_reason():
    r = explain_detail(drv(level_m=0.9, level_max_24h=0.1, level_max_72h=0.07), fv())
    assert [x.theme for x in r] == ["level"] and r[0].strength == "main reason"
    assert r[0].phrase == "water is already above its usual high mark"


def test_level_phrase_follows_the_values():
    below = fv(level_m=-0.2, level_max_24h=0.3)
    assert explain_detail(drv(level_m=0.5), below)[0].phrase == "water was above its usual high mark earlier today"
    assert explain_detail(drv(level_m=0.5), fv(level_m=-0.2, level_max_24h=-0.1, level_max_72h=0.2))[0].phrase.endswith("in recent days")
    assert explain_detail(drv(level_m=0.5), fv(level_m=-0.2, level_max_24h=-0.1, level_max_72h=-0.1))[0].phrase == "water is close to its usual high mark"
    assert explain_detail(drv(level_m=0.5), fv(level_m=-1.2, level_max_24h=-1.1, level_max_72h=-1.0)) == []  # far below the mark: no false "close to"


def test_never_claims_rising_for_a_falling_gauge():
    falling = fv(level_trend_m_per_h=-0.1, level_change_6h=-0.5, level_change_24h=-0.2)
    assert explain_detail(drv(level_trend=0.2, level_change_6h=0.3), falling) == []


def test_rain_is_only_ever_recent_and_only_if_it_rained():
    assert explain_detail(drv(rain_24h=0.4), fv(rain_24h=0.0)) == []
    r = explain_detail(drv(rain_24h=0.4), fv(rain_24h=2.0))
    assert r[0].phrase == "recent rain" and "heavy" not in r[0].phrase


def test_small_themes_are_dropped_and_strength_is_in_words():
    r = explain_detail(drv(level_m=1.0, elevation_m=0.3, level_change_6h=0.02), fv(elevation_m=1.0))
    assert [x.theme for x in r] == ["level", "terrain"] and r[1].strength == "standing factor"  # terrain is always last


def test_not_at_risk_explains_why_not():
    calm = fv(level_m=-1.0, level_trend_m_per_h=-0.01, level_change_6h=-0.05)
    r = explain_detail(drv(level_m=-0.8, elevation_m=-0.1), calm, at_risk=False)
    assert r[0].phrase == "water is well below its usual high mark"
    assert explain_text(r, at_risk=False).startswith("Main reason for the low risk")


def test_no_numbers_anywhere_and_legacy_call_still_works():
    r = explain_detail(drv(level_m=0.5, level_trend=0.2, rain_72h=0.1, hand_m=0.2, elevation_m=0.2, level_std_24h=0.1), fv(rain_72h=3.0), top=6)
    assert not re.search(r"\d", " ".join(x.phrase for x in r) + explain_text(r, True))
    assert explain(drv(level_m=0.5, elevation_m=0.2)) == ["water level is high now", "low elevation"]  # no fv: old behaviour


def test_terrain_phrases_are_checked_against_the_ground():
    assert explain_detail(drv(elevation_m=0.4), fv(elevation_m=2.0, hand_m=0.5))[0].phrase == "low-lying ground"
    assert explain_detail(drv(elevation_m=0.4), fv(elevation_m=6.0, hand_m=2.0)) == []  # high ground cannot be a reason for HIGH risk
    assert explain_detail(drv(elevation_m=-0.4), fv(elevation_m=6.0), at_risk=False)[0].phrase == "higher ground"
    assert explain_detail(drv(elevation_m=-0.4), fv(elevation_m=1.0, hand_m=0.2), at_risk=False) == []  # low ground is not protective


def test_terrain_is_a_standing_factor_never_the_why_now():
    low = fv(elevation_m=1.0, hand_m=0.3)
    r = explain_detail(drv(elevation_m=0.5, level_m=0.2), low)
    assert r[0].theme == "level" and r[-1].strength == "standing factor"
    only_ground = explain_detail(drv(elevation_m=0.5), low)
    assert explain_text(only_ground, True).startswith("Nothing unusual in recent water levels")
    assert "Standing factor: low-lying ground" in explain_text(r, True)
    assert explain_text(only_ground, True) == "Nothing unusual in recent water levels. The zone has low-lying ground, which raises its risk."
    assert explain_text(explain_detail(drv(elevation_m=-0.5), fv(elevation_m=6.0), at_risk=False), False) == "Nothing unusual in recent water levels. The zone sits on higher ground."
