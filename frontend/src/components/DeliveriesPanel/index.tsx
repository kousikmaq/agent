import { useMemo, useState } from "react";
import type { DeliveryReport, DeliveryStatus } from "../../types/api";
import { fmtDateTime, fmtMinutes } from "../../utils/format";

interface Props {
  report: DeliveryReport;
  /** Hand selected late/at-risk orders to the Risks tab for direct action. */
  onMitigateInRisks?: (orderIds: string[]) => void;
  /** Raise priority of the selected orders and re-plan directly from here. */
  onRaisePriority?: (orderIds: string[]) => void;
  /** Token currently being re-planned, if any. */
  mitigating?: string | null;
}

function statusBadge(status: DeliveryStatus): string {
  switch (status) {
    case "ON_TRACK":
      return "feas-ok";
    case "AT_RISK":
      return "feas-approve";
    default:
      return "feas-no"; // LATE / UNSCHEDULED
  }
}

function statusLabel(status: DeliveryStatus): string {
  return status.replace("_", " ").toLowerCase();
}

// Most time-critical first: late, then at-risk, then on-track, then unscheduled.
const STATUS_RANK: Record<DeliveryStatus, number> = {
  LATE: 0,
  AT_RISK: 1,
  ON_TRACK: 2,
  UNSCHEDULED: 3,
};

/** Delivery commitments board: RAG status per order due within the horizon. */
export function DeliveriesPanel({
  report,
  onMitigateInRisks,
  onRaisePriority,
  mitigating,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Sort by urgency: late orders (most overdue first), then by soonest due
  // date, so the most time-critical commitments are at the top.
  const lines = useMemo(
    () =>
      [...report.lines].sort((a, b) => {
        const rank = STATUS_RANK[a.status] - STATUS_RANK[b.status];
        if (rank !== 0) return rank;
        if (a.status === "LATE" && b.status === "LATE") {
          return b.tardiness_minutes - a.tardiness_minutes;
        }
        const due = a.due_date.localeCompare(b.due_date);
        if (due !== 0) return due;
        return (a.slack_minutes ?? 0) - (b.slack_minutes ?? 0);
      }),
    [report.lines]
  );

  // Only late / at-risk orders can be actioned (they map to delayed-order risks).
  const actionable = useMemo(
    () =>
      lines
        .filter((l) => l.status === "LATE" || l.status === "AT_RISK")
        .map((l) => l.order_id),
    [lines]
  );

  if (report.total === 0) {
    return (
      <p className="empty">
        No delivery commitments in the next {report.horizon_days} days.
      </p>
    );
  }

  const isActionable = (s: DeliveryStatus) => s === "LATE" || s === "AT_RISK";
  const allActionableSelected =
    actionable.length > 0 && actionable.every((id) => selected.has(id));

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (allActionableSelected) actionable.forEach((id) => next.delete(id));
      else actionable.forEach((id) => next.add(id));
      return next;
    });

  return (
    <div className="panel-list">
      <div className="severity-summary">
        <span className="badge feas-ok">On track: {report.on_track}</span>
        <span className="badge feas-approve">At risk: {report.at_risk}</span>
        <span className="badge feas-no">Late: {report.late}</span>
        <span className="badge sev-low">Unscheduled: {report.unscheduled}</span>
        <span className="muted">
          Commitments (next {report.horizon_days}d): {report.total}
        </span>
      </div>

      {(onMitigateInRisks || onRaisePriority) && actionable.length > 0 && (
        <div className="risk-bulkbar">
          <span className="risk-bulkbar-count">
            {selected.size > 0
              ? `${selected.size} order${selected.size > 1 ? "s" : ""} selected`
              : "Select late / at-risk orders to act on them"}
          </span>
          <div className="risk-bulkbar-actions">
            {onRaisePriority && (
              <button
                type="button"
                className="primary"
                disabled={selected.size === 0 || mitigating === "deliveries"}
                onClick={() => onRaisePriority(Array.from(selected))}
              >
                {mitigating === "deliveries"
                  ? "Re-planning…"
                  : `Raise priority & re-plan (${selected.size})`}
              </button>
            )}
            {onMitigateInRisks && (
              <button
                type="button"
                disabled={selected.size === 0}
                onClick={() => onMitigateInRisks(Array.from(selected))}
              >
                More actions in Risks →
              </button>
            )}
            {selected.size > 0 && (
              <button
                type="button"
                className="rec-dismiss"
                onClick={() => setSelected(new Set())}
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      <table className="data-table">
        <thead>
          <tr>
            {(onMitigateInRisks || onRaisePriority) && (
              <th>
                <input
                  type="checkbox"
                  checked={allActionableSelected}
                  onChange={toggleAll}
                  aria-label="Select all late and at-risk orders"
                />
              </th>
            )}
            <th>Order</th>
            <th>Customer</th>
            <th>Due</th>
            <th>Scheduled completion</th>
            <th>Slack / Late</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((ln) => (
            <tr key={ln.order_id}>
              {(onMitigateInRisks || onRaisePriority) && (
                <td>
                  {isActionable(ln.status) ? (
                    <input
                      type="checkbox"
                      checked={selected.has(ln.order_id)}
                      onChange={() => toggle(ln.order_id)}
                      aria-label={`Select ${ln.order_id}`}
                    />
                  ) : null}
                </td>
              )}
              <td>{ln.order_id}</td>
              <td>
                {ln.customer_id ?? "—"}
                {ln.customer_tier && (
                  <span className="muted"> ({ln.customer_tier})</span>
                )}
              </td>
              <td>{ln.due_date}</td>
              <td>
                {ln.scheduled_completion
                  ? fmtDateTime(ln.scheduled_completion)
                  : "—"}
              </td>
              <td>
                {ln.status === "LATE"
                  ? `late ${fmtMinutes(ln.tardiness_minutes)}`
                  : ln.slack_minutes !== null
                  ? fmtMinutes(ln.slack_minutes)
                  : "—"}
              </td>
              <td>
                <span className={`badge ${statusBadge(ln.status)}`}>
                  {statusLabel(ln.status)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
