import { useMemo } from "react";
import type { ScheduledOperation } from "../../types/api";
import { fmtDateTime, durationMinutes } from "../../utils/format";

interface Props {
  operations: ScheduledOperation[];
}

function colourFor(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) % 360;
  return `hsl(${hash}, 62%, 55%)`;
}

/**
 * Timeline of scheduled operations grouped by machine, revealing machine
 * loading and idle gaps across the schedule span.
 */
export function MachineTimeline({ operations }: Props) {
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
      ticks.push({
        fraction: (cursor.getTime() - minT) / spanT,
        label: isMidnight
          ? `${cursor.getMonth() + 1}/${cursor.getDate()}`
          : String(hour % 12 === 0 ? 12 : hour % 12),
        day: isMidnight,
      });
    }
    return { rows, min: minT, span: spanT, ticks };
  }, [operations]);

  if (operations.length === 0) {
    return <p className="empty">No scheduled operations.</p>;
  }

  return (
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
      {rows.map(([machineId, ops]) => (
        <div key={machineId} className="gantt-row">
          <div className="gantt-label" title={machineId}>
            {machineId}
          </div>
          <div className="gantt-track">
            {ops.map((op) => {
              const left =
                ((new Date(op.start).getTime() - min) / span) * 100;
              const width = Math.max(
                0.5,
                ((new Date(op.end).getTime() - new Date(op.start).getTime()) /
                  span) *
                  100
              );
              return (
                <div
                  key={op.operation_id}
                  className="gantt-bar"
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
      ))}
    </div>
  );
}
