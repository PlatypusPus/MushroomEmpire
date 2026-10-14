# SHROOMCAST

**Coastal flood intelligence for South Florida.** Winner of the **Coastal Intelligence Track** at the **Singularity Hackathon 2026**.

SHROOMCAST forecasts flood risk for 109 South Florida places up to 24 hours ahead. It explains each forecast, ranks where to respond first, and alerts the people who follow a place.

## What it does

- **Forecasts flood risk.** LightGBM quantile models give low, likely and high water levels at 1 to 24 hours ahead. A calibrated probability turns them into low, moderate, high and severe risk.
- **Explains each forecast.** SHAP shows what drives a place's risk (rain, tide, surge, ground water), and an AI briefing puts it into plain words.
- **Ranks the response.** A priority queue weighs risk against the people, hospitals, shelters, roads and buildings in each place. Sliders adjust the weights.
- **Advises what to do.** Steps for each place, with nearby shelters and who to contact.
- **Replays past storms.** Steps through 8 historical South Florida flood events using only the data available at each moment.
- **Goes live.** USGS gauges, NOAA tides, Open-Meteo rain, and NWS and NHC warnings, with predictions across the whole US. The live model retrains daily on new gauge data and keeps a new version only if it beats the current one.
- **Sends alerts.** Users sign in with Google, follow places, and get email or WhatsApp alerts.

## What's in it

- **Dashboard:** risk map with live and storm replay modes, a time slider, and a "water may spread" layer.
- **Response priority, Alerts and Live hazards pages.**
- **Assistant:** a chat that answers questions about the current forecast.
- **Model validation:** how well the forecasts held up on past storms.
- **Tutorials and a first-visit tour.**
- **API & MCP:** a REST API with interactive docs, and an MCP server with 8 tools for AI agents.

## Built with

| Part | Stack |
|---|---|
| Backend | FastAPI, LangGraph, LightGBM, SHAP, PostgreSQL |
| AI | LiteLLM, which runs Ollama locally or a hosted model such as Gemini |
| Frontend | React, Vite, Tailwind, Leaflet, React Query, Zustand |
| WhatsApp | Baileys bridge (Node) |

## Run it

```bash
# backend: copy backend/.env.example to backend/.env and fill it in
cd backend && uv sync && uv run alembic upgrade head
uv run python -m scripts.precache        # optional: makes storm replays instant
uv run uvicorn app.main:app --port 8000

# frontend
cd frontend && npm install && npm run dev

# WhatsApp bridge (optional)
cd whatsapp-bridge && npm install && npm start
```

Forecasts are indicative and support decisions only. They don't replace official warnings.
