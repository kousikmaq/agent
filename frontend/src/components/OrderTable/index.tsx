import { useMemo } from "react";
import type { ScheduledOperation } from "../../types/api";
import { fmtDateTime } from "../../utils/format";

interface Props {
  operations: ScheduledOperation[];
}

interface OrderRow {
  order_id: string;
  operations: number;
  start: string;
  end: string;
  machines: string[];
}

/** Tabular view of scheduled orders: span, operation count, machines used. */
export function OrderTable({ operations }: Props) {
  const rows = useMemo<OrderRow[]>(() => {
    const grouped = new Map<string, ScheduledOperation[]>();
    for (const op of operations) {
      const list = grouped.get(op.order_id) ?? [];
      list.push(op);
      grouped.set(op.order_id, list);
    }
    return Array.from(grouped.entries())
      .map(([order_id, ops]) => {
        const sorted = [...ops].sort(
          (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
        );
        return {
          order_id,
          operations: ops.length,
          start: sorted[0].start,
          end: sorted[sorted.length - 1].end,
          machines: Array.from(new Set(ops.map((o) => o.machine_id))).sort(),
        };
      })
      .sort((a, b) => a.order_id.localeCompare(b.order_id));
  }, [operations]);

  if (rows.length === 0) {
    return <p className="empty">No scheduled orders.</p>;
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Order</th>
          <th>Ops</th>
          <th>Start</th>
          <th>End</th>
          <th>Machines</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.order_id}>
            <td>{r.order_id}</td>
            <td>{r.operations}</td>
            <td>{fmtDateTime(r.start)}</td>
            <td>{fmtDateTime(r.end)}</td>
            <td>{r.machines.join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
