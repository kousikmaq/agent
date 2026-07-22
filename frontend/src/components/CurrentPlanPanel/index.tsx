import type { PlanModifications } from "../../types/api";
import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  data: PlanModifications;
  /** Revert to the original plan (discards all applied modifications). */
  onRevert?: () => void;
  /** Whether a revert / re-plan is in progress. */
  reverting?: boolean;
}

const fmtCount = (v: number) => String(Math.round(v));

// KPIs compared before/after, with the display formatter and improvement dir.
const ROWS: {
  key: string;
  label: string;
  fmt: (v: number) => string;
  lowerBetter: boolean;
}[] = [
  { key: "makespan_minutes", label: "Makespan", fmt: fmtMinutes, lowerBetter: true },
  {
    key: "total_tardiness_minutes",
    label: "Total tardiness",
    fmt: fmtMinutes,
    lowerBetter: true,
  },
  {
    key: "on_time_delivery_rate",
    label: "On-time delivery",
    fmt: fmtPercent,
    lowerBetter: false,
  },
  {
    key: "average_machine_utilization",
    label: "Machine utilization",
    fmt: fmtPercent,
    lowerBetter: false,
  },
  { key: "scheduled_orders", label: "Scheduled orders", fmt: fmtCount, lowerBetter: false },
  { key: "work_in_progress", label: "Work in progress", fmt: fmtCount, lowerBetter: true },
  { key: "cost_total", label: "Estimated cost", fmt: fmtCurrency, lowerBetter: true },
];

const ACTION_TONE: Record<string, string> = {
  RAISE_PRIORITY: "feas-approve",
  ASSIGN_ALTERNATE_MACHINE: "feas-ok",
  ADD_SHIFT: "feas-ok",
  APPROVE_OVERTIME: "feas-approve",
  RESCHEDULE_MAINTENANCE: "feas-ok",
  ASSIGN_ALTERNATE_WORKER: "feas-ok",
  EXPEDITE_PURCHASE_ORDER: "feas-ok",
  REPLENISH_ALTERNATE_SUPPLIER: "feas-ok",
  SPLIT_BATCH: "feas-approve",
};

/**
 * Current committed plan vs the originally planned one: a before/after KPI
 * comparison plus the ordered list of modifications (fixes) applied today.
 */
export function CurrentPlanPanel({ data, onRevert, reverting }: Props) {
  const hasMods = data.modifications.length > 0;

  return (
    <div className="currentplan">
      <div className="currentplan-head">
        <p className="panel-note">
          The current committed plan for {data.business_date}
          {hasMods
            ? ` — with ${data.modifications.length} modification${
                data.modifications.length > 1 ? "s" : ""
              } applied. Compared against the originally planned schedule.`
            : " — no modifications applied yet. It matches the originally planned schedule."}
        </p>
        {onRevert && hasMods && (
          <button
            type="button"
            className="revert-btn"
            disabled={reverting}
            onClick={onRevert}
            title="Discard all modifications and restore the original plan"
          >
            {reverting ? "Reverting…" : "↺ Revert to original plan"}
          </button>
        )}
      </div>

      <div className="nextweek-section">
        <span className="section-label">Original plan → current plan</span>
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Original</th>
              <th>Current</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => {
              const before = data.baseline_kpis[r.key];
              const after = data.current_kpis[r.key];
              const d =
                before === undefined || after === undefined
                  ? null
                  : after - before;
              const better =
                d === null || d === 0 ? null : r.lowerBetter ? d < 0 : d > 0;
              return (
                <tr key={r.key}>
                  <td>{r.label}</td>
                  <td>{before === undefined ? "—" : r.fmt(before)}</td>
                  <td>
                    <strong>{after === undefined ? "—" : r.fmt(after)}</strong>
                  </td>
                  <td>
                    {d === null || d === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      <span className={better ? "kpi-better" : "kpi-worse"}>
                        {d < 0 ? "▼" : "▲"} {r.fmt(Math.abs(d))}{" "}
                        {better ? "better" : "worse"}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="nextweek-section">
        <span className="section-label">
          Modifications applied ({data.modifications.length})
        </span>
        {hasMods ? (
          <ul className="rec-list">
            {data.modifications.map((m, i) => (
              <li key={i} className="rec-item">
                <div className="rec-item-head">
                  <span className="rec-title">{m.label}</span>
                  <span className={`badge ${ACTION_TONE[m.action] ?? "sev-low"}`}>
                    {m.action.replace(/_/g, " ").toLowerCase()}
                  </span>
                </div>
                <p className="rec-detail">
                  Applied {m.applied_at.replace("T", " ")}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">
            No fixes applied. Apply a fix from the Risks tab to modify this plan.
          </p>
        )}
      </div>
    </div>
  );
}
