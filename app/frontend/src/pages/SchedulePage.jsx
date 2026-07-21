import React, { useEffect, useRef, useState } from 'react'
import { getOverview, getSchedule } from '../api'
import GanttChart from '../components/GanttChart'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

const STEPS = [
  'Reading routings & due dates…',
  'Building precedence constraints…',
  'Adding one-job-per-machine rules…',
  'Searching for the shortest makespan…',
  'Finalising the schedule…',
]

export default function SchedulePage({ week, setWeek, navigate }) {
  const [weeks, setWeeks] = useState(null)
  const [n, setN] = useState(12)
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(0)
  const [fresh, setFresh] = useState(false)     // triggers gantt fade-in animation
  const [highlight, setHighlight] = useState(null)
  const [err, setErr] = useState(null)
  const stepTimer = useRef(null)

  useEffect(() => {
    getOverview()
      .then(ov => {
        setWeeks(ov.weeks)
        if (!week) {
          const current = [...ov.weeks].sort((a, b) => a.week_start.localeCompare(b.week_start))[0]
          setWeek(current.week_start)
        }
      })
      .catch(e => setErr(String(e)))
  }, [])

  function optimize() {
    if (!week || busy) return
    setBusy(true); setPlan(null); setHighlight(null); setStep(0)
    // animate the solver steps while we wait
    stepTimer.current = setInterval(() => setStep(s => Math.min(s + 1, STEPS.length - 1)), 380)
    getSchedule(week, n)
      .then(p => { setPlan(p); setFresh(true); setTimeout(() => setFresh(false), 900) })
      .catch(e => setErr(String(e)))
      .finally(() => { clearInterval(stepTimer.current); setBusy(false) })
  }

  // auto-optimise once when the week changes, so the page is never empty
  useEffect(() => {
    if (!week) return
    optimize()
    return () => clearInterval(stepTimer.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  return (
    <>
      <div className="pagehead">
        <h1>Schedule Optimization</h1>
        <p>A feasible, near-optimal machine schedule built by a constraint solver (OR-Tools CP-SAT) for the most urgent orders this week.</p>
      </div>

      <HelpBox title="New here? How to read the Gantt schedule">
        <ul>
          <li>The <b>Gantt chart</b> is a timeline. <b>Rows are machines</b>; <b>left → right is time</b> (hours from the start of the plan).</li>
          <li>Each coloured block is one <b>operation</b>; blocks of the same colour belong to the same order as it moves machine to machine.</li>
          <li>Blocks on a row never overlap — a machine runs <b>one job at a time</b>. An order's operations always follow its routing order.</li>
          <li><b>Makespan</b> is when the last block finishes — the solver's goal is to make this as small as possible.</li>
          <li>Change the <b>scope</b> and press <b>Optimize</b> to re-solve. Click any block to focus one order.</li>
        </ul>
      </HelpBox>

      <WeekBar weeks={weeks} week={week} setWeek={setWeek} />

      <div className="card" style={{ marginTop: 4 }}>
        <div className="customizer">
          <label>
            Orders to schedule
            <InfoTip text="The most urgent N orders of the week are scheduled. Fewer orders solve faster and read more clearly; more orders give a fuller plan." />
            <input type="range" min={6} max={24} step={2} value={n} disabled={busy}
              onChange={e => setN(Number(e.target.value))} />
            <span className="cv">{n}</span>
          </label>
          <button className="btn-primary" onClick={optimize} disabled={busy}>
            {busy ? 'Optimizing…' : '⚙ Optimize schedule'}
          </button>
        </div>
      </div>

      {busy && (
        <div className="solving">
          <div className="spinner" />
          <div className="solving-steps">
            {STEPS.map((s, i) => (
              <div key={i} className={`step ${i < step ? 'done' : i === step ? 'active' : ''}`}>
                {i < step ? '✓ ' : i === step ? '▸ ' : '· '}{s}
              </div>
            ))}
          </div>
        </div>
      )}

      {plan && !busy && (
        <>
          <div className="grid cards3">
            <div className="card stat">
              <div className="label">Solver result <InfoTip text="OPTIMAL = provably shortest. FEASIBLE = a valid schedule found within the time limit." /></div>
              <div className="value green">{plan.status}</div>
              <div className="sub">solved in {plan.solve_ms} ms</div>
            </div>
            <div className="card stat">
              <div className="label">Makespan <InfoTip text="Total time from start until the very last operation finishes." /></div>
              <div className="value navy">{plan.makespan_hours} h</div>
              <div className="sub">objective: {plan.objective}</div>
            </div>
            <div className="card stat">
              <div className="label">Orders scheduled</div>
              <div className="value navy">{plan.orders_scheduled}</div>
              <div className="sub">{plan.ops.length} operations · {plan.machines.length} machines</div>
            </div>
          </div>

          {plan.ops.length === 0
            ? <div className="info">No orders due this week, so there is nothing to schedule. Pick another week above.</div>
            : <GanttChart plan={plan} animate={fresh} highlight={highlight} onSelectOrder={setHighlight} />}

          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button className="btn-ghost" onClick={() => navigate('priority', week)}>← See which orders are most urgent</button>
            <button className="btn-ghost" onClick={() => navigate('capacity', week)}>Check capacity for this week</button>
          </div>
        </>
      )}
    </>
  )
}
