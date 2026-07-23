import { useMemo, useState } from "react";
import type {
  DeliveryReport,
  DeliveryStatus,
  ScheduledOperation,
} from "../../types/api";
import { fmtDateTime } from "../../utils/format";

interface Props {
  /** Scheduled operations (the committed plan) for ops / machines / span. */
  operations: ScheduledOperation[];
  /** order_id → raw priority (1 low … 10 high) from the day's snapshot. */
  priorities: Record<string, number>;
  /** Delivery report for status / late / due-date columns (may be null). */
  deliveries: DeliveryReport | null;
  /** Commit the staged per-order priority changes and re-plan the day. */
  onReplan?: (priorities: Record<string, number>) => void;
  /** Whether a re-plan is currently running. */
  replanning?: boolean;
}

interface OrderRow {
  order_id: string;
  priority: number | null;
  status: DeliveryStatus | null;
  tardiness: number;
  due_date: string | null;
  ops: number;
  machines: string[];
  start: string | null;
  end: string | null;
}

type SortKey = "order_id" | "priority" | "status" | "tardiness" | "due_date" | "ops";
type SortDir = "asc" | "desc";

const STATUS_RANK: Record<DeliveryStatus, number> = {
  LATE: 0,
  AT_RISK: 1,
  ON_TRACK: 2,
  UNSCHEDULED: 3,
};

function statusBadge(status: DeliveryStatus | null): string {
  switch (status) {
    case "ON_TRACK":
      return "feas-ok";
    case "AT_RISK":
      return "feas-approve";
    case "LATE":
    case "UNSCHEDULED":
      return "feas-no";
    default:
      return "sev-low";
  }
}

function statusLabel(status: DeliveryStatus | null): string {
  return status ? status.replace("_", " ").toLowerCase() : "—";
}

/** Priorities the user can pick (0 = highest). Stored raw as 10 - level. */
const PRIORITY_CHOICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

/** Convert a raw priority (1 low … 10 high) to the 0-based display (0 = highest). */
const toDisplayPriority = (raw: number | null): number | null =>
  raw == null ? null : Math.max(0, Math.min(9, 10 - raw));

/**
 * Orders workspace — the merged Orders + Deliveries view. Each order shows its
 * priority, delivery status and lateness alongside its scheduled span. Two
 * independent actions: **Raise priority** stages a new priority for the
 * selected orders (reflected immediately), and **Re-plan** commits every staged
 * change in a single re-solve so the whole system stays in sync.
 */
