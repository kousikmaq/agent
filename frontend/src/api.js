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

export function getSchedule(scenario = "min_risk", maxOrders = 12) {
  return fetch(`/api/schedule?scenario=${scenario}&max_orders=${maxOrders}`).then(json);
}

export function getScenarios(maxOrders = 12) {
  return fetch(`/api/scenarios?max_orders=${maxOrders}`).then(json);
}

export function getMachines() {
  return fetch("/api/machines").then(json);
}

export function getPrioritize(topN = 12) {
  return fetch(`/api/prioritize?top_n=${topN}`).then(json);
}

export function getOrderRisk(topN = 20) {
  return fetch(`/api/risk/orders?top_n=${topN}`).then(json);
}

export function getDelayRisk(topN = 12) {
  return fetch(`/api/risk/delay?top_n=${topN}`).then(json);
}

export function getDowntime() {
  return fetch("/api/risk/downtime").then(json);
}

export function getDemandForecast() {
  return fetch("/api/demand/forecast").then(json);
}

export function getStockout() {
  return fetch("/api/demand/stockout").then(json);
}

export function getReorderRecs() {
  return fetch("/api/reorder/recommendations").then(json);
}

export function getAllocation() {
  return fetch("/api/allocation").then(json);
}

export function getInsights() {
  return fetch("/api/insights").then(json);
}

