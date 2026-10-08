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
| `status` | `insufficient_data` / `no_episode_expected` / `already_above_normal_high_water` / `episode_expected` | Decides the wording (section 4). `already_above...` means the gauge is already past its usual high-water mark, so "onset" is not a future event |
| `probability_pct` | 0 to 100, from the quantile trajectory | `null` only for `insufficient_data` |
| `severity` | low, moderate, high, severe | Placeholder thresholds, not calibrated (see section 6) |
| `onset`, `peak` | earliest, likely, latest clock times | `latest` can fall on the next day; show the three together as a window |
| `drivers` | up to 3 plain phrases, strongest first | Already words, no numbers |
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

- Forecast quality on the 2020 to 2023 holdout (v2): exceedance within 24 h PR-AUC 0.69 against a 0.12 base rate; onset from below the mark PR-AUC 0.50 against a 0.09 base rate. Good, not certain. Metrics: `GET /api/models/{region_id}/metrics`.
- Labels are gauge high-water episodes, about 18 per gauge-year. Reported real floods (SFBench observations) match them about twice as often as chance.
- 29 of 109 zones have no usable water gauge and must show as insufficient data.
- Severity cut-offs (0.15 and 0.45 stage units) are uncalibrated placeholders.
- No tide or surge input in the shipped model, so coastal events can be under-forecast.
- Ranking counts OSM schools as "potential shelters", which inflates the vulnerable term for large cities (Miami has 242). Treat `rank_reason` as a heuristic until a real shelter list replaces it.
