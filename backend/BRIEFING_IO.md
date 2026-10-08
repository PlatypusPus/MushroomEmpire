# Briefing agent: inputs and outputs

Goal: wrap an LLM around the forecast so the UI shows short, plain, safe text. The LLM only narrates. It never computes,
and every number it writes must exist in its input.

Real data for everything below: `backend/samples/zone_payloads_nicole.json` (Hurricane Nicole, issue time 2022-11-09 12:00,
80 of 109 zones forecast). Code: `app/agents/briefing_io.py` (input builder and number check), `app/agents/briefing.py`
(existing template and `check_numbers`), `app/llm/client.py` (`chat()`, LiteLLM, model from `.env`).

## 1. Pipeline, and where the briefing sits

```
snapshot --ingest--> FeatureVector --forecast--> DepthTrajectory --derive--> RiskOutput
                                        |                              |
                                   drivers (raw)                  explain --> drivers_text (plain words)
exposure (OSM assets) ----------------------------------------------------> ExposureItem[]
all zones: rank --> rank, rank_reason
                         ALL OF THE ABOVE = ZonePayload  ---> briefing_input() ---> LLM ---> grounded() ---> UI
```

## 2. Input

Fetch one `ZonePayload` per zone: `GET /api/zones/{zone_id}?issue_ts=&event_id=` (or all zones from `GET /api/ranking`).
Convert it with `briefing_input(payload, zone_name)`; give the LLM only that dict. Example (Miami, top-ranked zone):

```json
{
  "zone_id": "1245000", "zone_name": "Miami", "status": "already_above_normal_high_water",
  "as_of": "12:00 PM", "horizon_h": 24, "probability_pct": 78, "severity": "high",
  "onset": {"earliest": "1:00 PM", "likely": "1:00 PM", "latest": "12:00 PM"},
  "peak":  {"earliest": "1:00 PM", "likely": "12:00 AM", "latest": "12:00 PM"},
  "drivers": ["high water level now", "high water earlier today", "high water over recent days"],
  "exposure_counts": {"shelter": 242, "hospital": 7, "fire_station": 17, "police": 32},
  "hospitals_named": ["..."],
  "exposure_note": "shelters are only potential (OSM schools and community centres); never call them confirmed shelters",
  "rank": 1, "rank_reason": "High probability, early onset",
  "is_simulated": false, "coverage": "experimental", "model": "lightgbm-quantile-v2",
  "alert_text": "High Water Risk, Miami. Onset 1:00 PM, peak 12:00 AM. Drivers: high water level now + ..."
}
```

| Field | Meaning | Notes for the writer |
|---|---|---|
| `status` | `insufficient_data` / `episode_possible` / `no_episode_expected` / `already_above_normal_high_water` / `episode_expected` | Decides the wording (section 4). `already_above...` means the gauge is already past its usual high-water mark, so "onset" is not a future event. `episode_possible` = no median crossing but probability is at or above the validated alert threshold (0.27): say "a high-water episode is possible", give no onset time |
| `probability_pct` | 0 to 100, from the quantile trajectory | `null` only for `insufficient_data` |
| `severity` | low, moderate, high, severe | Placeholder thresholds, not calibrated (see section 6) |
| `onset`, `peak` | earliest, likely, latest clock times | `latest` can fall on the next day; show the three together as a window |
| `drivers` | up to 3 plain phrases, strongest first | Already words, no numbers |
| `reasons`, `explanation` | `[{phrase, strength}]` with strength `main reason` / `important` / `minor`, and one ready sentence | Value-checked by the Explainability agent (a phrase is only produced if the feature values support it). Prefer these over inventing causes. When the zone is not at risk they explain why it is not ("higher ground", "water well below its usual high-water mark") |
| `exposure_counts`, `hospitals_named` | counts by type; only hospitals are named | Never list the raw asset list |
| `rank`, `rank_reason` | recommended response order and the two top factors | The system recommends only; it never dispatches |
| `is_simulated`, `coverage` | label flags | Must be echoed in the text if `is_simulated` |
| `alert_text` | deterministic template | Use as the fallback and as a style reference |

Times are the SF2Bench wall clock (probably US Eastern standard time, unverified). Print them without a timezone suffix.

## 3. Output (recommended contract for the UI)