export function OrdersPanel({
  operations,
  priorities,
  deliveries,
  onReplan,
  replanning,
}: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "priority",
    dir: "asc",
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Staged priority overrides (order_id → new raw priority) not yet re-planned.
  const [staged, setStaged] = useState<Record<string, number>>({});
  // The 0-based priority the user will stage (0 = highest).
  const [pickPriority, setPickPriority] = useState<number>(0);

  const deliveryByOrder = useMemo(() => {
    const map = new Map<string, DeliveryReport["lines"][number]>();
    for (const line of deliveries?.lines ?? []) map.set(line.order_id, line);
    return map;
  }, [deliveries]);

  const rows = useMemo<OrderRow[]>(() => {
    const grouped = new Map<string, ScheduledOperation[]>();
    for (const op of operations) {
      const list = grouped.get(op.order_id) ?? [];
      list.push(op);
      grouped.set(op.order_id, list);
    }
    // Union of scheduled orders and delivery-line orders.
    const ids = new Set<string>([
      ...grouped.keys(),
      ...deliveryByOrder.keys(),
      ...Object.keys(priorities),
    ]);
    return Array.from(ids).map((order_id) => {
      const ops = grouped.get(order_id) ?? [];
      const chron = [...ops].sort(
        (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
      );
      const line = deliveryByOrder.get(order_id);
      return {
        order_id,
        priority: staged[order_id] ?? priorities[order_id] ?? line?.priority ?? null,
        status: line?.status ?? null,
        tardiness: line?.tardiness_minutes ?? 0,
        due_date: line?.due_date ?? null,
        ops: ops.length,
        machines: Array.from(new Set(ops.map((o) => o.machine_id))).sort(),
        start: chron.length ? chron[0].start : null,
        end: chron.length ? chron[chron.length - 1].end : null,
      };
    });
  }, [operations, priorities, deliveryByOrder, staged]);

  const sorted = useMemo(() => {
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      let cmp = 0;
      switch (sort.key) {
        case "order_id":
          cmp = a.order_id.localeCompare(b.order_id);
          break;
        case "priority":
          cmp =
            (toDisplayPriority(a.priority) ?? 999) -
            (toDisplayPriority(b.priority) ?? 999);
          break;
        case "status":
          cmp =
            (a.status ? STATUS_RANK[a.status] : 9) -
            (b.status ? STATUS_RANK[b.status] : 9);
          break;
        case "tardiness":
          cmp = a.tardiness - b.tardiness;
          break;
        case "due_date":
          cmp = (a.due_date ?? "").localeCompare(b.due_date ?? "");
          break;
        case "ops":
          cmp = a.ops - b.ops;
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
        : { key, dir: key === "order_id" ? "asc" : "desc" }
    );
  const caret = (key: SortKey) =>
    sort.key === key ? (
      <span className="sort-caret">{sort.dir === "asc" ? "▲" : "▼"}</span>
    ) : null;

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.order_id));
  const toggleAll = () =>
    setSelected(() => {
      if (allSelected) return new Set();
      return new Set(rows.map((r) => r.order_id));
    });

  // Stage the chosen priority for the selected orders (raise OR lower).
  const applyPriorityToSelected = () => {
    if (selected.size === 0) return;
    const raw = Math.max(1, Math.min(10, 10 - pickPriority));
    setStaged((prev) => {
      const next = { ...prev };
      for (const id of selected) next[id] = raw;
      return next;
    });
  };

  const clearStaged = () => setStaged({});

  const stagedCount = Object.keys(staged).length;
  const isStaged = (id: string) => staged[id] !== undefined;

  return (
    <div className="panel-list">
      {deliveries && (
        <div className="severity-summary">
          <span className="badge feas-ok">On track: {deliveries.on_track}</span>
          <span className="badge feas-approve">At risk: {deliveries.at_risk}</span>
          <span className="badge feas-no">Late: {deliveries.late}</span>
          <span className="badge sev-low">
            Unscheduled: {deliveries.unscheduled}
          </span>
          <span className="muted">Orders: {rows.length}</span>
        </div>
      )}

      {/* Two independent actions: stage a priority, then re-plan. */}
      <div className="risk-bulkbar">
        <span className="risk-bulkbar-count">
          {selected.size > 0
            ? `${selected.size} order${selected.size > 1 ? "s" : ""} selected`
            : "Select orders to change their priority"}
        </span>
        <div className="risk-bulkbar-actions orders-actions">
          <label className="orders-prio-pick">
            New priority
            <select
              value={pickPriority}
              onChange={(e) => setPickPriority(Number(e.target.value))}
            >
              {PRIORITY_CHOICES.map((p) => (
                <option key={p} value={p}>
                  {p}
                  {p === 0 ? " (highest)" : p === 9 ? " (lowest)" : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={selected.size === 0}
            onClick={applyPriorityToSelected}
            title="Stage this priority for the selected orders"
          >
            Raise / set priority ({selected.size})
          </button>
          <button
            type="button"
            className="primary"
            disabled={stagedCount === 0 || replanning}
            onClick={() => onReplan?.(staged)}
            title="Re-solve the day with the staged priorities"
          >
            {replanning ? "Re-planning…" : `Re-plan (${stagedCount})`}
          </button>
          {stagedCount > 0 && !replanning && (
            <button type="button" onClick={clearStaged} title="Discard staged changes">
              Clear staged
            </button>
          )}
        </div>
      </div>

      <table className="data-table orders-table">
        <thead>
          <tr>
            <th className="col-check">
              <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            </th>
            <th className="sortable" onClick={() => onSort("order_id")}>
              Order {caret("order_id")}
            </th>
            <th className="sortable" onClick={() => onSort("priority")}>
              Priority {caret("priority")}
            </th>
            <th className="sortable" onClick={() => onSort("status")}>
              Status {caret("status")}
            </th>
            <th className="sortable" onClick={() => onSort("tardiness")}>
              Late {caret("tardiness")}
            </th>
            <th className="sortable" onClick={() => onSort("due_date")}>
              Due {caret("due_date")}
            </th>
            <th className="sortable" onClick={() => onSort("ops")}>
              Ops {caret("ops")}
            </th>
            <th>Machines</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.order_id} className={isStaged(r.order_id) ? "row-staged" : ""}>
              <td className="col-check">
                <input
                  type="checkbox"
                  checked={selected.has(r.order_id)}
                  onChange={() => toggle(r.order_id)}
                />
              </td>
              <td>{r.order_id}</td>
              <td>
                <span className="prio-badge prio-med">
                  {toDisplayPriority(r.priority) ?? "—"}
                </span>
                {isStaged(r.order_id) && (
                  <span className="staged-tag" title="Staged, not yet re-planned">
                    staged
                  </span>
                )}
              </td>
              <td>
                <span className={`badge ${statusBadge(r.status)}`}>
                  {statusLabel(r.status)}
                </span>
              </td>
              <td>
                {r.tardiness > 0 ? (
                  <span className="kpi-worse">
                    {Math.round(r.tardiness / 60)}h late
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>{r.due_date ?? <span className="muted">—</span>}</td>
              <td>{r.ops}</td>
              <td className="machines-cell">
                {r.start ? (
                  <span title={`${fmtDateTime(r.start)} → ${fmtDateTime(r.end!)}`}>
                    {r.machines.join(", ")}
                  </span>
                ) : (
                  <span className="muted">not scheduled</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="panel-note">
        Priority: 0 = highest, 9 = lowest. Staging a priority does not change
        the plan until you press <strong>Re-plan</strong>.
      </p>
    </div>
  );
}
