import type { KpiSet } from "../../types/api";
import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  kpis: KpiSet;
}

interface Card {
  label: string;
  value: string;
  tone?: "good" | "warn" | "bad" | "neutral";
  info: string;
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
      info: "Share of orders finishing on or before their due date. Higher is better — 100% means nothing is late.",
    },
    {
      label: "Avg Machine Utilization",
      value: fmtPercent(util),
      tone: "neutral",
      info: "How busy the machines are on average. Very high can mean bottlenecks; very low means spare capacity.",
    },
    {
      label: "Total Tardiness",
      value: fmtMinutes(kpis.total_tardiness_minutes),
      tone: (kpis.total_tardiness_minutes ?? 0) === 0 ? "good" : "warn",
      info: "Total lateness added up across every late order. Zero is ideal; larger means more/later delays.",
    },
    {
      label: "Makespan",
      value: fmtMinutes(kpis.metrics["makespan_minutes"]),
      tone: "neutral",
      info: "Total time from the first operation starting to the last one finishing — the length of the whole plan.",
    },
    {
      label: "Scheduled Orders",
      value: String(kpis.metrics["scheduled_orders"] ?? 0),
      tone: "neutral",
      info: "How many production orders are included in today's schedule.",
    },
    {
      label: "Est. Plan Cost",
      value:
        kpis.metrics["cost_total"] !== undefined
          ? fmtCurrency(kpis.metrics["cost_total"])
          : "—",
      tone: "neutral",
      info: "Estimated cost of running this plan (labour, machine time and any overtime).",
    },
    {
      label: "Work In Progress",
      value: String(kpis.work_in_progress ?? 0),
      tone: "neutral",
      info: "Orders already started but not yet finished — work currently on the shop floor.",
    },
  ];

  return (
    <div className="kpi-grid">
      {cards.map((c) => (
        <div key={c.label} className={`kpi-card tone-${c.tone ?? "neutral"}`}>
          <div className="kpi-value">{c.value}</div>
          <div className="kpi-label">{c.label}</div>
          <div className="kpi-tip" role="tooltip">
            <div className="kpi-tip-title">{c.label}</div>
            {c.info}
          </div>
        </div>
      ))}
    </div>
  );
}
