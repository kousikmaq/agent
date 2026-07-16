// Thin API client for the FastAPI backend (proxied by Vite).
const json = (r) => r.json();

export function getStatus() {
  return fetch("/api/status").then(json);
}

export function sendChat(query, useCache = true) {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, use_cache: useCache }),
  }).then(json);
}

export function executeAction(id, params) {
  return fetch("/api/actions/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, params }),
  }).then(json);
}

export function getPlan(scenario = "min_risk") {
  return fetch(`/api/plan?scenario=${scenario}`).then(json);
}

export function regeneratePlan(scenario = "min_risk") {
  return fetch(`/api/plan/regenerate?scenario=${scenario}`, { method: "POST" }).then(json);
}
