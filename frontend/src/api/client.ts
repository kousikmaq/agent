/**
 * Typed API client for the FastAPI backend.
 * All calls target the versioned "/api/v1" surface (proxied by Vite in dev).
 */

import type {
  ChatResponse,
  DatesResponse,
  AutonomyCapability,
  DeliveryDriftReport,
  DeliveryReport,
  EmailReportRequest,
  EmailResult,
  EmailRisksRequest,
  EmailChatRequest,
  FactorySnapshot,
  GenerateDataResponse,
  KpiSet,
  OrchestrationResult,
  OptimizeGoalResponse,
  PlaceOrderRequest,
  PurchaseOrder,
  PlanModifications,
  MaterialsReport,
  RecommendationSet,
  RiskReport,
  RolesResponse,
  ScenarioComparison,
  ScenarioRecommendation,
  AutoRemediateResult,
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

  /** Revert to the original baseline plan (fast: no re-solve, no scenario re-run). */
  revertPlan: (date: string) =>
    request<ScheduleResult>(`/schedule/${date}/revert`, { method: "POST" }),

  getSchedule: (date: string) => request<ScheduleResult>(`/schedule/${date}`),
  getKpis: (date: string) => request<KpiSet>(`/analytics/${date}`),
  getRisks: (date: string) => request<RiskReport>(`/risks/${date}`),
  getModifications: (date: string) =>
    request<PlanModifications>(`/risks/${date}/modifications`),
  removeModification: (date: string, applied_at: string, max_time_seconds?: number) =>
    request<ScheduleResult>(`/risks/${date}/modifications/remove`, {
      method: "POST",
      body: JSON.stringify({ applied_at, max_time_seconds }),
    }),
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
  replanPriorities: (
    date: string,
    priorities: Record<string, number>,
    max_time_seconds?: number
  ) =>
    request<ScheduleResult>(`/risks/${date}/replan-priorities`, {
      method: "POST",
      body: JSON.stringify({ priorities, max_time_seconds }),
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
  /** The day's fixed original-plan KPIs (write-once; never moves). */
  getOriginalPlanKpis: (date: string) =>
    request<Record<string, number>>(`/scenarios/${date}/original`),
  /** Autonomously re-plan around high-priority late orders. */
  autoRemediate: (date: string, priority_max?: number, notify?: boolean) =>
    request<AutoRemediateResult>(`/schedule/auto-remediate`, {
      method: "POST",
      body: JSON.stringify({ business_date: date, priority_max, notify }),
    }),
  /** Run the full autonomous action bundle for a day. */
  runAutonomy: (date: string) =>
    request<Record<string, unknown>>(`/schedule/${date}/run-autonomy`, {
      method: "POST",
    }),

  applyScenario: (
    date: string,
    scenario_type: string,
    max_time_seconds?: number
  ) =>
    request<ScheduleResult>(`/scenarios/${date}/apply`, {
      method: "POST",
      body: JSON.stringify({ scenario_type, max_time_seconds }),
    }),

  /** Plan by a natural-language goal: LLM picks the objective weighting, the
   * solver re-solves. Pass apply=false to preview the weighting only. */
  optimizeGoal: (date: string, goal: string, apply = true) =>
    request<OptimizeGoalResponse>(`/scenarios/${date}/optimize-goal`, {
      method: "POST",
      body: JSON.stringify({ goal, apply }),
    }),

  /** Ask the advisor which solved scenario to commit (read-only advice). */
  recommendScenario: (date: string) =>
    request<ScenarioRecommendation>(`/scenarios/${date}/recommend`, {
      method: "POST",
    }),

  getDeliveries: (date: string, horizon = 7) =>
    request<DeliveryReport>(`/deliveries/${date}?horizon_days=${horizon}`),
  getDeliveryDrift: (date: string, horizon = 7) =>
    request<DeliveryDriftReport>(`/deliveries/${date}/drift?horizon_days=${horizon}`),
  getShopFloor: (date: string) =>
    request<ShopFloorStatus>(`/shopfloor/${date}`),

  /** Every autonomous capability with its status (done or standing by). */
  getAgentActivity: (date: string) =>
    request<AutonomyCapability[]>(`/shopfloor/${date}/activity`),

  getMaterials: (date: string) =>
    request<MaterialsReport>(`/materials/${date}`),
  /** Purchase orders placed (auto or manual) for the day. */
  getPurchaseOrders: (date: string) =>
    request<PurchaseOrder[]>(`/materials/${date}/purchase-orders`),
  /** Place a purchase order for one material (logged + emailed). */
  reorderMaterial: (
    date: string,
    product_id: string,
    quantity?: number,
    reason?: string
  ) =>
    request<PurchaseOrder>(`/materials/${date}/reorder`, {
      method: "POST",
      body: JSON.stringify({ product_id, quantity, reason }),
    }),

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

  /** Email the current assistant conversation (content-based, not a fixed report). */
  emailChat: (date: string, payload: EmailChatRequest) =>
    request<EmailResult>(`/actions/${date}/email-chat`, {
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