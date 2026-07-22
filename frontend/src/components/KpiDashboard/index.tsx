import type { KpiSet } from "../../types/api";
import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  kpis: KpiSet;
}

interface Card {
  label: string;
  value: string;
  tone?: "good" | "warn" | "bad" | "neutral";
}

/** Headline KPI cards for a planned production day. */
export function KpiDashboard({ kpis }: Props) {
  const otd = kpis.on_time_delivery_rate;
  const util = kpis.average_machine_utilization;

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
      value: fmtMinutes(kpis.total_tardiness_minutes),
      tone: (kpis.total_tardiness_minutes ?? 0) === 0 ? "good" : "warn",
    },
    {
      label: "Makespan",
      value: fmtMinutes(kpis.metrics["makespan_minutes"]),
      tone: "neutral",
    },
    {
      label: "Scheduled Orders",
      value: String(kpis.metrics["scheduled_orders"] ?? 0),
      tone: "neutral",
    },
    {
      label: "Est. Plan Cost",
      value:
        kpis.metrics["cost_total"] !== undefined
          ? fmtCurrency(kpis.metrics["cost_total"])
          : "—",
      tone: "neutral",
    },
    {
      label: "Work In Progress",
      value: String(kpis.work_in_progress ?? 0),
      tone: "neutral",
    },
  ];

  return (
    <div className="kpi-grid">
      {cards.map((c) => (
        <div key={c.label} className={`kpi-card tone-${c.tone ?? "neutral"}`}>
          <div className="kpi-value">{c.value}</div>
          <div className="kpi-label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