```json
{
  "zone_id": "1245000",
  "headline": "High water risk in Miami",
  "summary": "One or two sentences, plain language, under 45 words.",
  "when": "Already above its usual high-water mark; likely to stay high into the night.",
  "why": ["high water level now", "high water earlier today"],
  "who": "7 hospitals and 17 fire stations are in this zone.",
  "caveat": "Experimental forecast. Based on water-level gauges, not observed flooding.",
  "source": "llm" 
}
```

`source` is `"llm"` or `"template"`. If the LLM is down, times out, or fails `grounded()`, return the same shape with
`summary` set to `alert_text` and `source: "template"`; the UI looks identical. For a cross-zone overview, pass the
top N `briefing_input` dicts (sorted by `rank`) and ask for one paragraph plus an ordered list; ground it with the union
of their allowed numbers.

## 4. Writing rules (put these in the system prompt)

1. Use only numbers present in the input. Allowed: probability, clock times, rank, exposure counts, the horizon.
2. Never print stage or water-level values, rain amounts, or depths. Their units are unverified (ROOT_CONTEXT item 10). Say "high", "rising", "heavy".
3. Say "high water" or "water risk", not "flood": labels are stage-exceedance episodes, not observed flooding.
4. `insufficient_data`: write "Insufficient data, risk unknown." Never say low or safe. Never guess.
5. `no_episode_expected`: say no high-water episode is expected in the next 24 h. Do not promise safety.
5b. `episode_possible`: say an episode is possible with the probability; do not give an onset or peak time (there is none).
6. `already_above_normal_high_water`: do not write "onset at 1:00 PM". Say water is already high and give the peak window.
7. Shelters are only potential. Name hospitals, count the rest.
8. If `is_simulated`, say "Simulation" first. Always keep the experimental caveat when `coverage` is `experimental`.
9. Recommend, never order. "Responders may prioritise", not "Dispatch".
10. Return JSON only. No markdown, no emoji.

## 5. Checks before showing anything

```python
from app.agents.briefing_io import briefing_input, grounded
inp = briefing_input(payload, zone_name)
try:
    text = grounded(llm_summary, inp)      # ValueError on any invented number
except (ValueError, LLMUnavailable):
    text = inp["alert_text"]               # deterministic fallback
```

Also reject text containing forbidden words ("flood" outside quoted names, "safe", "guarantee", "dispatch") and any
percentage that differs from `probability_pct`. Tests: `tests/test_briefing_io.py`.

## 6. What the writer should not over-claim (current model facts)

- Forecast quality on the 2020 to 2023 holdout (v2, calibrated on 2015 to 2019): event within 24 h (3 or more hours above the gauge mark) PR-AUC 0.67 against a 0.10 base rate; at the alert threshold 0.27, precision 0.58 and recall 0.68 overall, but only precision 0.46 and recall 0.53 when a gauge starts below its mark (2,383 missed events, 3,154 false alarms in 67,345 gauge-days). Good, not certain. Probabilities are calibrated (ECE 0.013), so "78%" can be read as about 78 in 100 similar situations, with S_7 slightly less frequent than predicted. Timing: for events caught, the likely onset is off by a median 0 h (mean absolute 2.6 h, 90% within 10 h); the likely peak is off by a mean absolute 6.8 h (90% within 15 h), so treat the peak time as rough. The stated time windows are about 23 h wide and almost always contain the truth, which makes them weak; say "later today" rather than a precise hour for the peak. Metrics: `GET /api/models/{region_id}/metrics`.
- Labels are gauge high-water episodes, about 18 per gauge-year. Reported real floods (SFBench observations) match them about twice as often as chance.
- 29 of 109 zones have no usable water gauge and must show as insufficient data.
- Severity is now fitted on the validation years but weak: exact class match is high only because most cases are "low"; for real events moderate is right 20% of the time, high 28%, severe 40% (recall 20%, 36%, 57%), though 97% of cases are within one class. Prefer wording like "higher than usual" over a hard severity word.
- No tide or surge input in the shipped model, so coastal events can be under-forecast.
- Ranking counts OSM schools as "potential shelters", which inflates the vulnerable term for large cities (Miami has 242). Treat `rank_reason` as a heuristic until a real shelter list replaces it.
