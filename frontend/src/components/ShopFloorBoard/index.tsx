import { useState } from "react";
import type { RiskReport, ShopFloorStatus } from "../../types/api";
import { RiskPanel } from "../RiskPanel";

interface Props {
  status: ShopFloorStatus;
  risks?: RiskReport | null;
  /** Redirect to the Materials tab on the planning page. */
  onViewMaterials?: () => void;
}

type DetailKey = "machines" | "workers" | "orders" | "materials" | "risks";

interface Stat {
  label: string;
  value: number;
  tone?: "good" | "warn" | "bad" | "neutral";
}

function StatCard({
  title,
  stats,
  active,
  hint,
  onClick,
}: {
  title: string;
  stats: Stat[];
  active: boolean;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`floor-card${active ? " active" : ""}`}
      onClick={onClick}
    >
      <div className="floor-card-title">{title}</div>
      <div className="floor-stats">
        {stats.map((s) => (
          <div key={s.label} className={`floor-stat tone-${s.tone ?? "neutral"}`}>
            <span className="floor-stat-value">{s.value}</span>
            <span className="floor-stat-label">{s.label}</span>
          </div>
        ))}
      </div>
      <span className="floor-card-hint">{hint} →</span>
    </button>
  );
}

/** Live shop-floor status: machines, workers, orders, materials, risks. */
export function ShopFloorBoard({ status, risks, onViewMaterials }: Props) {
  const [detail, setDetail] = useState<DetailKey>("machines");

  return (
    <div className="floor">
      <div className="floor-grid">
        <StatCard
          title="Machines"
          active={detail === "machines"}
          hint="View machines needing attention"
          onClick={() => setDetail("machines")}
          stats={[
            { label: "Available", value: status.machine_available, tone: "good" },
            { label: "Running", value: status.machine_running, tone: "neutral" },
            { label: "Idle", value: status.machine_idle, tone: "neutral" },
            { label: "Down", value: status.machine_down, tone: "bad" },
            { label: "Maintenance", value: status.machine_maintenance, tone: "warn" },
          ]}
        />
        <StatCard
          title="Workers"
          active={detail === "workers"}
          hint="View workforce"
          onClick={() => setDetail("workers")}
          stats={[
            { label: "Available", value: status.worker_available, tone: "good" },
            { label: "Unavailable", value: status.worker_unavailable, tone: "warn" },
            { label: "Total", value: status.worker_total, tone: "neutral" },
          ]}
        />
        <StatCard
          title="Orders"
          active={detail === "orders"}
          hint="View order breakdown"
          onClick={() => setDetail("orders")}
          stats={[
            { label: "In progress", value: status.orders_in_progress, tone: "neutral" },
            { label: "Released", value: status.orders_released, tone: "neutral" },
            { label: "Planned", value: status.orders_planned, tone: "neutral" },
            { label: "Completed", value: status.orders_completed, tone: "good" },
            { label: "Cancelled", value: status.orders_cancelled, tone: "warn" },
          ]}
        />
        <StatCard
          title="Materials"
          active={detail === "materials"}
          hint="View materials running low"
          onClick={() =>
            onViewMaterials ? onViewMaterials() : setDetail("materials")
          }
          stats={[
            { label: "Below reorder", value: status.materials_below_reorder, tone: "warn" },
            { label: "Below safety", value: status.materials_below_safety, tone: "bad" },
          ]}
        />
        <StatCard
          title="Risks"
          active={detail === "risks"}
          hint="View risk details"
          onClick={() => setDetail("risks")}
          stats={[
            { label: "Open", value: status.open_risks, tone: status.open_risks ? "warn" : "good" },
            { label: "Critical", value: status.critical_risks, tone: status.critical_risks ? "bad" : "good" },
          ]}
        />
      </div>

      <div className="floor-detail">
        {detail === "machines" && (
          <div className="panel-list">
            <div className="list-item-head">
              <span className="list-item-title">Machines needing attention</span>
            </div>
            {status.machines_attention.length === 0 ? (
              <p className="muted">All machines operational.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Machine</th>
                    <th>Work center</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {status.machines_attention.map((m) => (
                    <tr key={m.machine_id}>
                      <td>{m.machine_id} · {m.name}</td>
                      <td>{m.work_center}</td>
                      <td>
                        <span
                          className={`badge ${
                            m.status === "DOWN" ? "feas-no" : "feas-approve"
                          }`}
                        >
                          {m.status.toLowerCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {detail === "workers" && (
          <div className="panel-list">
            <div className="list-item-head">
              <span className="list-item-title">Workforce</span>
            </div>
            <p className="muted">
              {status.worker_available} of {status.worker_total} workers available;{" "}
              {status.worker_unavailable} unavailable (leave / off-shift).
            </p>
          </div>
        )}

        {detail === "orders" && (
          <div className="panel-list">
            <div className="list-item-head">
              <span className="list-item-title">Order status breakdown</span>
            </div>
            <table className="data-table">
              <tbody>
                <tr>
                  <td>In progress</td>
                  <td>{status.orders_in_progress}</td>
                </tr>
                <tr>
                  <td>Released</td>
                  <td>{status.orders_released}</td>
                </tr>
                <tr>
                  <td>Planned</td>
                  <td>{status.orders_planned}</td>
                </tr>
                <tr>
                  <td>Completed</td>
                  <td>{status.orders_completed}</td>
                </tr>
                <tr>
                  <td>Cancelled</td>
                  <td>{status.orders_cancelled}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {detail === "materials" && (
          <div className="panel-list">
            <div className="list-item-head">
              <span className="list-item-title">Materials running low</span>
            </div>
            {status.materials_attention.length === 0 ? (
              <p className="muted">All materials above thresholds.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Material</th>
                    <th>Net available</th>
                    <th>Safety</th>
                    <th>Flag</th>
                  </tr>
                </thead>
                <tbody>
                  {status.materials_attention.map((m) => (
                    <tr key={m.product_id}>
                      <td>{m.product_id}</td>
                      <td>{m.net_available}</td>
                      <td>{m.safety_stock}</td>
                      <td>
                        <span
                          className={`badge ${m.below_safety ? "feas-no" : "feas-approve"}`}
                        >
                          {m.below_safety ? "below safety" : "below reorder"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {detail === "risks" && (
          <div className="panel-list">
            <div className="list-item-head">
              <span className="list-item-title">Detected risks</span>
            </div>
            {risks ? (
              <RiskPanel report={risks} />
            ) : (
              <p className="muted">
                No risk report for this day yet — run the planner on the Planning
                page to detect risks.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
