# Orchestration: how the agents connect

One tick (one issue time, every zone) is a single LangGraph workflow in `app/pipeline.py`. Replay, the REST API and the tests all
call it (`orchestrator.run_tick`), so there is one code path. `tests/reference_tick.py` keeps the old plain loop, and
`tests/test_pipeline.py` proves the graph returns identical payloads (it also did on 14 real ticks of 109 zones before the switch).

## Tick graph (zones fan out in parallel, then rank across zones)

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	zone(zone)
	rank(rank)
	assemble(assemble)
	__end__([<p>__end__</p>]):::last
	__start__ -.-> zone;
	rank --> assemble;
	zone --> rank;
	assemble --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Zone subgraph (the agent chain, one zone)

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	ingest(ingest)
	forecast(forecast)
	derive(derive)
	explain(explain)
	exposure(exposure)
	__end__([<p>__end__</p>]):::last
	__start__ --> ingest;
	derive --> explain;
	derive --> exposure;
	forecast --> derive;
	ingest -.-> exposure;
	ingest -.-> forecast;
	explain --> __end__;
	exposure --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

* **ingestion** -> FeatureVector (only rows with `availability_ts <= issue_ts`). No usable gauge: the zone stops here and is reported as
  *insufficient data*, never low risk.
* **forecasting** -> DepthTrajectory (LightGBM quantiles, persistence fallback).
* **risk+peak** -> RiskOutput: probability, severity, onset from the trajectory, peak window replaced by the dedicated peak model.
* **explainability** and **exposure** run in parallel after risk.
* **rank** (cross-zone weighted sum) and **assemble** (alert text, `ZonePayload`) need every zone, so they come after the fan-in.

## Guarantees

| Property | How |
|---|---|
| Deterministic | zone results arrive in any order and are re-sorted into snapshot order before ranking |
| Failure isolation | an agent exception turns that zone into *insufficient data* (`rank_reason` says the forecast failed) and is listed in `TickResult.errors`; the tick completes |
| Observable | every node is a named LangChain `Runnable`; `trace` holds per-agent milliseconds; `GET /api/pipeline` returns the summary and this diagram |
| Streamable | `astream_tick` yields `zone` events as zones finish, then `ranked`, then `done`; `GET /api/tick/stream` is the SSE form |
| Bounded parallelism | `MAX_PARALLEL_ZONES = 4` (work is CPU-bound; more threads only add contention) |

## Cost (event 5, 109 zones, 80 forecast, laptop CPU): about 1.2 to 1.5 s per tick

Mean per call: forecasting 102 ms, risk+peak 133 ms, ingestion 1.1 ms, exposure 0.2 ms, explainability 0.04 ms (timings include thread
waits). Ticks are memoised by the replay engine, so scrubbing re-reads. Batching the LightGBM predictions across zones would be the
next speed-up if live ticks need to be faster.

## Grounded assistant (`app/assistant.py`, `POST /api/assistant`)

A LangChain (LCEL) chain that connects questions to the agents' outputs: `RunnablePassthrough.assign(route) | assign(facts via RunnableBranch) | compose`.

```mermaid
graph LR
  Q[question + selected zone] --> R[route: rules, no LLM]
  R -->|zone / why| Z[briefing_input of the zone]
  R -->|exposure| E[exposure counts + hospitals]
  R -->|top| T[ranked zones]
  R -->|model| M[stored validation facts]
  R -->|help| H[fixed help text]
  Z --> C[compose: local LLM phrases the facts]
  E --> C
  T --> C
  M --> C
  C --> G{guard: numbers in facts, no forbidden words, no contradiction}
  G -->|pass| A[LLM answer]
  G -->|fail or LLM down| X[deterministic template from the same facts]
```

* The model sees only the small `facts` JSON, never raw data, and may not compute. Every number in its text must occur in the facts.
* An insufficient-data zone never reaches the model (it could call it low risk); a ranking answer that calls an unknown zone "low risk" is rejected.
* `source` is `llm` or `template`; `reason` says why a draft was rejected. Intent routing is rule-based because a 3B model routes unreliably.
* Tested with a fake model (routing, grounded accept, invented-number / forbidden-word / contradiction fallback, LLM down, endpoint). Not yet run against a live Ollama model.
