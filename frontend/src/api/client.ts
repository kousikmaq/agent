/**
 * Typed API client for the FastAPI backend.
 * All calls target the versioned "/api/v1" surface (proxied by Vite in dev).
 */

import type {
  ChatResponse,
  DatesResponse,
  DeliveryDriftReport,
  DeliveryReport,
  EmailReportRequest,
  EmailResult,
  EmailRisksRequest,
  FactorySnapshot,
  GenerateDataResponse,
  KpiSet,
  OrchestrationResult,
  PlaceOrderRequest,
  PlanModifications,
  RecommendationSet,
  RiskReport,
  RolesResponse,
  ScenarioComparison,
  ScheduleResult,
  ShopFloorStatus,
  WeeklyPlanReport,
} from "../types/api";

const BASE = "/api/v1";

/** Standard error envelope returned by the backend. */
interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: unknown };
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as ApiErrorBody;
      message = body.error?.message ?? message;
      code = body.error?.code;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message, code);
  }
  return (await response.json()) as T;
}

export const api = {
  listDates: () => request<DatesResponse>("/data/dates"),

  getSnapshot: (date: string) =>
    request<FactorySnapshot>(`/data/${date}`),

  generateData: (business_date: string) =>
    request<GenerateDataResponse>("/data/generate", {
      method: "POST",
      body: JSON.stringify({ business_date }),
    }),

  runSchedule: (business_date: string, max_time_seconds?: number, force = false) =>
    request<ScheduleResult>("/schedule/run", {
      method: "POST",
      body: JSON.stringify({ business_date, max_time_seconds, force }),
    }),

  getSchedule: (date: string) => request<ScheduleResult>(`/schedule/${date}`),
  getKpis: (date: string) => request<KpiSet>(`/analytics/${date}`),
  getRisks: (date: string) => request<RiskReport>(`/risks/${date}`),
  getModifications: (date: string) =>
    request<PlanModifications>(`/risks/${date}/modifications`),
  mitigateOrderPriority: (
    date: string,
    order_ids: string[],
    priority = 10,
    max_time_seconds?: number
  ) =>
    request<ScheduleResult>(`/risks/${date}/mitigate-priority`, {
      method: "POST",
      body: JSON.stringify({ order_ids, priority, max_time_seconds }),
    }),
  applyRiskFix: (
    date: string,
    action: string,
    targets: Record<string, string[]>,
    max_time_seconds?: number
  ) =>
    request<ScheduleResult>(`/risks/${date}/apply-fix`, {
      method: "POST",
      body: JSON.stringify({ action, targets, max_time_seconds }),
    }),
  applyRiskFixes: (
    date: string,
    payload: {
      order_ids?: string[];
      priority?: number;
      actions?: { action: string; targets: Record<string, string[]> }[];
      max_time_seconds?: number;
    }
  ) =>
    request<ScheduleResult>(`/risks/${date}/apply-fixes`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getRecommendations: (date: string) =>
    request<RecommendationSet>(`/recommendations/${date}`),
  getScenarios: (date: string) =>
    request<ScenarioComparison>(`/scenarios/${date}`),

  applyScenario: (
    date: string,
    scenario_type: string,
    max_time_seconds?: number
  ) =>
    request<ScheduleResult>(`/scenarios/${date}/apply`, {
      method: "POST",
      body: JSON.stringify({ scenario_type, max_time_seconds }),
    }),

  getDeliveries: (date: string, horizon = 7) =>
    request<DeliveryReport>(`/deliveries/${date}?horizon_days=${horizon}`),
  getDeliveryDrift: (date: string, horizon = 7) =>
    request<DeliveryDriftReport>(`/deliveries/${date}/drift?horizon_days=${horizon}`),
  getShopFloor: (date: string) =>
    request<ShopFloorStatus>(`/shopfloor/${date}`),

  getWeeklyPlan: (date: string, asOf?: string) =>
    request<WeeklyPlanReport>(
      `/weekly/${date}${asOf ? `?as_of=${asOf}` : ""}`
    ),

  ask: (date: string, question: string) =>
    request<ChatResponse>(`/chat/${date}`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  runOrchestrate: (
    business_date: string,
    question?: string,
    persist = true,
    pause_after?: string[]
  ) =>
    request<OrchestrationResult>("/orchestrate/run", {
      method: "POST",
      body: JSON.stringify({ business_date, question, persist, pause_after }),
    }),

  resumeOrchestrate: (run_id: string, approve: boolean, gate?: string) =>
    request<OrchestrationResult>("/orchestrate/resume", {
      method: "POST",
      body: JSON.stringify({ run_id, approve, gate }),
    }),

  emailRisks: (date: string, payload: EmailRisksRequest = {}) =>
    request<EmailResult>(`/actions/${date}/email-risks`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  emailReport: (date: string, payload: EmailReportRequest) =>
    request<EmailResult>(`/actions/${date}/email-report`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  placeOrder: (payload: PlaceOrderRequest) =>
    request<EmailResult>("/actions/place-order", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getRoles: () => request<RolesResponse>("/actions/roles"),
};