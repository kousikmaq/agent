import React, { useEffect, useState } from 'react'
import { getOverview, getSchedule } from '../api'
import GanttChart from '../components/GanttChart'

export default function SchedulePage({ week, setWeek }) {
  const [weeks, setWeeks] = useState(null)
  const [n, setN] = useState(12)
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    getOverview()
      .then(ov => {
        setWeeks(ov.weeks)
        if (!week) {
          const worst = [...ov.weeks].sort((a, b) => b.bottleneck_util - a.bottleneck_util)[0]
          setWeek(worst.week_start)
        }
      })
      .catch(e => setErr(String(e)))
  }, [])

  useEffect(() => {
    if (!week) return
    setPlan(null); setBusy(true)
    getSchedule(week, n).then(setPlan).catch(e => setErr(String(e))).finally(() => setBusy(false))
  }, [week, n])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')

  return (
    <>
      <div className="pagehead">
        <h1>Schedule Optimization</h1>
        <p>A feasible, near-optimal machine schedule built by a constraint solver (OR-Tools CP-SAT) for the most urgent orders this week.</p>
      </div>

      <div className="weeks">
        {weeks.map(w => (
          <button key={w.week_start}
            className={`weekchip ${w.week_start === week ? 'active' : ''}`}
            onClick={() => setWeek(w.week_start)}>
            <span className={`dot ${statusClass(w.status)}`} />
            {w.week_start.slice(5)}
          </button>
        ))}
      </div>

      <div className="info">
        <b>Scope:</b> to keep the solve fast and the chart readable, the
        {' '}
        <select value={n} onChange={e => setN(Number(e.target.value))} className="nsel">
          {[8, 12, 16, 20].map(v => <option key={v} value={v}>{v}</option>)}
        </select>
        {' '}most urgent orders of the week are scheduled. Every operation respects its routing order and one-job-per-machine.
      </div>

      {busy && <div className="loading">Solving…</div>}

      {plan && !busy && (
        <>
          <div className="grid cards3">
            <div className="card stat">
              <div className="label">Solver result</div>
              <div className="value green">{plan.status}</div>
              <div className="sub">solved in {plan.solve_ms} ms</div>
            </div>
            <div className="card stat">
              <div className="label">Makespan (finish everything)</div>
              <div className="value navy">{plan.makespan_hours} h</div>
              <div className="sub">objective: {plan.objective}</div>
            </div>
            <div className="card stat">
              <div className="label">Orders scheduled</div>
              <div className="value navy">{plan.orders_scheduled}</div>
              <div className="sub">{plan.ops.length} operations · {plan.machines.length} machines</div>
            </div>
          </div>

          <GanttChart plan={plan} />
        </>
      )}
    </>
  )
}
