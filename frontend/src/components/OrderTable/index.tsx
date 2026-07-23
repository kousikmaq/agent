import { useMemo, useState } from "react";
import type { ScheduledOperation } from "../../types/api";
import { fmtDateTime } from "../../utils/format";

interface Props {
  operations: ScheduledOperation[];
  /** order_id → raw priority (1 low … 10 high) from the day's snapshot. */
  priorities?: Record<string, number>;
}

interface OrderRow {
  order_id: string;
  operations: number;
  priorityRaw: number | null;
  start: string;
  end: string;
  machines: string[];
}

type SortKey = "order_id" | "operations" | "priority" | "start" | "end";
type SortDir = "asc" | "desc";

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
      const chron = [...ops].sort(
        (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
      );
      return {
        order_id,
        operations: ops.length,
        priorityRaw: priorities?.[order_id] ?? null,
        start: chron[0].start,
        end: chron[chron.length - 1].end,
        machines: Array.from(new Set(ops.map((o) => o.machine_id))).sort(),
      };
    });
  }, [operations, priorities]);

  // 0-based priority rank: the highest raw priority present maps to 0, the next
  // distinct level to 1, and so on — so the column reads 0, 1, 2, …
  const rankOf = useMemo(() => {
    const distinct = Array.from(
      new Set(rows.map((r) => r.priorityRaw).filter((p): p is number => p != null))
    ).sort((a, b) => b - a);
    return new Map(distinct.map((p, i) => [p, i] as const));
  }, [rows]);
  const maxRank = Math.max(1, rankOf.size - 1);

  const displayPriority = (raw: number | null): number | null =>
    raw == null ? null : rankOf.get(raw) ?? null;

  const priorityBadge = (raw: number | null) => {
    const d = displayPriority(raw);
    if (d === null) return <span className="prio-badge prio-low">—</span>;
    // Relative colour: top third = high (red), middle = medium (yellow),
    // bottom third = low (white).
    const cls =
      d <= maxRank / 3
        ? "prio-high"
        : d <= (2 * maxRank) / 3
        ? "prio-med"
        : "prio-low";
    return <span className={`prio-badge ${cls}`}>{d}</span>;
  };

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
          cmp =
            (displayPriority(a.priorityRaw) ?? 999) -
            (displayPriority(b.priorityRaw) ?? 999);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sort, rankOf]);

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
      <div className="prio-legend">
        <span className="prio-legend-item">
          <span className="prio-dot dot-high" /> High
        </span>
        <span className="prio-legend-item">
          <span className="prio-dot dot-med" /> Medium
        </span>
        <span className="prio-legend-item">
          <span className="prio-dot dot-low" /> Low
        </span>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            {header("order_id", "Order")}
            {header("priority", "Priority")}
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
              <td>{priorityBadge(r.priorityRaw)}</td>
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
