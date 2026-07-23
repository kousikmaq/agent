import { useMemo, useState } from "react";
import type { ScheduledOperation } from "../../types/api";
import { fmtDateTime } from "../../utils/format";

interface Props {
  operations: ScheduledOperation[];
  /** order_id → raw priority (1 low … 10 high) from the day's snapshot. */
  priorities?: Record<string, number>;
}

// Backend priority is 1..10 (10 = highest). We show it on a 0-based scale where
// 0 = highest priority (per product decision), i.e. display = MAX - raw.
const MAX_PRIORITY = 10;

interface OrderRow {
  order_id: string;
  operations: number;
  priority: number | null;
  start: string;
  end: string;
  machines: string[];
}

type SortKey = "order_id" | "operations" | "priority" | "start" | "end";
type SortDir = "asc" | "desc";

function priorityBadge(p: number | null) {
  if (p === null) return <span className="prio-badge prio-low">—</span>;
  // p is the 0-based display priority: 0 = highest/most urgent → red.
  const cls = p <= 2 ? "prio-high" : p <= 5 ? "prio-med" : "prio-low";
  return <span className={`prio-badge ${cls}`}>{p}</span>;
}

/** Tabular view of scheduled orders: priority, span, ops, machines — sortable. */
export function OrderTable({ operations, priorities }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "priority",
    dir: "asc",
  });

  const rows = useMemo<OrderRow[]>(() => {
    const grouped = new Map<string, ScheduledOperation[]>();
    for (const op of operations) {
      const list = grouped.get(op.order_id) ?? [];
      list.push(op);
      grouped.set(op.order_id, list);
    }
    return Array.from(grouped.entries()).map(([order_id, ops]) => {
      const sorted = [...ops].sort(
        (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
      );
      const raw = priorities?.[order_id];
      return {
        order_id,
        operations: ops.length,
        priority: raw != null ? MAX_PRIORITY - raw : null,
        start: sorted[0].start,
        end: sorted[sorted.length - 1].end,
        machines: Array.from(new Set(ops.map((o) => o.machine_id))).sort(),
      };
    });
  }, [operations, priorities]);

  const sorted = useMemo(() => {
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      let cmp = 0;
      switch (sort.key) {
        case "order_id":
          cmp = a.order_id.localeCompare(b.order_id);
          break;
        case "operations":
          cmp = a.operations - b.operations;
          break;
        case "priority":
          cmp = (a.priority ?? 999) - (b.priority ?? 999);
          break;
        case "start":
          cmp = new Date(a.start).getTime() - new Date(b.start).getTime();
          break;
        case "end":
          cmp = new Date(a.end).getTime() - new Date(b.end).getTime();
          break;
      }
      return cmp * dir;
    });
  }, [rows, sort]);

  if (rows.length === 0) {
    return <p className="empty">No scheduled orders.</p>;
  }

  const onSort = (key: SortKey) =>
    setSort((cur) =>
      cur.key === key
        ? { key, dir: cur.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" }
    );

  const caret = (key: SortKey) =>
    sort.key === key ? (
      <span className="sort-caret">{sort.dir === "asc" ? "▲" : "▼"}</span>
    ) : (
      <span className="sort-caret">↕</span>
    );

  const header = (key: SortKey, label: string) => (
    <th className="sortable" onClick={() => onSort(key)} title={`Sort by ${label}`}>
      {label}
      {caret(key)}
    </th>
  );

  return (
    <div>
      <p className="table-hint">
        <span className="prio-badge prio-high">0</span> = highest priority (most
        urgent); higher numbers mean lower priority.
      </p>
      <table className="data-table">
        <thead>
          <tr>
            {header("order_id", "Order")}
            <th
              className="sortable"
              onClick={() => onSort("priority")}
              title="Sort by priority (0 = highest)"
            >
              Priority
              {caret("priority")}
            </th>
            {header("operations", "Ops")}
            {header("start", "Start")}
            {header("end", "End")}
            <th>Machines</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.order_id}>
              <td>{r.order_id}</td>
              <td>{priorityBadge(r.priority)}</td>
              <td>{r.operations}</td>
              <td>{fmtDateTime(r.start)}</td>
              <td>{fmtDateTime(r.end)}</td>
              <td>{r.machines.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
