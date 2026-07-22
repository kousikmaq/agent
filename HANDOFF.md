# Handoff — Production Planning & Schedule Optimization Agent

_Last updated: 2026-07-21_

## 1. What this is

A deterministic **production planning & schedule optimization** app for a discrete-manufacturing factory. For a given business date it decides *which operation runs on which machine, with which worker, at what time*, then analyzes the plan for KPIs, risks, recommendations, cost, and what-if scenarios.

- **No AI/ML in planning.** The optimizer is Google **OR-Tools CP-SAT** (constraint solver). Same inputs → same plan.
- The only "AI" is an optional **explain-only** chat assistant.

## 2. Architecture / stack

- **Backend** — Python + FastAPI, routes under `/api/v1`. OR-Tools CP-SAT scheduler. Pydantic models. Located in `backend/`.
- **Frontend** — React 18 + TypeScript + Vite. `frontend/`, dev server `localhost:5173`, proxies `/api` → `localhost:8000`.
- **Data** — CSV factory snapshots per day in `backend/datasets/<date>/`. Planning outputs persisted in `backend/outputs/<date>/`.

### Pipeline (per Run Planner)
`load data → business rules/policy → CP-SAT solve → analytics (KPIs + cost) → risk detection → recommendations → scenario planning (4 what-ifs) → explanation context → persist`

## 3. How to run

Backend (run WITHOUT `--reload` for stability during demos):
```powershell
Set-Location "<repo>\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Frontend:
```powershell
Set-Location "<repo>\frontend"
npm run dev
```
Health check: `Invoke-RestMethod http://localhost:8000/api/v1/data/dates`

### Checks
- Frontend typecheck: `cd frontend; npx tsc --noEmit` (clean).
- Backend tests: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_optimization.py tests/test_monitoring.py -q` (15 pass).

### Operational notes
- Each **Run Planner / Generate Next Day / Apply scenario** triggers heavy CP-SAT solves (main solve + 4 scenario solves, ~6–30 s each). The single-worker server is **busy/unresponsive during a solve** — this is expected, not a crash. Click once and wait for the status bar.
- Data date/clock is 2026-07-21; snapshots exist 2026-07-17 → 2026-07-31. Current week = Mon 2026-07-20 → Sat 2026-07-25.

## 4. Features added this cycle

### Frontend
- **Weekly Plan** tab — Mon–Sat per-day target workload; Saturday "update the plan" cadence banner.
- **Daily Progress** tab — planned vs actual per day, capped at today; on-track banner.
- **Generate Next Day** — builds tomorrow as a **forward "plan-only" view**; hides risk/delivery/drift/progress/recommendation tabs and trims Overview to plan cards (can't assess a day not yet worked).
- Date selector capped at today.
- **Scenarios** — rows are **clickable** to expand each plan's *approach* + full KPI breakdown + **cost breakdown** vs baseline; baseline auto-expands; **"Use this plan as the current plan"** applies/commits a scenario.
- **Recommendations** — duplicate proposals **grouped** (collapsible with count) to remove redundancy; **Approve / Dismiss** controls; "Hide dismissed" toggle.
- **Cost / money** — "Est. Plan Cost" KPI card + per-scenario cost breakdown (labor regular/overtime, machine, tardiness penalty).
- **Assistant** moved to a right **side dock** with clickable suggested questions.
- **Skeleton loading** across the dashboard.
- Removed **MAF** UI (Guide the MAF run, Run via MAF, Workflow tab).
- Fixed invisible Weekly "Target Workload" bars (color contrast).
- **Shop Floor** page left unchanged intentionally.

### Backend / optimizer (CP-SAT)
- **On-time objective strengthened** — explicit per-late-order penalty (weighted by priority) so the solver maximizes the *count* of on-time orders, not just minutes late. Config `late_order_weight` (default 1440).
- **Batch processing (parallel-batch machines)** — PAINTING + QC machines process up to **3** operations simultaneously per batch cycle (`AddCumulative`). Regular stations keep one-at-a-time no-overlap; maintenance fully blocks a batch machine. Config: `enable_batching` (default True), `batch_work_centers` (PAINTING, QC), `batch_capacity` (3), `batch_same_family_only` (default **False** — see notes).
- **Apply-scenario endpoint** — `POST /api/v1/scenarios/{date}/apply` re-solves with the scenario transform and persists it as the committed plan.
- **Cost estimator** — `backend/app/analytics/cost.py`, merged into KPI `metrics` and scenario KPIs.

## 5. Key files touched

Backend:
- `app/optimization/objectives.py` — on-time + tardiness + makespan objective.
- `app/optimization/constraints/due_dates.py` — `is_late` reified flag.
- `app/optimization/constraints/machine_capacity.py` — batch vs no-overlap capacity logic.
- `app/optimization/batching.py` (new) — product-family helper.
- `app/optimization/config.py` — solver options (on-time weight, batching).
- `app/optimization/cp_sat_model.py` — `batch_machines` lookup.
- `app/analytics/cost.py` (new), `app/analytics/kpis.py` — cost model.
- `app/scenario/comparison.py` — cost KPIs in scenario compare.
- `app/services/orchestrator.py` — `apply_scenario`.
- `app/api/v1/routes_scenarios.py`, `schemas.py` — apply endpoint.
- `app/api/v1/routes_weekly.py` (new), `app/analytics/weekly.py` (new) — weekly plan.

Frontend:
- `src/pages/DashboardPage.tsx` — tabs, next-day plan, apply, loading, cost wiring.
- `src/components/ScenarioComparison/`, `RecommendationPanel/`, `WeeklyPlanPanel/`, `DailyProgressPanel/`, `ChatAssistant/`, `Skeleton/`, `KpiDashboard/`.
- `src/api/client.ts`, `src/types/api.ts`, `src/utils/format.ts`, `src/index.css`.

## 6. Decisions & caveats

- **Batch family compatibility:** user asked for "same product family," but there is **no family master data** (12 products, each its own routing). Family is derived deterministically from `product_id` in `batching.py` as a stand-in. Empirically the strict-family mode adds ~thousands of constraints that hurt the 30 s solve and *worsened* results, so the default is **capacity-only batching** (`batch_same_family_only=False`). Strict-family mode remains available; revisit if the solver time budget is increased.
- **Batch impact (fair A/B, same data, 30 s):** on-time 83.7% → **88.4%**, makespan **−10%**, lower tardiness & cost.
- **Scenario baseline vs top KPIs differ slightly:** the scenario "Current Plan" is a *fresh re-solve*; CP-SAT returns a FEASIBLE (not proven-optimal) solution within the 30 s limit, so two solves of the same plan can differ marginally. Scenario deltas are internally consistent.
- **Cost is directional** (assumed rates, no rate master data): labor $36/h (OT 1.5×), machine $24/h, late penalty $0.25/order-minute. For comparison, not accounting.

## 7. Suggested next steps

- Surface batching as a **"Batch Processing" scenario** in the Scenarios tab (requires the scenario engine to vary solver options per scenario, not just state).
- Add real **product-family** and **machine batch-capacity** master data to the CSV schema.
- Consider a longer/adaptive solver time budget; then re-enable strict-family batching.
- Feed **real actuals** into Daily Progress (currently deterministically simulated in `weekly.py`).
