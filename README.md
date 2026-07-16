# Production Planning & Schedule Optimization Agent

A multi-agent, action-taking assistant for a beverage manufacturing plant. It analyses
capacity, detects bottlenecks, predicts delay & downtime risk, forecasts demand, optimises the
production schedule, and — with your confirmation — takes real actions (email alerts, material
re-orders, chart & plan exports).

- **Orchestration:** Microsoft Agent Framework (MAF) — orchestrator + 3 specialist agents
- **LLM:** Azure OpenAI `gpt-4o` (optional; a deterministic router answers without a key)
- **Everything else is open source:** FastAPI, scikit-learn, Google OR-Tools, SQLite, React

## Architecture (layers)
```
React (chat · dashboards · action approvals)
        |  REST + WebSocket
FastAPI  ->  Answer service (semantic cache + intent router)
        |
MAF Orchestrator ── Capacity&Scheduling · Risk&Reliability · Demand&Inventory specialists
        |
Intelligence: OR-Tools scheduler · 3 ML models · analytics · ML->language explainer
        |
Data: clean star-schema CSVs   +   Actions: email / reorder / chart / export
```

## What each feature uses
| Feature | Technique |
|---|---|
| Capacity analysis, bottleneck, prioritization, allocation | direct calculation / rules |
| Schedule optimization (3 scenarios) | OR-Tools CP-SAT |
| Delay-risk identification | ML classifier (macro-F1 ≈ 0.76) |
| Machine downtime risk | ML classifier (F1 ≈ 0.90) |
| Demand vs capacity | ML regressor (MAPE ≈ 14% vs 22% baseline) |
## Quick start (fresh clone)

**Prerequisites:** Python 3.11+ and Node.js 20+.

The dataset CSVs are committed, but the ML models are **not** (they're build artifacts).
You train them **once** — after that the server starts instantly on every run.

```bash
# 1. Backend deps
cd backend
pip install -r requirements.txt

# 2. One-time setup: trains all models if missing (idempotent, ~2-3 min).
#    Data is regenerated only if it's missing.
python -m app.setup

# 3. Run the backend
python -m uvicorn app.main:app --port 8000
```

> You do **not** retrain on every run. `python -m app.setup` is a one-time step; the models
> persist in `backend/models/`. If you skip step 2, the server auto-trains on first startup
> (set `AUTO_SETUP=0` in `.env` to disable that). `python -m app.setup --force` retrains from scratch.

```bash
# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api and /ws to :8000)
```

Key endpoints: `GET /api/status`, `POST /api/chat`, `WS /ws/chat`,
`GET /api/capacity|bottlenecks|schedule|risk/delay|risk/downtime|risk/orders|demand|demand/stockout|demand/regions`,
`POST /api/actions/execute`.

## Deploy with Docker (models baked into the image)
```bash
# build context = this folder
docker build -t production-planner .
docker run -p 8000:8000 \
  -e AZURE_OPENAI_API_KEY=your-key \
  -e AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/ \
  production-planner
```
Models are trained at **build time**, so the container starts instantly. Secrets are passed at
runtime (never baked in). For the frontend, run `npm run build` and serve `frontend/dist/` from
any static host (point it at the backend URL).

## Regenerate data / retrain (optional)
```bash
cd backend
python data/generate_dataset.py     # regenerate the star-schema CSVs
python data/validate_dataset.py     # integrity check (must PASS)
python -m app.ml.train              # retrain all models
# or simply:  python -m app.setup --force
```

## Tests
```bash
cd backend
python -m pytest -q
```

## Configuration
Copy `.env.example` to `.env` (in this folder) and fill in Azure OpenAI + SMTP if desired.
Without an Azure key the system still works (deterministic router). Without SMTP the email
action runs in simulation mode (writes to a local outbox). Secrets are read from the
environment and never committed or logged.

## Actions (human-in-the-loop)
The agent proposes actions; you confirm them in the UI. Each maps to
`POST /api/actions/execute` with an allow-listed `id`:
`send_email`, `place_reorder`, `generate_chart`, `export_plan`.

## Data model
See [backend/data/schema.md](backend/data/schema.md). One coherent star schema
(dimensions + facts, ≥500 rows per fact, consistent keys, `DD-MM-YYYY`, UTF-8).
