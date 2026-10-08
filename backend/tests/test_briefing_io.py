import json
from pathlib import Path

import pytest

from app.agents.briefing_io import briefing_input, grounded
from app.schemas import ZonePayload

S = json.loads((Path(__file__).resolve().parents[1] / "samples" / "zone_payloads_nicole.json").read_text())
top = S["example_top_zone"]
by = S["by_status"]


def inp(example):
    return briefing_input(ZonePayload(**example["zone_payload"]), example["zone_name"])


def test_status_is_explicit():
    for status, example in by.items():  # every sample must map to the status it was filed under
        assert inp(example)["status"] == status
    assert {"insufficient_data", "no_episode_expected"} <= set(by)
    assert inp(by["insufficient_data"])["probability_pct"] is None  # unknown is never shown as low


def test_nothing_the_llm_must_not_print_is_passed():
    i = inp(top)
    assert not {"level_m", "peak_level_m", "rain_6h", "geometry"} & set(i)
    assert i["exposure_counts"]["shelter"] > 100 and len(i["hospitals_named"]) <= 3  # counts, not a 240-item list


def test_grounded_accepts_template_and_rejects_invented_numbers():
    i = inp(top)
    assert grounded(i["alert_text"], i) == i["alert_text"]
    assert grounded(f"{i['zone_name']} is at {i['probability_pct']} percent.", i)
    with pytest.raises(ValueError):
        grounded(f"{i['zone_name']} will see 3.5 feet of water.", i)


def test_timing_reliability_is_stated():
    assert inp(top)["timing_reliability"] == {"peak": "moderate", "onset": "rough"}
