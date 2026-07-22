# Production Planning & Schedule Optimization Agent

An enterprise-grade agent that generates **deterministic** production schedules for a
manufacturing plant using **Google OR-Tools (CP-SAT)** and **business rules** — with an
Azure OpenAI assistant used **only** to explain results and answer planner questions.

> **Core principle:** scheduling decisions are 100% deterministic (Constraint Programming +
> Business Rules). No Machine Learning is used for scheduling, and the LLM never makes
> scheduling decisions.

---

## Status

| Phase | Scope | State |
|-------|-------|-------|
| **Phase 1** | Project foundation (this delivery) | ✅ Complete |
| Phase 2+ | Domain models, simulator, ingestion, optimization, analytics, risk, recommendation, scenario, explanation, chat, frontend | ⏳ Pending approval |

Phase 1 delivers the runnable application skeleton only — **no business logic**.

---

## Architecture (summary)

Deterministic pipeline (built out over later phases):

```
Data Source (CSV simulator → future ERP/MES)
  → Ingestion & Validation
  → Business Rules
  → OR-Tools CP-SAT Optimization
  → Analytics (KPIs)
  → Risk Detection
  → Recommendation
  → Scenario Planning
  → Explanation Context Builder
  → Azure OpenAI (explain-only)
```

The optimization core is isolated behind a ports-and-adapters seam so the daily simulator
can be replaced by live ERP/MES integrations without changing any downstream logic.

---

## Project structure (backend, Phase 1)

```
backend/
├── app/
│   ├── main.py              # FastAPI application factory & entrypoint
│   ├── config.py            # Pydantic settings (env-driven, PPO_ prefix)
│   ├── api/
│   │   └── v1/              # Versioned API surface
│   │       ├── routes_health.py
│   │       └── schemas.py
│   ├── core/
│   │   ├── logging.py       # Console / JSON logging config
│   │   ├── exceptions.py    # Application exception hierarchy
│   │   └── error_handlers.py# Global error envelope
│   ├── utils/               # Shared helpers (datetime, filesystem)
│   ├── domain/              # (later) canonical models + deterministic core
│   ├── ingestion/           # (later) CSV/ERP data-source adapters
│   ├── rules/               # (later) business rules engine
│   ├── optimization/        # (later) OR-Tools CP-SAT
│   ├── analytics/           # (later) KPIs
│   ├── risk/                # (later) risk detection
│   ├── recommendation/      # (later) recommendations
│   ├── scenario/            # (later) scenario planning
│   ├── explanation/         # (later) LLM context builder
│   ├── chat/                # (later) Azure OpenAI (explain-only)
│   └── services/            # (later) orchestration
├── simulator/               # (later) stateful daily factory simulator
├── datasets/                # generated daily snapshots (git-ignored)
├── outputs/                 # generated results (git-ignored)
├── tests/                   # test suite
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── .env.example
```

---

## Getting started (local)

### Prerequisites
- Python 3.12+

### Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Run the API

```powershell
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Readiness: http://localhost:8000/api/v1/ready

### Run tests

```powershell
cd backend
pytest
```

---

## Run with Docker

```powershell
docker compose up --build
```

The service exposes port `8000` and includes a container health check on
`/api/v1/health`. Generated `datasets/` and `outputs/` are mounted as volumes.

---

## Configuration

All settings are environment-driven with the `PPO_` prefix and can be placed in
`backend/.env` (see `.env.example`). Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PPO_ENVIRONMENT` | `development` | Deployment environment |
| `PPO_LOG_LEVEL` | `INFO` | Log verbosity |
| `PPO_LOG_JSON` | `false` | Structured JSON logs |
| `PPO_CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins |
| `PPO_SOLVER_MAX_TIME_SECONDS` | `30` | CP-SAT time limit (later phases) |
| `PPO_AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI (later phases) |

---

## License

Proprietary — internal manufacturing use.
