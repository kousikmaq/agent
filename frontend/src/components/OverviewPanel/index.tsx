import type {
  DeliveryReport,
  KpiSet,
  RecommendationSet,
  RiskReport,
  ScenarioComparison,
  ScheduleResult,
} from "../../types/api";

interface Props {
  schedule: ScheduleResult;
  kpis: KpiSet;
  risks: RiskReport;
  recommendations: RecommendationSet;
  scenarios: ScenarioComparison;
  deliveries: DeliveryReport | null;
  onNavigate: (tab: string) => void;
  /** When true, show only plan-related cards (a forward next-day plan). */
  planOnly?: boolean;
}

const CONFLICT_TYPES = new Set(["WORKER_CONFLICT", "MAINTENANCE_CONFLICT"]);

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Compute the busiest machine (bottleneck) from scheduled operations. */
function bottleneck(schedule: ScheduleResult): { machine: string; minutes: number } | null {
  const load = new Map<string, number>();
  for (const op of schedule.scheduled_operations) {
    const mins = (new Date(op.end).getTime() - new Date(op.start).getTime()) / 60000;
    load.set(op.machine_id, (load.get(op.machine_id) ?? 0) + mins);
  }
  let best: { machine: string; minutes: number } | null = null;
  for (const [machine, minutes] of load) {
    if (!best || minutes > best.minutes) best = { machine, minutes };
  }
  return best;
}

interface Card {
  key: string;
  title: string;
  headline: string;
  sub: string;
  tone: "good" | "warn" | "bad" | "neutral";
  tab: string;
  cta: string;
}

/** Capability overview: frames the 6 core planning features with live numbers. */
export function OverviewPanel({
  schedule,
  kpis,
  risks,
  recommendations,
  scenarios,
  deliveries,
  onNavigate,
  planOnly = false,
}: Props) {
  const bn = bottleneck(schedule);
  const conflicts = risks.risks.filter((r) => CONFLICT_TYPES.has(r.risk_type));
  const atRisk = deliveries
    ? deliveries.at_risk + deliveries.late
    : risks.risks.filter((r) => r.risk_type === "DELAYED_ORDER").length;
  const feasibleRecs = recommendations.recommendations.filter(
    (r) => r.feasibility === "FEASIBLE"
  ).length;
  const planOk = schedule.status === "OPTIMAL" || schedule.status === "FEASIBLE";

  const cards: Card[] = [
    {
      key: "bottleneck",
      title: "Capacity bottlenecks",
      headline: bn ? bn.machine : "—",
      sub: bn
        ? `${Math.round(bn.minutes / 60)}h load · avg util ${pct(
            kpis.average_machine_utilization
          )}`
        : "No operations scheduled",
      tone: "warn",
      tab: "machines",
      cta: "View machine load",
    },
    {
      key: "conflicts",
      title: "Scheduling conflicts",
      headline: String(conflicts.length),
      sub: conflicts.length
        ? "worker / maintenance clashes flagged"
        : "No conflicts detected",
      tone: conflicts.length ? "bad" : "good",
      tab: "risks",
      cta: "View conflicts",
    },
    {
      key: "plan",
      title: "Optimized production plan",
      headline: schedule.status,
      sub: `${schedule.scheduled_operations.length} ops · makespan ${
        schedule.makespan_minutes != null
          ? Math.round(schedule.makespan_minutes / 60) + "h"
          : "—"
      }`,
      tone: planOk ? "good" : "bad",
      tab: "gantt",
      cta: "View schedule",
    },
    {
      key: "atrisk",
      title: "At-risk orders",
      headline: String(atRisk),
      sub: deliveries
        ? `on-time rate ${pct(deliveries.on_time_rate)}`
        : "orders flagged late / at risk",
      tone: atRisk ? "warn" : "good",
      tab: "deliveries",
      cta: "View deliveries",
    },
    {
      key: "recs",
      title: "Recommended fixes",
      headline: String(recommendations.recommendations.length),
      sub: `${feasibleRecs} feasible now`,
      tone: recommendations.recommendations.length ? "neutral" : "good",
      tab: "risks",
      cta: "Act on risks",
    },
    {
      key: "scenarios",
      title: "Planning scenarios",
      headline: String(scenarios.results.length),
      sub: "what-if plans compared vs baseline",
      tone: "neutral",
      tab: "scenarios",
      cta: "Compare scenarios",
    },
  ];

  // On a forward next-day plan we can only show the plan, not risk/assessment.
  const planKeys = new Set(["bottleneck", "plan", "scenarios"]);
  const shownCards = planOnly
    ? cards.filter((c) => planKeys.has(c.key))
    : cards;

  return (
    <div className="overview">
      <p className="muted">
        {planOnly
          ? `Forward plan for ${schedule.business_date} — plan only. Risk and`
          : `Six core capabilities for ${schedule.business_date}. Each card links to the`}{" "}
        {planOnly
          ? "delivery assessment appear once the day is worked."
          : "full detail view."}
      </p>
      <div className="overview-grid">
        {shownCards.map((c) => (
          <div key={c.key} className={`overview-card tone-${c.tone}`}>
            <div className="overview-card-title">{c.title}</div>
            <div className="overview-card-headline">{c.headline}</div>
            <div className="overview-card-sub">{c.sub}</div>
            <button className="overview-card-cta" onClick={() => onNavigate(c.tab)}>
              {c.cta} →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
