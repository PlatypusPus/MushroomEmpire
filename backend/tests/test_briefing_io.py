import json
from pathlib import Path

import pytest

from app.agents.briefing_io import briefing_input, briefing_prompt, grounded, grounded_prompt, prompt_allowed_numbers
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


def test_prompt_is_minimal_and_status_conditioned():
    p = inp(top)
    q = briefing_prompt(ZonePayload(**top["zone_payload"]), top["zone_name"])
    # one causal field, no triple telling; fallback text and rank boilerplate stay server-side
    assert "reasons" in q and "drivers" not in q and "explanation" not in q
    assert "alert_text" not in q and "rank" not in q and "timing_reliability" not in q
    assert "model" not in q and "as_of" not in q and "horizon_h" not in q
    assert len(json.dumps(q)) < len(json.dumps(p))  # strictly smaller than the full facts
    # no-episode prompts carry no times the rules forbid
    from datetime import datetime, timezone
    no = dict(top["zone_payload"], probability=0.05, severity="low", onset=None, peak=None)
    qn = briefing_prompt(ZonePayload(**no), top["zone_name"])
    assert qn["status"] == "no_episode_expected" and "onset" not in qn and "peak" not in qn


def test_prompt_grounds_expected_output_and_blocks_forbidden_times():
    q = briefing_prompt(ZonePayload(**top["zone_payload"]), top["zone_name"])
    # the fallback template is grounded by the full facts (its own path), not by the trimmed prompt
    assert grounded(inp(top)["alert_text"], inp(top)) == inp(top)["alert_text"]
    # a well-formed LLM-style sentence using only prompt numbers passes ...
    good = f"High water in {q['zone_name']}, {q['probability_pct']}% chance, peaking around {q['peak']}."
    assert grounded_prompt(good, q) == good
    # ... while an onset time the rules forbid is not even in the allowlist, so it falls back
    with pytest.raises(ValueError):
        grounded_prompt(f"{q['zone_name']} onset {inp(top)['onset']['likely']}.", q)
    with pytest.raises(ValueError):
        grounded_prompt(f"{top['zone_name']} will see 3.5 feet of water.", q)
