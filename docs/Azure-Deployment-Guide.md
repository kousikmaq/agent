# Production Planning & Schedule Optimization Agent

## Azure Deployment Guide

This guide describes how to deploy the agent to Azure. It has two deployable artifacts:

- **Backend** — FastAPI app (`agent/backend`) with the OR-Tools CP-SAT scheduler, the Microsoft Agent Framework (MAF) multi-agent copilot, ML models baked in at build time, and a background daily/weekly planning thread. Deployed as a container to **Azure Container Apps**.
- **Frontend** — React + Vite + TypeScript SPA (`agent/frontend`). Built to static files and deployed to **Azure Static Web Apps**.

For the resource list and monthly cost, see [Azure-Deployment-Estimate.md](Azure-Deployment-Estimate.md).

---

## 1. Architecture

```
Browser ──► Azure Static Web Apps (React SPA)
                     │  /api/v1/* (reverse-proxied)
                     ▼
        Azure Container Apps (FastAPI backend)
         ├─ OR-Tools CP-SAT scheduler
         ├─ MAF multi-agent copilot ──► Azure OpenAI (gpt-4o, optional)
         ├─ ML models (baked into image)
         ├─ background planning scheduler (daily + Saturday weekly)
         └─ Azure Files mount ──► datasets/ , outputs/ , SQLite cache
                     │
              Azure Key Vault (secrets)  •  Application Insights (telemetry)
              Azure Container Registry (image source)
```

Key deployment facts derived from the code:

- The backend serves under `PPO_API_V1_PREFIX` (default `/api/v1`); the SPA calls a **relative** `/api/v1` base (`frontend/src/api/client.ts`), so the frontend host must reverse-proxy `/api` to the backend.
- Models are trained at **image build time** (`RUN python -m app.setup` in the Dockerfile), so runtime start is instant and `AUTO_SETUP=0`.
- The app writes to `datasets/` and `outputs/` and a SQLite cache at runtime — mount **Azure Files** so this survives redeploys, or accept that the idempotent scheduler regenerates them on start.
- The background scheduler runs only when `PPO_ENABLE_SCHEDULER=true` and is skipped under pytest; it needs the replica to stay warm (no scale-to-zero).

---

## 2. Prerequisites

- Azure CLI (`az`) and the Container Apps extension:
  ```powershell
  az extension add --name containerapp --upgrade
  az login
  ```
- Docker (to build/push the backend image) — or use `az acr build` to build in the cloud.
- Node.js 18+ (to build the frontend) — or let the Static Web Apps GitHub Action build it.
- An Azure subscription with a resource group.

Set shared variables (adjust names/region):

```powershell
$RG        = "rg-ppo-agent"
$LOC       = "eastus"
$ACR       = "acrppoagent"           # must be globally unique, lowercase
$ENVNAME   = "cae-ppo-agent"
$APP       = "ppo-backend"
$KV        = "kv-ppo-agent"          # must be globally unique
$STORAGE   = "stppoagent"            # must be globally unique, lowercase
$SHARE     = "ppo-data"

az group create --name $RG --location $LOC
```

---

## 3. Container Registry + backend image

```powershell
# Create the registry
az acr create --resource-group $RG --name $ACR --sku Basic --admin-enabled true

# Build the image in ACR from the repo root (Dockerfile is at agent/Dockerfile,
# build context is agent/ because the Dockerfile COPYs backend/).
az acr build --registry $ACR --image ppo-backend:latest --file agent/Dockerfile agent
```

> The build runs `python -m app.setup` to train the ML models into the image. Expect a longer build (OR-Tools, pandas, scikit models). Runtime startup is then instant.

---

## 4. Key Vault (secrets)

Store only the secrets the agent actually uses. **Azure OpenAI and SMTP are optional** — omit them for a deterministic-only, no-email deployment.

```powershell
az keyvault create --name $KV --resource-group $RG --location $LOC

# Optional — LLM copilot prose
az keyvault secret set --vault-name $KV --name "azure-openai-api-key"  --value "<key>"
# Optional — email/notification actions
az keyvault secret set --vault-name $KV --name "smtp-password"         --value "<app-password>"
```

The Container App will read these via a user-assigned or system-assigned managed identity (see step 7). This keeps secrets out of the repo and out of the image.

---

## 5. Storage (durable datasets / outputs / cache)

```powershell
az storage account create --name $STORAGE --resource-group $RG --location $LOC --sku Standard_LRS
$STKEY = az storage account keys list --account-name $STORAGE --resource-group $RG --query "[0].value" -o tsv
az storage share-rm create --resource-group $RG --storage-account $STORAGE --name $SHARE --quota 5
```

The share is mounted into the Container App at `/app/datasets` and `/app/outputs` in step 7 (via the environment storage link). If you prefer to skip persistence, the scheduler will regenerate a fresh dataset/plan on each start (idempotent), but committed scenarios and history will not carry across redeploys.

---

## 6. Container Apps environment

```powershell
az containerapp env create --name $ENVNAME --resource-group $RG --location $LOC

# Link the Azure Files share to the environment so the app can mount it
az containerapp env storage set `
  --name $ENVNAME --resource-group $RG `
  --storage-name ppodata `
  --azure-file-account-name $STORAGE `
  --azure-file-account-key $STKEY `
  --azure-file-share-name $SHARE `
  --access-mode ReadWrite
```

---

## 7. Deploy the backend Container App

