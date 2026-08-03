# Production Planning & Schedule Optimization Agent

## Azure Deployment — Resources & Billing Estimate

---

## 1. Azure Resources Required

| Resource | Why It's Needed |
|----------|-----------------|
| **Azure Container Apps** | Hosts the FastAPI backend (REST API, the Microsoft Agent Framework multi-agent copilot, the OR-Tools CP-SAT scheduler, and the background daily/weekly planning thread). Runs the container 24/7 — it must stay warm (min 1 replica, **no scale-to-zero**) because it holds in-memory plan/scenario caches and runs an internal scheduler that refreshes today's plan and publishes next week's plans every Saturday. |
| **Azure Container Registry (ACR)** | Private registry to store the backend's Docker image before Container Apps pulls and runs it. The image is larger than a typical API because OR-Tools, pandas, and the ML models are **trained and baked in at build time** (`python -m app.setup`) so runtime start is instant. |
| **Azure Static Web Apps** | Hosts the built React/Vite/TypeScript frontend (dashboard, plan/scenario, live-operations views) as a static site; no server needed for this part. |
| **Azure Files (Storage Account)** | The agent is **file-based** — it writes generated daily datasets (`datasets/<date>/` CSVs), plan/scenario/risk results (`outputs/<date>/` JSON), and a SQLite semantic cache. A mounted Azure Files share keeps these artifacts so plans and committed scenarios survive redeploys/restarts. (Replaces the SQL database used by other services — this agent needs no relational DB.) |
| **Azure Key Vault** | Stores secrets (Azure OpenAI key, SMTP password for the email/notification actions) so they're never hardcoded or committed to the repo. Settings are loaded with the `PPO_` env prefix and injected from Key Vault at startup. |
| **Azure OpenAI Service (gpt-4o)** | **Optional.** Powers the natural-language copilot chat — it only *rewrites the prose* on top of the deterministic router's structured answer. The scheduling engine and the multi-agent layer run fully **without** it; if no key is configured the agent still answers deterministically. |
| **Application Insights** | Monitoring — request tracing, error logs, and performance data for the backend (solver timings, planning-cycle runs). |

> **Design note:** Scheduling is 100% deterministic (OR-Tools CP-SAT + business rules). The LLM never makes scheduling decisions, so Azure OpenAI is a convenience layer, not a hard dependency.

---

## 2. Billing Calculation

Estimated using the **same Pay-As-You-Go rate basis as the MAIR estimate** (East US region) so the two are directly comparable. Assumes a low-traffic internal deployment: 1 always-on backend replica, light copilot usage, one automated planning cycle per day plus a weekly publish on Saturdays.

### Assumptions used
- **Container Apps:** 2 vCPU / 4 GiB, 1 replica kept warm all month. Sized higher than a plain API because the CP-SAT solver runs with 8 search workers (up to ~60 s per solve) and pandas + the baked-in ML models need headroom; scale-to-zero is disabled so the in-memory caches and the background planning thread stay alive. Request traffic stays well under the 2M free requests/month.
- **Azure Files:** small Standard (transaction-optimized) share (~5 GB) for `datasets/`, `outputs/`, and the SQLite cache, with light daily I/O.
- **Azure OpenAI:** ~1,500 copilot chats/month, ~1,500 input + 500 output tokens per chat (a typical planning Q&A exchange). Optional — omit this line for a deterministic-only deployment.

### Line-item calculation

| Resource | Rate | Calculation | Monthly Cost |
|----------|------|-------------|--------------|
| Container Apps (2 vCPU / 4 GiB, always-on) | $0.000008/vCPU-s, $0.000001/GiB-s | 2 vCPU × 2,592,000 s × $0.000008 + 4 GiB × 2,592,000 s × $0.000001 | **$51.84** |
| Container Apps requests | $0.40/million after 2M free | Under free tier at this traffic level | $0.00 |
| Azure Container Registry (Basic) | $0.167/day | $0.167 × 30 days | $5.01 |
| Azure Static Web Apps | Free tier | Standard SPA hosting, no custom auth/API needs | $0.00 |
| Azure Files (Standard, ~5 GB + light I/O) | ~$0.06/GB + transactions | Durable share for datasets / outputs / SQLite cache | $3.00 |
| Azure Key Vault | ~$0.03/10,000 operations | Low-volume secret reads at startup | $0.50 |
| Application Insights | First 5 GB/month free | Under free tier at this log volume | $0.00 |
| Azure OpenAI — gpt-4o input *(optional)* | $2.50/1M tokens | 1,500 chats × 1,500 tokens = 2.25M tokens × $2.50 | $5.63 |
| Azure OpenAI — gpt-4o output *(optional)* | $10.00/1M tokens | 1,500 chats × 500 tokens = 0.75M tokens × $10.00 | $7.50 |
| **Total — with copilot (LLM enabled)** | | | **$73.48/month** |
| **Total — deterministic-only (no Azure OpenAI)** | | | **$60.35/month** |

---

## 3. Notes & Cost Levers

- **Biggest line is compute.** Dropping to 1 vCPU / 2 GiB (like the MAIR baseline) would cut Container Apps to **$25.92/month**, but risks out-of-memory and slower CP-SAT solves given OR-Tools + pandas + the ML models; 2 vCPU / 4 GiB is the recommended safe size.
- **Azure OpenAI is fully optional** — leaving it out saves ~$13/month and the agent still answers planning questions deterministically.
- **No relational database is required.** The workflow state (draft → committed scenario → applied plan) is persisted as JSON on the Azure Files share, so there is no Azure SQL line item.
- **ACR could be shared** across environments; the Basic tier ($5/month) is sufficient for a single private image.
- **Application Insights and Static Web Apps** are expected to stay within their free tiers at this scale.
