# Production Planning & Schedule Optimization Agent

An end-to-end demo: **FastAPI + Microsoft Agent Framework (Azure OpenAI)** backend and a
**React + Vite + Recharts** dashboard. Feature 1 of 9 is fully working: **Capacity Analysis**
(with basic bottleneck detection). The rest are scaffolded and shown on the roadmap.

The golden rule: the deterministic engine computes every number; the AI copilot only
explains it in plain language. It never invents figures.

```
app/
  backend/    FastAPI API, capacity engine, MAF agent, step-by-step logging
  frontend/   React dashboard with live charts and the copilot panel
```

## 1. Run the backend

```powershell
cd app/backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # or just: fastapi uvicorn[standard] pydantic python-dotenv
.\.venv\Scripts\python.exe -m uvicorn main:app --port 8001 --reload
```

- API docs: http://localhost:8001/docs
- Logs stream to the console and to `app/backend/logs/app.log` (every step is logged).

### Enable the Azure OpenAI copilot (optional)
The app works without a key (it falls back to a deterministic summary). To turn on the LLM:

```powershell
cd app/backend
copy .env.example .env       # then edit .env with your Azure OpenAI details
.\.venv\Scripts\python.exe -m pip install agent-framework
```

`.env` needs: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`.

## 2. Run the frontend

```powershell
cd app/frontend
npm install
npm run dev -- --port 5199
```

Open http://localhost:5199. If the backend runs on a different port than 8001,
update the `BASE` constant in `src/api.js`.

## 3. What you will see
- **At a glance**: bottleneck, overloaded machines, orders considered, status.
- **Capacity dashboard**: two live charts (hours needed vs available; how busy each machine is).
- **Roadmap & copilot**: which features are live vs planned, and a chat box that answers
  questions using real engine numbers.

## API quick reference
| Endpoint | What it does |
|---|---|
| `GET /api/health` | health check |
| `GET /api/dataset/summary` | row counts per table + the weeks in the order book |
| `GET /api/capacity/overview` | BULK: bottleneck utilisation for every week in one pass |
| `GET /api/capacity/heatmap` | work-centre x week utilisation grid |
| `GET /api/capacity?week=YYYY-MM-DD` | capacity for one week (defaults to the busiest) |
| `GET /api/priority?week=YYYY-MM-DD` | order prioritization (EDD + critical ratio + tier/penalty) |
| `GET /api/allocate?week=YYYY-MM-DD` | resource allocation: offload overloaded machines (before/after) |
| `GET /api/schedule?week=YYYY-MM-DD&n=12` | schedule optimization (OR-Tools CP-SAT) - Gantt for top-N orders |
| `GET /api/risk?week=YYYY-MM-DD` | delay risk: material (BOM vs inventory) + capacity, with fixes |
| `GET /api/demand` | demand vs capacity across the horizon: can we commit to the order book? |
| `GET /api/scenarios?week=YYYY-MM-DD` | what-if scenarios: baseline vs add-a-shift vs defer orders |
| `GET /api/features` | roadmap (live vs planned) |
| `POST /api/agent/ask` | ask the planning copilot |

## Dataset (backend/data)
A connected, relational valve-manufacturing dataset (deterministic, seeded):

| Table | Rows | Linked by |
|---|---|---|
| work_centers | 9 | work_center_id |
| items | 45 | item_id |
| routings | 270 | item_id, work_center_id |
| components | 45 | component_id |
| bom | 330 | item_id, component_id |
| inventory | 45 | component_id |
| customers | 30 | customer_id |
| orders | 520 | item_id, customer_id |

Regenerate any time with:

```powershell
cd app/backend/data
..\.venv\Scripts\python.exe generate_dataset.py
```
