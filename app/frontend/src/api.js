// Small API helper. Backend runs on port 8000 (see backend README).
const BASE = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

export const getOverview = () => get('/api/capacity/overview')
export const getHeatmap = () => get('/api/capacity/heatmap')
export const getWeek = (week) => get(`/api/capacity${week ? `?week=${week}` : ''}`)
export const getPriority = (week) => get(`/api/priority${week ? `?week=${week}` : ''}`)
export const getAllocation = (week) => get(`/api/allocate${week ? `?week=${week}` : ''}`)
export const getSchedule = (week, n = 12) => get(`/api/schedule?n=${n}${week ? `&week=${week}` : ''}`)
export const getRisk = (week) => get(`/api/risk${week ? `?week=${week}` : ''}`)
export const getDemand = () => get('/api/demand')
export const getScenarios = (week) => get(`/api/scenarios${week ? `?week=${week}` : ''}`)
export const getWeeks = () => get('/api/weeks')
export const getDatasetSummary = () => get('/api/dataset/summary')
export const getFeatures = () => get('/api/features')

export async function askAgent(question) {
  const res = await fetch(`${BASE}/api/agent/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question })
  })
  if (!res.ok) throw new Error(`ask -> ${res.status}`)
  return res.json()
}
