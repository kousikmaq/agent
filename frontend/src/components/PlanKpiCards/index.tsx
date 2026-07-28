import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  /** Flat KPI dict (e.g. a scenario comparison row's `kpis`). */
  kpis: Record<string, number>;
  /** Optional heading shown above the cards. */
  title?: string;
}

interface Card {
  label: string;
  value: string;
  tone: "good" | "warn" | "bad" | "neutral";
}

/**
 * Headline KPI cards driven by a flat KPI dict (the scenario-comparison shape),
 * so they can be shown outside the Planning page — e.g. the baseline plan's
 * numbers on the Live Operations page. Mirrors {@link KpiDashboard}.
 */
export function PlanKpiCards({ kpis, title }: Props) {
  const otd = kpis["on_time_delivery_rate"] ?? null;
  const util = kpis["average_machine_utilization"] ?? null;
  const tardiness = kpis["total_tardiness_minutes"] ?? 0;

  const cards: Card[] = [
    {
      label: "On-Time Delivery",
      value: fmtPercent(otd),
      tone: otd === null ? "neutral" : otd >= 0.95 ? "good" : otd >= 0.8 ? "warn" : "bad",
    },
    {
      label: "Avg Machine Utilization",
      value: fmtPercent(util),
      tone: "neutral",
    },
    {
      label: "Total Tardiness",
      value: fmtMinutes(tardiness),
      tone: tardiness === 0 ? "good" : "warn",
    },
    {
      label: "Makespan",
      value: fmtMinutes(kpis["makespan_minutes"]),
      tone: "neutral",
    },
    {
      label: "Scheduled Orders",
      value: String(Math.round(kpis["scheduled_orders"] ?? 0)),
      tone: "neutral",
    },
    {
      label: "Est. Plan Cost",
      value:
        kpis["cost_total"] !== undefined ? fmtCurrency(kpis["cost_total"]) : "—",
      tone: "neutral",
    },
    {
      label: "Work In Progress",
      value: String(Math.round(kpis["work_in_progress"] ?? 0)),
      tone: "neutral",
    },
  ];

  return (
    <section className="kpi-section">
      {title && <div className="plan-kpi-title">{title}</div>}
      <div className="kpi-grid">
        {cards.map((c) => (
          <div key={c.label} className={`kpi-card tone-${c.tone}`}>
            <div className="kpi-value">{c.value}</div>
            <div className="kpi-label">{c.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
