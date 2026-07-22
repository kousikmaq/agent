/**
 * Shared TypeScript types mirroring the backend Pydantic DTOs.
 * Field names use snake_case to match the JSON returned by the API.
 */

export type SolverStatus =
  | "OPTIMAL"
  | "FEASIBLE"
  | "INFEASIBLE"
  | "UNKNOWN"
  | "MODEL_INVALID";

export interface ScheduledOperation {
  order_id: string;
  operation_id: string;
  machine_id: string;
  worker_id: string | null;
  start: string; // ISO datetime
  end: string; // ISO datetime
}

export interface ScheduleResult {
  business_date: string;
  status: SolverStatus;
  scheduled_operations: ScheduledOperation[];
  makespan_minutes: number | null;
  objective_value: number | null;
  solve_time_seconds: number | null;
}

export interface KpiSet {
  business_date: string;
  on_time_delivery_rate: number | null;
  average_machine_utilization: number | null;
  total_tardiness_minutes: number | null;
  work_in_progress: number | null;
  metrics: Record<string, number>;
}

export type RiskSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Risk {
  risk_id: string;
  risk_type: string;
  severity: RiskSeverity;
  title: string;
  description: string;
  affected_entities: Record<string, string[]>;
  evidence: Record<string, unknown>;
}

export interface RiskReport {
  business_date: string;
  risks: Risk[];
}

export type RecommendationFeasibility =
  | "FEASIBLE"
  | "REQUIRES_APPROVAL"
  | "INFEASIBLE";

export interface Recommendation {
  recommendation_id: string;
  action: string;
  addresses_risk_ids: string[];
  title: string;
  description: string;
  target_entities: Record<string, string[]>;
  expected_impact: Record<string, unknown>;
  feasibility: RecommendationFeasibility;
  priority: number;
}

export interface RecommendationSet {
  business_date: string;
  recommendations: Recommendation[];
}

export interface ScenarioResult {
  scenario_type: string;
  name: string;
  kpis: Record<string, number>;
  is_baseline: boolean;
}

export interface ScenarioComparison {
  business_date: string;
  baseline_type: string;
  results: ScenarioResult[];
  kpi_deltas: Record<string, Record<string, number>>;
}

export interface PlanModification {
  label: string;
  action: string;
  applied_at: string;
  targets: Record<string, string[]>;
}

export interface PlanModifications {
  business_date: string;
  baseline_kpis: Record<string, number>;
  current_kpis: Record<string, number>;
  modifications: PlanModification[];
}

export interface ChatResponse {
  business_date: string;
  question: string;
  answer: string;
}

export type DeliveryStatus = "ON_TRACK" | "AT_RISK" | "LATE" | "UNSCHEDULED";

export interface DeliveryLine {
  order_id: string;
  product_id: string;
  customer_id: string | null;
  customer_tier: string | null;
  due_date: string;
  scheduled_completion: string | null;
  tardiness_minutes: number;
  slack_minutes: number | null;
  priority: number;
  status: DeliveryStatus;
}

export interface DeliveryReport {
  business_date: string;
  horizon_days: number;
  total: number;
  on_track: number;
  at_risk: number;
  late: number;
  unscheduled: number;
  on_time_rate: number | null;
  lines: DeliveryLine[];
}

export interface AgentStepTrace {
  agent: string;
  status: string;
  attempts: number;
  duration_ms: number;
  started_at: string;
  finished_at: string;
  error: string | null;
}

export interface OrchestrationResult {
  run_id: string;
  business_date: string;
  workflow: string;
  state: string;
  message: string;
  completed_agents: string[];
  steps: AgentStepTrace[];
  total_duration_ms: number;
  persisted: boolean;
  pending_gate: string | null;
  schedule: ScheduleResult | null;
  kpis: KpiSet | null;
  risks: RiskReport | null;
  recommendations: RecommendationSet | null;
  scenario_comparison: ScenarioComparison | null;
  answer: string | null;
}

export interface DatesResponse {
  dates: string[];
}

export interface GenerateDataResponse {
  business_date: string;
  change_events: number;
}

/** Loosely typed factory snapshot (only fields the UI reads). */
export interface FactorySnapshot {
  business_date: string;
  production_orders: unknown[];
  machines: unknown[];
  workers: unknown[];
  [key: string]: unknown;
}

export type DriftTrend = "IMPROVING" | "STABLE" | "SLIPPING" | "NEW";

export interface DriftLine {
  order_id: string;
  due_date: string;
  current_completion: string | null;
  previous_completion: string | null;
  delta_minutes: number | null;
  current_status: DeliveryStatus;
  previous_status: DeliveryStatus | null;
  trend: DriftTrend;
}

export interface DeliveryDriftReport {
  business_date: string;
  previous_date: string | null;
  total: number;
  slipping: number;
  improving: number;
  stable: number;
  new: number;
  lines: DriftLine[];
}

export type WeeklyDayStatus = "PLANNED" | "ON_TRACK" | "AT_RISK" | "BEHIND";

export interface WeeklyDayPlan {
  date: string;
  weekday: string;
  is_past: boolean;
  is_today: boolean;
  planned_operations: number;
  planned_minutes: number;
  planned_orders: number;
  planned_units: number;
  actual_operations: number | null;
  actual_minutes: number | null;
  actual_orders: number | null;
  actual_units: number | null;
  attainment: number | null;
  status: WeeklyDayStatus;
}

export interface WeeklyPlanReport {
  business_date: string;
  as_of_date: string;
  week_start: string;
  week_end: string;
  plan_set_on: string;
  next_update_on: string;
  update_due: boolean;
  planned_operations: number;
  planned_minutes: number;
  planned_orders: number;
  planned_units: number;
  planned_to_date_operations: number;
  planned_to_date_units: number;
  actual_to_date_operations: number;
  actual_to_date_units: number;
  attainment_to_date: number | null;
  overall_status: WeeklyDayStatus;
  days: WeeklyDayPlan[];
}

export interface MachineStatusLine {
  machine_id: string;
  name: string;
  work_center: string;
  status: string;
}

export interface MaterialShortLine {
  product_id: string;
  net_available: number;
  safety_stock: number;
  reorder_point: number;
  below_safety: boolean;
}

export interface ShopFloorStatus {
  business_date: string;
  machine_total: number;
  machine_available: number;
  machine_running: number;
  machine_idle: number;
  machine_down: number;
  machine_maintenance: number;
  machines_attention: MachineStatusLine[];
  worker_total: number;
  worker_available: number;
  worker_unavailable: number;
  orders_planned: number;
  orders_released: number;
  orders_in_progress: number;
  orders_completed: number;
  orders_cancelled: number;
  materials_below_reorder: number;
  materials_below_safety: number;
  materials_attention: MaterialShortLine[];
  open_risks: number;
  critical_risks: number;
}
