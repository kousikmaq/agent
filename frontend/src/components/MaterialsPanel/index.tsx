import { useEffect, useMemo, useState } from "react";
import type { MaterialLine, MaterialsReport, PurchaseOrder } from "../../types/api";
import { api, ApiError } from "../../api/client";
import { ActionButton } from "../ActionButton";
import { toast } from "../Toast";
import { fmtDateTime } from "../../utils/format";

interface Props {
  report: MaterialsReport;
  /** Business date, used to load/place this day's purchase orders. */
  date: string;
}

type SortKey =
  | "product_id"
  | "on_hand"
  | "net_available"
  | "reorder_point"
  | "safety_stock"
  | "shortage"
  | "status";
type SortDir = "asc" | "desc";

// Higher = more critical, used for the status sort.
function statusRank(m: MaterialLine): number {
  if (m.below_safety) return 2;
  if (m.below_reorder) return 1;
  return 0;
}

function statusBadge(m: MaterialLine): { cls: string; label: string } {
  if (m.below_safety) return { cls: "feas-no", label: "below safety" };
  if (m.below_reorder) return { cls: "feas-approve", label: "below reorder" };
  return { cls: "feas-ok", label: "ok" };
}

const fmt = (v: number) =>
  Number.isInteger(v) ? String(v) : v.toFixed(1);

/**
 * Materials availability board: on-hand / allocated / net available and any
 * shortage against reorder / safety, sortable by column. Any material can be
 * replenished directly with a place-order email — the same action offered for
 * material-shortage risks, kept consistent per selected material.
 */
