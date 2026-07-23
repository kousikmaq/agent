import { useMemo, useState } from "react";
import type { ScheduledOperation } from "../../types/api";
import { fmtDateTime, durationMinutes } from "../../utils/format";

interface Props {
  operations: ScheduledOperation[];
  /** When set, only operations that start on this business day are shown. */
  date?: string;
}

/** Deterministic HSL colour per key (order/machine) for bar fills. */
function colourFor(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) % 360;
  return `hsl(${hash}, 62%, 55%)`;
}

/**
 * Gantt chart of scheduled operations grouped by production order.
 * Bars are positioned proportionally across the schedule's time span and
 * coloured by machine. Click a machine in the legend to focus on just its
 * operations (others dim out).
 */
export function GanttChart({ operations, date }: Props) {
  const [focus, setFocus] = useState<string | null>(null);

  const { rows, min, span, ticks, machines } = useMemo(() => {
    // Show only the selected business day's operations (the solver schedules the
    // full backlog, which can spill into later days).
    const dayOps = date
      ? operations.filter((o) => o.start.slice(0, 10) === date)
      : operations;
    if (dayOps.length === 0)
      return { rows: [], min: 0, span: 1, ticks: [], machines: [] };
    const starts = dayOps.map((o) => new Date(o.start).getTime());
    const ends = dayOps.map((o) => new Date(o.end).getTime());
    const minT = Math.min(...starts);
    const maxT = Math.max(...ends);
    const spanT = Math.max(1, maxT - minT);
    const grouped = new Map<string, ScheduledOperation[]>();
    for (const op of dayOps) {
      const list = grouped.get(op.order_id) ?? [];
      list.push(op);
      grouped.set(op.order_id, list);
    }
    const rows = Array.from(grouped.entries()).sort((a, b) =>
      a[0].localeCompare(b[0])
    );
    const machines = Array.from(new Set(dayOps.map((o) => o.machine_id))).sort();
    // Adaptive hour ticks aligned to clean clock hours. Midnight ticks show the
    // date (M/D) so multi-day spans stay legible; other ticks show the hour.
    const HOUR = 3_600_000;
    const totalHours = spanT / HOUR;
    const STEPS = [1, 2, 3, 4, 6, 12, 24];
    const step = STEPS.find((s) => totalHours / s <= 16) ?? 24;
    const cursor = new Date(minT);
    cursor.setMinutes(0, 0, 0);
    if (cursor.getTime() < minT) cursor.setHours(cursor.getHours() + 1);
    while (cursor.getHours() % step !== 0) cursor.setHours(cursor.getHours() + 1);
    const ticks: { fraction: number; label: string; day: boolean }[] = [];
    for (; cursor.getTime() <= maxT; cursor.setHours(cursor.getHours() + step)) {
      const hour = cursor.getHours();
      const isMidnight = hour === 0;
      ticks.push({
        fraction: (cursor.getTime() - minT) / spanT,
        label: isMidnight
          ? `${cursor.getMonth() + 1}/${cursor.getDate()}`
          : String(hour % 12 === 0 ? 12 : hour % 12),
        day: isMidnight,
      });
    }
    return { rows, min: minT, span: spanT, ticks, machines };
  }, [operations, date]);

  if (rows.length === 0) {
    return <p className="empty">No scheduled operations for this day.</p>;
  }

  const focusOps = focus
    ? rows.flatMap(([, ops]) => ops.filter((o) => o.machine_id === focus))
    : [];
  const focusOrders = focus
    ? new Set(focusOps.map((o) => o.order_id)).size
    : 0;

  return (
    <div>
      <div className="gantt-legend">
        {machines.map((m) => (
          <button
            key={m}
            type="button"
            className={`gantt-legend-item${
              focus && focus !== m ? " dimmed" : ""
            }${focus === m ? " focused" : ""}`}
            onClick={() => setFocus((cur) => (cur === m ? null : m))}
            title={`Click to focus on ${m}`}
          >
            <span
              className="gantt-legend-swatch"
              style={{ backgroundColor: colourFor(m) }}
            />
            {m}
          </button>
        ))}
        {focus && (
          <span className="gantt-focus-hint">
            Focused on {focus} — click again to show all
          </span>
        )}
      </div>

      <div className="gantt">
        <div className="gantt-axis">
          <div className="gantt-label" aria-hidden="true" />
          <div className="gantt-axis-track">
            {ticks.map((t, i) => (
              <div
                key={i}
                className="gantt-tick"
                style={{ left: `${t.fraction * 100}%` }}
              >
                <span
                  className={`gantt-tick-label${t.day ? " gantt-tick-day" : ""}`}
                >
                  {t.label}
                </span>
                <span className="gantt-tick-mark" />
              </div>
            ))}
          </div>
        </div>
        {rows.map(([orderId, ops]) => {
          const rowHasFocus = focus ? ops.some((o) => o.machine_id === focus) : true;
          return (
            <div
              key={orderId}
              className={`gantt-row${focus && !rowHasFocus ? " dimmed" : ""}`}
            >
              <div className="gantt-label" title={orderId}>
                {orderId}
              </div>
              <div className="gantt-track">
                {ops.map((op) => {
                  const left =
                    ((new Date(op.start).getTime() - min) / span) * 100;
                  const width = Math.max(
                    0.5,
                    ((new Date(op.end).getTime() -
                      new Date(op.start).getTime()) /
                      span) *
                      100
                  );
                  const dim = focus ? op.machine_id !== focus : false;
                  return (
                    <div
                      key={`${op.order_id}-${op.operation_id}-${op.start}`}
                      className={`gantt-bar${dim ? " dimmed" : ""}`}
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        backgroundColor: colourFor(op.machine_id),
                      }}
                      title={`${op.operation_id} on ${op.machine_id}${
                        op.worker_id ? ` / ${op.worker_id}` : ""
                      }\n${fmtDateTime(op.start)} → ${fmtDateTime(
                        op.end
                      )} (${durationMinutes(op.start, op.end)}m)`}
                    >
                      <span className="gantt-bar-text">{op.machine_id}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="gantt-explain">
        {focus ? (
          <span>
            Showing only <strong>{focus}</strong>: {focusOps.length} operation
            {focusOps.length === 1 ? "" : "s"} across {focusOrders} order
            {focusOrders === 1 ? "" : "s"}. Everything else is dimmed. Click{" "}
            {focus} again to show the full plan.
          </span>
        ) : (
          <span className="muted">
            Each row is a production order; each bar is one operation, placed on
            a time axis and coloured by the machine running it. Longer bars take
            longer. <strong>Click a machine above</strong> to focus on just its
            work, or hover any bar for details.
          </span>
        )}
      </div>
    </div>
  );
}
