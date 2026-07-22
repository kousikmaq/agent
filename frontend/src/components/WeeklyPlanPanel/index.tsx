import type { WeeklyPlanReport } from "../../types/api";

interface Props {
  report: WeeklyPlanReport;
}

function hours(minutes: number): string {
  return `${Math.round(minutes / 60)}h`;
}

/** Weekly plan: the week's total workload broken into per-day targets. */
export function WeeklyPlanPanel({ report }: Props) {
  const maxOps = Math.max(1, ...report.days.map((d) => d.planned_operations));

  return (
    <div className="weekly">
      <p className="muted">
        Week <strong>{report.week_start}</strong> → <strong>{report.week_end}</strong>.
        The plan below is the target workload for each day.
      </p>

      <div className={`cadence-banner${report.update_due ? " due" : ""}`}>
        {report.update_due ? (
          <>
            <strong>Weekly plan update due.</strong> It's Saturday ({report.next_update_on})
            — review this week and set next week's plan.
          </>
        ) : (
          <>
            Plan set on <strong>Sat {report.plan_set_on}</strong>. Updated every
            Saturday — next update <strong>Sat {report.next_update_on}</strong>.
          </>
        )}
      </div>

      <div className="kpi-grid">
        <div className="kpi-card tone-neutral">
          <div className="kpi-value">{report.planned_units}</div>
          <div className="kpi-label">Units to produce</div>
        </div>
        <div className="kpi-card tone-neutral">
          <div className="kpi-value">{report.planned_orders}</div>
          <div className="kpi-label">Orders to complete</div>
        </div>
        <div className="kpi-card tone-neutral">
          <div className="kpi-value">{report.planned_operations}</div>
          <div className="kpi-label">Operations</div>
        </div>
        <div className="kpi-card tone-neutral">
          <div className="kpi-value">{hours(report.planned_minutes)}</div>
          <div className="kpi-label">Work hours</div>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Day</th>
            <th>Target workload</th>
            <th>Operations</th>
            <th>Orders due</th>
            <th>Units</th>
            <th>Hours</th>
          </tr>
        </thead>
        <tbody>
          {report.days.map((d) => (
            <tr key={d.date} className={d.is_today ? "row-today" : undefined}>
              <td>
                <strong>{d.weekday}</strong> {d.date.slice(5)}
                {d.is_today && <span className="muted"> · today</span>}
              </td>
              <td>
                <div className="bar-track">
                  <div
                    className="bar-fill plan"
                    style={{ width: `${(d.planned_operations / maxOps) * 100}%` }}
                  />
                </div>
              </td>
              <td>{d.planned_operations}</td>
              <td>{d.planned_orders}</td>
              <td>{d.planned_units}</td>
              <td>{hours(d.planned_minutes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