```powershell
$ACRSERVER = az acr show --name $ACR --query loginServer -o tsv

az containerapp create `
  --name $APP --resource-group $RG --environment $ENVNAME `
  --image "$ACRSERVER/ppo-backend:latest" `
  --registry-server $ACRSERVER `
  --target-port 8000 --ingress external `
  --cpu 2 --memory 4Gi `
  --min-replicas 1 --max-replicas 1 `
  --system-assigned `
  --env-vars `
    PPO_ENVIRONMENT=production `
    PPO_LOG_JSON=true `
    PPO_ENABLE_SCHEDULER=true `
    AUTO_SETUP=0
```

Sizing/scaling notes:
- `--cpu 2 --memory 4Gi` gives the CP-SAT solver (8 search workers) and pandas/ML headroom.
- `--min-replicas 1 --max-replicas 1` keeps a single warm replica. **Do not scale to zero** — the in-memory plan/scenario caches and the background scheduler must stay alive, and multiple replicas would each run their own scheduler and caches.

Mount the file share and grant Key Vault access:

```powershell
# Give the app's managed identity read access to Key Vault secrets
$PRINCIPAL = az containerapp show --name $APP --resource-group $RG --query identity.principalId -o tsv
az keyvault set-policy --name $KV --object-id $PRINCIPAL --secret-permissions get list
```

Then add the volume mount and secret references by editing the app YAML (`az containerapp update --yaml`), mounting storage `ppodata` at `/app/datasets` and `/app/outputs`, and mapping Key Vault secrets to `PPO_AZURE_OPENAI_API_KEY` / `PPO_SMTP_PASSWORD`. Also set the non-secret Azure OpenAI settings if using the copilot:

```
PPO_AZURE_OPENAI_ENDPOINT=https://<your-openai>.openai.azure.com/
PPO_AZURE_OPENAI_DEPLOYMENT=<gpt-4o-deployment-name>
PPO_AZURE_OPENAI_API_VERSION=2024-10-21
```

Get the backend URL:

```powershell
$BACKEND = az containerapp show --name $APP --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv
"https://$BACKEND/api/v1/health"
```

---

## 8. Frontend (Azure Static Web Apps)

The SPA calls `/api/v1` relatively, so route `/api` to the backend. Add a `staticwebapp.config.json` in `agent/frontend` that rewrites API calls to the Container App:

```json
{
  "routes": [
    { "route": "/api/*", "rewrite": "https://<BACKEND-FQDN>/api/*" }
  ],
  "navigationFallback": { "rewrite": "/index.html" }
}
```

Build and deploy:

```powershell
cd agent/frontend
npm ci
npm run build        # tsc && vite build -> dist/

az staticwebapp create --name swa-ppo-agent --resource-group $RG --location $LOC
npx @azure/static-web-apps-cli deploy ./dist --deployment-token <SWA_DEPLOY_TOKEN>
```

> For CI/CD, connect the repo to Static Web Apps instead; set **app location** = `agent/frontend`, **output location** = `dist`, and the build runs `npm run build` automatically.

---

## 9. CORS

If you use the SWA reverse-proxy above, requests are same-origin and no CORS change is needed. If instead the SPA calls the backend on a different origin, set the allowed origin on the backend:

```powershell
az containerapp update --name $APP --resource-group $RG `
  --set-env-vars PPO_CORS_ORIGINS=https://<your-swa-hostname>
```

---

## 10. Monitoring (Application Insights)

```powershell
az monitor app-insights component create `
  --app ai-ppo-agent --location $LOC --resource-group $RG --application-type web
```

Wire the connection string into the app via an env var and the OpenTelemetry/App Insights SDK, or use the Container Apps built-in Log Analytics that the environment already streams to (`az containerapp logs show --name $APP --resource-group $RG --follow`).

---

## 11. Verify the deployment

```powershell
# Backend health + readiness
Invoke-RestMethod "https://$BACKEND/api/v1/health"
Invoke-RestMethod "https://$BACKEND/api/v1/ready"

# A real endpoint (dates available / a day's KPIs)
Invoke-RestMethod "https://$BACKEND/api/v1/analytics/2026-07-29"
```

Then open the Static Web App URL in a browser and confirm the dashboard loads plans and the copilot responds.

Checklist:
- [ ] `/api/v1/health` returns healthy
- [ ] SPA loads and `/api/*` reaches the backend (proxy/CORS correct)
- [ ] Azure Files mount holds `datasets/` and `outputs/` across a restart
- [ ] Copilot answers (deterministic even with no Azure OpenAI key)
- [ ] Key Vault secrets resolve (no secrets in image or env in plaintext)

---

## 12. Environment variables reference

| Variable | Purpose | Required |
|----------|---------|----------|
| `PPO_ENVIRONMENT` | `production` in Azure | Yes |
| `PPO_ENABLE_SCHEDULER` | Runs the daily/weekly planning thread | Yes (`true`) |
| `AUTO_SETUP` | `0` — models already baked into the image | Yes |
| `PPO_API_V1_PREFIX` | API base path (`/api/v1`) | Default OK |
| `PPO_CORS_ORIGINS` | Allowed SPA origin(s) | Only if not proxying |
| `PPO_SOLVER_MAX_TIME_SECONDS` | CP-SAT time limit | Default OK |
| `PPO_AZURE_OPENAI_ENDPOINT` / `_DEPLOYMENT` / `_API_VERSION` / `_API_KEY` | Copilot LLM (gpt-4o) | Optional |
| `PPO_SMTP_HOST` / `_PORT` / `_USERNAME` / `_PASSWORD` / `_USE_TLS` | Email/notification actions | Optional |
| `PPO_ALERT_EMAIL_FROM` / `_TO` | Default alert recipients | Optional |

Secrets (`*_API_KEY`, `*_PASSWORD`) should come from Key Vault references, never plaintext env vars or the image.