export function MaterialsPanel({ report, date }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "status",
    dir: "desc",
  });
  // Latest purchase order per material for the day (product_id -> PO).
  const [pos, setPos] = useState<Record<string, PurchaseOrder>>({});
  useEffect(() => {
    let active = true;
    api
      .getPurchaseOrders(date)
      .then((list) => {
        if (!active) return;
        const map: Record<string, PurchaseOrder> = {};
        for (const po of list) map[po.product_id] = po; // appended in order: last wins
        setPos(map);
      })
      .catch(() => {
        if (active) setPos({});
      });
    return () => {
      active = false;
    };
  }, [date]);

  const sorted = useMemo(() => {
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...report.lines].sort((a, b) => {
      let cmp = 0;
      switch (sort.key) {
        case "product_id":
          cmp = a.product_id.localeCompare(b.product_id);
          break;
        case "on_hand":
          cmp = a.on_hand - b.on_hand;
          break;
        case "net_available":
          cmp = a.net_available - b.net_available;
          break;
        case "reorder_point":
          cmp = a.reorder_point - b.reorder_point;
          break;
        case "safety_stock":
          cmp = a.safety_stock - b.safety_stock;
          break;
        case "shortage":
          cmp = a.shortage - b.shortage;
          break;
        case "status":
          cmp = statusRank(a) - statusRank(b);
          break;
      }
      return cmp * dir;
    });
  }, [report.lines, sort]);

  const onSort = (key: SortKey) =>
    setSort((cur) =>
      cur.key === key
        ? { key, dir: cur.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "product_id" ? "asc" : "desc" }
    );
  const caret = (key: SortKey) =>
    sort.key === key ? (
      <span className="sort-caret">{sort.dir === "asc" ? "▲" : "▼"}</span>
    ) : null;

  const placeOrder = async (m: MaterialLine) => {
    const reason = m.below_safety
      ? `${m.product_id} is below safety stock (net ${fmt(m.net_available)}, ` +
        `safety ${fmt(m.safety_stock)}).`
      : m.below_reorder
      ? `${m.product_id} is below its reorder point (net ${fmt(m.net_available)}, ` +
        `reorder ${fmt(m.reorder_point)}).`
      : `Replenishment for ${m.product_id}.`;
    const qty = m.shortage > 0 ? Math.ceil(m.shortage) : undefined;
    try {
      const po = await api.reorderMaterial(date, m.product_id, qty, reason);
      setPos((prev) => ({ ...prev, [po.product_id]: po }));
      toast(`Purchase order for ${m.product_id} placed (${po.email_status}).`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Failed to place order", "error");
      throw e;
    }
  };

  if (report.total === 0) {
    return <p className="empty">No materials tracked for this day.</p>;
  }

  // Mutually-exclusive counts that match the Status column: a material below
  // safety is shown as "below safety" (not also counted under "below reorder").
  const belowSafetyCount = report.lines.filter((l) => l.below_safety).length;
  const belowReorderOnly = report.lines.filter(
    (l) => l.below_reorder && !l.below_safety
  ).length;

  return (
    <div className="panel-list">
      <div className="severity-summary">
        <span className="badge feas-no">Below safety: {belowSafetyCount}</span>
        <span className="badge feas-approve">
          Below reorder: {belowReorderOnly}
        </span>
        <span className="muted">Materials tracked: {report.total}</span>
      </div>

      <table className="data-table materials-table">
        <thead>
          <tr>
            <th className="sortable" onClick={() => onSort("product_id")}>
              Material {caret("product_id")}
            </th>
            <th className="sortable" onClick={() => onSort("on_hand")}>
              On hand {caret("on_hand")}
            </th>
            <th>Allocated</th>
            <th className="sortable" onClick={() => onSort("net_available")}>
              Net available {caret("net_available")}
            </th>
            <th className="sortable" onClick={() => onSort("reorder_point")}>
              Reorder {caret("reorder_point")}
            </th>
            <th className="sortable" onClick={() => onSort("safety_stock")}>
              Safety {caret("safety_stock")}
            </th>
            <th className="sortable" onClick={() => onSort("shortage")}>
              Shortage {caret("shortage")}
            </th>
            <th className="sortable" onClick={() => onSort("status")}>
              Status {caret("status")}
            </th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => {
            const badge = statusBadge(m);
            return (
              <tr key={m.product_id}>
                <td>
                  <strong>{m.product_id}</strong>
                  {m.name && <div className="muted mat-name">{m.name}</div>}
                </td>
                <td>{fmt(m.on_hand)}</td>
                <td>{fmt(m.allocated)}</td>
                <td>{fmt(m.net_available)}</td>
                <td>{fmt(m.reorder_point)}</td>
                <td>{fmt(m.safety_stock)}</td>
                <td>
                  {m.shortage > 0 ? (
                    <span className="kpi-worse">{fmt(m.shortage)}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <span className={`badge ${badge.cls}`}>{badge.label}</span>
                </td>
                <td>
                  {pos[m.product_id] ? (
                    <div className="mat-po">
                      <span
                        className="badge badge-ordered"
                        title={`${
                          pos[m.product_id].mode === "auto" ? "Auto" : "Manually"
                        }-placed purchase order`}
                      >
                        ✅ Ordered {fmt(pos[m.product_id].quantity)}
                        {pos[m.product_id].mode === "auto" ? " · auto" : " · manual"}
                      </span>
                      <span className="mat-po-time">
                        at {fmtDateTime(pos[m.product_id].placed_at)}
                      </span>
                      <ActionButton
                        icon="✉"
                        label="Order again"
                        pendingLabel="Ordering…"
                        successLabel="Ordered"
                        onAction={() => placeOrder(m)}
                      />
                    </div>
                  ) : m.below_safety || m.below_reorder ? (
                    <ActionButton
                      icon="✉"
                      label="Place order"
                      pendingLabel="Ordering…"
                      successLabel="Ordered"
                      onAction={() => placeOrder(m)}
                    />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="panel-note">
        Place order emails a purchase-order request and records it for the day.
        Materials below safety stock or their reorder point can be ordered
        automatically once per day; each row shows what was ordered and when,
        and you can Order again if needed.
      </p>
    </div>
  );
}
