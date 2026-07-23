import { useState } from "react";
import type { PlanModification, PlanModifications } from "../../types/api";
import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  data: PlanModifications;
  /** Revert to the original plan (discards all applied modifications). */
  onRevert?: () => void;
  /** Whether a revert / re-plan is in progress. */
  reverting?: boolean;
  /** Re-apply a previously applied modification to the current plan. */
  onReapply?: (modification: PlanModification) => void;
  /** applied_at of the modification currently being re-applied, if any. */
  reapplying?: string | null;
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

// The headline KPIs pinned at the top as the fixed original plan.
const ORIGINAL_CARDS: { key: string; label: string; fmt: (v: number) => string }[] = [
  { key: "makespan_minutes", label: "Makespan", fmt: fmtMinutes },
  { key: "on_time_delivery_rate", label: "On-time delivery", fmt: fmtPercent },
  { key: "total_tardiness_minutes", label: "Total tardiness", fmt: fmtMinutes },
  { key: "cost_total", label: "Estimated cost", fmt: fmtCurrency },
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

/** Readable list of the entities a modification targeted. */
function targetSummary(targets: Record<string, string[]>): string {
  const parts: string[] = [];
  for (const [key, values] of Object.entries(targets)) {
    if (!values || values.length === 0) continue;
    const label = key.replace(/_/g, " ").replace(/s$/, "");
    parts.push(`${values.length} ${label}${values.length > 1 ? "s" : ""}`);
  }
  return parts.join(" · ") || "the whole plan";
}

/**
 * Current committed plan view:
 *  1. the fixed original plan pinned at the top;
 *  2. a before/after KPI comparison (original → current → change); and
 *  3. the ordered list of modifications applied, each of which can be opened
 *     to see its plan detail and re-applied to the current plan.
 */
export function CurrentPlanPanel({
  data,
  onRevert,
  reverting,
  onReapply,
  reapplying,
}: Props) {
  const hasMods = data.modifications.length > 0;
  // applied_at of the modification whose plan detail is expanded.
  const [openMod, setOpenMod] = useState<string | null>(null);

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

      {/* 1. The fixed original plan, pinned at the top. */}
      <div className="nextweek-section">
        <span className="section-label">Original plan (fixed baseline)</span>
        <div className="original-plan-cards">
          {ORIGINAL_CARDS.map((c) => {
            const v = data.baseline_kpis[c.key];
            return (
              <div key={c.key} className="original-plan-card">
                <span className="opc-label">{c.label}</span>
                <span className="opc-value">
                  {v === undefined ? "—" : c.fmt(v)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 2. Before/after comparison. */}
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
            {data.modifications.map((m, i) => {
              const isOpen = openMod === `${m.applied_at}-${i}`;
              const isReapplying = reapplying === m.applied_at;
              return (
                <li key={`${m.applied_at}-${i}`} className="rec-item">
                  <div className="rec-item-head">
                    <span className="rec-title">{m.label}</span>
                    <span className={`badge ${ACTION_TONE[m.action] ?? "sev-low"}`}>
                      {m.action.replace(/_/g, " ").toLowerCase()}
                    </span>
                  </div>
                  <p className="rec-detail">
                    Applied {m.applied_at.replace("T", " ")}
                  </p>
                  <div className="rec-item-actions">
                    <button
                      type="button"
                      className="action-btn ab-ghost"
                      onClick={() =>
                        setOpenMod((cur) =>
                          cur === `${m.applied_at}-${i}`
                            ? null
                            : `${m.applied_at}-${i}`
                        )
                      }
                    >
                      {isOpen ? "Hide the plan" : "See the plan"}
                    </button>
                  </div>

                  {isOpen && (
                    <div className="mod-plan">
                      <div className="mod-plan-grid">
                        <div>
                          <span className="opc-label">Action</span>
                          <span className="opc-value-sm">
                            {m.action.replace(/_/g, " ").toLowerCase()}
                          </span>
                        </div>
                        <div>
                          <span className="opc-label">Targets</span>
                          <span className="opc-value-sm">
                            {targetSummary(m.targets)}
                          </span>
                        </div>
                        <div>
                          <span className="opc-label">Applied</span>
                          <span className="opc-value-sm">
                            {m.applied_at.replace("T", " ")}
                          </span>
                        </div>
                      </div>
                      {Object.entries(m.targets).map(([key, values]) =>
                        values && values.length > 0 ? (
                          <p key={key} className="rec-detail">
                            <strong>{key.replace(/_/g, " ")}:</strong>{" "}
                            {values.join(", ")}
                          </p>
                        ) : null
                      )}
                      {onReapply && (
                        <button
                          type="button"
                          className="primary"
                          disabled={isReapplying || reverting}
                          onClick={() => onReapply(m)}
                          title="Re-apply this modification to the current plan"
                        >
                          {isReapplying ? "Re-applying…" : "↻ Reapply this plan"}
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
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
