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

## Prerequisites
- Python 3.11+ and Node.js 20+
- Install backend deps: `cd backend && pip install -r requirements.txt`

## 1. Data (already generated in `backend/data/star/`)
```bash
python backend/data/generate_dataset.py   # regenerate
python backend/data/validate_dataset.py   # integrity check (must PASS)
```

## 2. Train the ML models (already trained in `backend/models/`)
```bash
cd backend
pip install -r requirements.txt
python -m app.ml.train
```

## 3. Run the backend
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```
Key endpoints: `GET /api/status`, `POST /api/chat`, `WS /ws/chat`,
`GET /api/capacity|bottlenecks|schedule|risk/delay|risk/downtime|demand`,
`POST /api/actions/execute`.

## 4. Run the frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api and /ws to :8000)
```

## 5. Tests
```bash
cd backend
python -m pytest -q
```

## Configuration
Copy `.env.example` to `.env` (repo root) and fill in Azure OpenAI + SMTP if desired.
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
