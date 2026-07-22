import type { WeeklyDayStatus, WeeklyPlanReport } from "../../types/api";
import { todayIso } from "../../utils/format";

interface Props {
  report: WeeklyPlanReport;
  asOf: string;
  onAsOfChange: (date: string) => void;
}

function statusClass(s: WeeklyDayStatus): string {
  switch (s) {
    case "ON_TRACK":
      return "feas-ok";
    case "AT_RISK":
      return "feas-approve";
    case "BEHIND":
      return "feas-no";
    default:
      return "sev-low";
  }
}

function statusLabel(s: WeeklyDayStatus): string {
  return s.replace("_", " ").toLowerCase();
}

function pct(v: number | null): string {
  return v === null ? "—" : `${Math.round(v * 100)}%`;
}

/** Daily progress: actuals up to "today" vs the weekly plan's daily targets. */
export function DailyProgressPanel({ report, asOf, onAsOfChange }: Props) {
  const overall = report.overall_status;

  return (
    <div className="weekly">
      <div className={`ontrack-banner ${statusClass(overall)}`}>
        <div className="ontrack-headline">
          {overall === "ON_TRACK"
            ? "On track"
            : overall === "AT_RISK"
            ? "At risk"
            : overall === "BEHIND"
            ? "Behind schedule"
            : "Not started"}
        </div>
        <div className="ontrack-sub">
          {report.actual_to_date_operations} of{" "}
          {report.planned_to_date_operations} operations done through{" "}
          {report.as_of_date} · {pct(report.attainment_to_date)} of plan
        </div>
      </div>

      <div className="as-of-row">
        <label>
          Progress as of{" "}
          <select value={asOf} onChange={(e) => onAsOfChange(e.target.value)}>
            {report.days
              .filter((d) => d.date <= todayIso())
              .map((d) => (
                <option key={d.date} value={d.date}>
                  {d.weekday} {d.date}
                </option>
              ))}
          </select>
        </label>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Day</th>
            <th>Planned ops</th>
            <th>Actual ops</th>
            <th>Progress</th>
            <th>Attainment</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {report.days.map((d) => (
            <tr key={d.date} className={d.is_today ? "row-today" : undefined}>
              <td>
                <strong>{d.weekday}</strong> {d.date.slice(5)}
              </td>
              <td>{d.planned_operations}</td>
              <td>{d.actual_operations ?? "—"}</td>
              <td>
                {d.is_past ? (
                  <div className="bar-track">
                    <div
                      className="bar-fill plan"
                      style={{ width: "100%" }}
                    />
                    <div
                      className={`bar-fill actual ${statusClass(d.status)}`}
                      style={{
                        width: `${Math.min(100, (d.attainment ?? 0) * 100)}%`,
                      }}
                    />
                  </div>
                ) : (
                  <span className="muted">future target</span>
                )}
              </td>
              <td>{pct(d.attainment)}</td>
              <td>
                <span className={`badge ${statusClass(d.status)}`}>
                  {statusLabel(d.status)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Actuals for elapsed days are simulated until the live shop-floor feed is
        connected.
      </p>
    </div>
  );
}
