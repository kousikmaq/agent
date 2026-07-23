import { useMemo, useState } from "react";
import type { ScheduledOperation } from "../../types/api";
import { fmtDateTime, durationMinutes } from "../../utils/format";
import { colourFor } from "../../utils/colors";

interface Props {
  operations: ScheduledOperation[];
}

/**
 * Timeline of scheduled operations grouped by machine, revealing machine
 * loading and idle gaps across the schedule span. Click a machine to focus on
 * just its row (others dim out).
 */
export function MachineTimeline({ operations }: Props) {
  const [focus, setFocus] = useState<string | null>(null);

  const { rows, min, span, ticks } = useMemo(() => {
    if (operations.length === 0)
      return { rows: [], min: 0, span: 1, ticks: [] };
    const starts = operations.map((o) => new Date(o.start).getTime());
    const ends = operations.map((o) => new Date(o.end).getTime());
    const minT = Math.min(...starts);
    const maxT = Math.max(...ends);
    const spanT = Math.max(1, maxT - minT);
    const grouped = new Map<string, ScheduledOperation[]>();
    for (const op of operations) {
      const list = grouped.get(op.machine_id) ?? [];
      list.push(op);
      grouped.set(op.machine_id, list);
    }
    const rows = Array.from(grouped.entries()).sort((a, b) =>
      a[0].localeCompare(b[0])
    );
    // Adaptive hour ticks aligned to clean clock hours; midnight ticks show the
    // date (M/D) so multi-day spans stay legible.
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
      const hour12 = hour % 12 === 0 ? 12 : hour % 12;
      const ampm = hour < 12 ? "AM" : "PM";
      ticks.push({
        fraction: (cursor.getTime() - minT) / spanT,
        label: isMidnight
          ? cursor.toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })
          : `${hour12} ${ampm}`,
        day: isMidnight,
      });
    }
    return { rows, min: minT, span: spanT, ticks };
  }, [operations]);

  if (operations.length === 0) {
    return <p className="empty">No scheduled operations.</p>;
  }

  // Filter/legend is by ORDER (bars are coloured by order). Clicking an order
  // focuses just its operations across the machines.
  const orders = Array.from(
    new Set(rows.flatMap(([, ops]) => ops.map((o) => o.order_id)))
  ).sort();
  const focusOps = focus
    ? rows.flatMap(([, ops]) => ops.filter((o) => o.order_id === focus))
    : [];
  const focusMachines = focus
    ? new Set(
        rows
          .filter(([, ops]) => ops.some((o) => o.order_id === focus))
          .map(([m]) => m)
      ).size
    : 0;
  const focusMinutes = focusOps.reduce(
    (sum, o) => sum + durationMinutes(o.start, o.end),
    0
  );

  return (
    <div>
      <div className="gantt-legend">
        {orders.map((orderId) => (
          <button
            key={orderId}
            type="button"
            className={`gantt-legend-item${
              focus && focus !== orderId ? " dimmed" : ""
            }${focus === orderId ? " focused" : ""}`}
            onClick={() =>
              setFocus((cur) => (cur === orderId ? null : orderId))
            }
            title={`Click to focus on ${orderId}`}
          >
            <span
              className="gantt-legend-swatch"
              style={{ backgroundColor: colourFor(orderId) }}
            />
            {orderId}
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
        {rows.map(([machineId, ops]) => {
          const rowHasFocus = focus
            ? ops.some((o) => o.order_id === focus)
            : true;
          return (
            <div
              key={machineId}
              className={`gantt-row${focus && !rowHasFocus ? " dimmed" : ""}`}
            >
              <div className="gantt-label" title={machineId}>
                {machineId}
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
                  const dim = focus ? op.order_id !== focus : false;
                  return (
                    <div
                      key={`${op.order_id}-${op.operation_id}-${op.start}`}
                      className={`gantt-bar${dim ? " dimmed" : ""}`}
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        backgroundColor: colourFor(op.order_id),
                      }}
                      title={`${op.order_id} · ${op.operation_id}\n${fmtDateTime(
                        op.start
                      )} → ${fmtDateTime(op.end)} (${durationMinutes(
                        op.start,
                        op.end
                      )}m)`}
                    >
                      <span className="gantt-bar-text">{op.order_id}</span>
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
            {focusOps.length === 1 ? "" : "s"} across {focusMachines} machine
            {focusMachines === 1 ? "" : "s"}, about {Math.round(focusMinutes)}{" "}
            minutes of work. Click {focus} again to show every order.
          </span>
        ) : (
          <span className="muted">
            Each row is a machine; each bar is an operation it runs, coloured by
            order. Gaps between bars are idle time.{" "}
            <strong>Click an order above</strong> to follow just that order across
            the machines, or hover a bar for details.
          </span>
        )}
      </div>
    </div>
  );
}
