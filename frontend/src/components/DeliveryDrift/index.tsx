import type { DeliveryDriftReport, DriftTrend } from "../../types/api";

interface Props {
  report: DeliveryDriftReport;
}

function trendClass(t: DriftTrend): string {
  switch (t) {
    case "SLIPPING":
      return "feas-no";
    case "IMPROVING":
      return "feas-ok";
    case "NEW":
      return "prio";
    default:
      return "sev-low";
  }
}

function deltaLabel(minutes: number | null): string {
  if (minutes === null) return "—";
  const hours = minutes / 60;
  const sign = minutes > 0 ? "+" : "";
  return `${sign}${hours.toFixed(1)}h`;
}

/** Commitment drift: how each order moved versus the previous day's plan. */
export function DeliveryDrift({ report }: Props) {
  if (report.previous_date === null) {
    return (
      <p className="empty">
        No previous plan to compare against yet — drift appears once a prior day
        has been planned.
      </p>
    );
  }

  return (
    <div className="panel-list">
      <p className="muted">
        Comparing <strong>{report.business_date}</strong> plan vs{" "}
        <strong>{report.previous_date}</strong>.
      </p>
      <div className="kpi-grid">
        <div className="kpi-card tone-bad">
          <div className="kpi-value">{report.slipping}</div>
          <div className="kpi-label">Slipping later</div>
        </div>
        <div className="kpi-card tone-good">
          <div className="kpi-value">{report.improving}</div>
          <div className="kpi-label">Improving</div>
        </div>
        <div className="kpi-card tone-neutral">
          <div className="kpi-value">{report.stable}</div>
          <div className="kpi-label">Stable</div>
        </div>
        <div className="kpi-card tone-neutral">
          <div className="kpi-value">{report.new}</div>
          <div className="kpi-label">New</div>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Order</th>
            <th>Due</th>
            <th>Change vs prev</th>
            <th>Trend</th>
          </tr>
        </thead>
        <tbody>
          {report.lines.map((ln) => (
            <tr key={ln.order_id}>
              <td>{ln.order_id}</td>
              <td>{ln.due_date}</td>
              <td>
                <span
                  className={`delta ${
                    (ln.delta_minutes ?? 0) > 0 ? "up" : "down"
                  }`}
                >
                  {deltaLabel(ln.delta_minutes)}
                </span>
              </td>
              <td>
                <span className={`badge ${trendClass(ln.trend)}`}>
                  {ln.trend.toLowerCase()}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
