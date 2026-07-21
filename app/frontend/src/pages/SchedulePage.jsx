import React, { useEffect, useRef, useState } from 'react'
import { getOverview, getSchedule } from '../api'
import GanttChart from '../components/GanttChart'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'
import RecommendationList from '../components/RecommendationList'

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
  const [appliedN, setAppliedN] = useState(12)
  const [plan, setPlan] = useState(null)
  const [prevMakespan, setPrevMakespan] = useState(null)
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
    setPrevMakespan(plan ? plan.makespan_hours : null)
    setBusy(true); setPlan(null); setHighlight(null); setStep(0)
    // animate the solver steps while we wait
    stepTimer.current = setInterval(() => setStep(s => Math.min(s + 1, STEPS.length - 1)), 380)
    getSchedule(week, n)
      .then(p => { setPlan(p); setAppliedN(n); setFresh(true); setTimeout(() => setFresh(false), 900) })
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
          <button className="btn-primary" onClick={optimize} disabled={busy || (plan && n === appliedN)}>
            {busy ? 'Optimizing…' : '⚙ Optimize schedule'}
          </button>
        </div>
        {plan && !busy && (
          <p className="muted" style={{ marginTop: 10, marginBottom: 0 }}>
            {n === appliedN
              ? `This plan is the optimal (shortest) schedule for ${appliedN} orders — re-running with the same scope gives the same result. Move the slider to try a different number of orders.`
              : `Scope changed to ${n} orders — click Optimize to re-solve (currently showing ${appliedN}).`}
          </p>
        )}
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
              <div className="label">Makespan <InfoTip text="Total time from start until the very last operation finishes. Fewer orders usually means a shorter makespan." /></div>
              <div className="value navy">{plan.makespan_hours} h</div>
              <div className="sub">
                {prevMakespan != null && prevMakespan !== plan.makespan_hours ? (
                  <span style={{ color: plan.makespan_hours < prevMakespan ? '#2e7d46' : '#c0392b', fontWeight: 700 }}>
                    {plan.makespan_hours < prevMakespan ? '▼' : '▲'} {Math.abs(plan.makespan_hours - prevMakespan).toFixed(1)} h vs previous
                  </span>
                ) : `objective: ${plan.objective}`}
              </div>
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

          {highlight && plan.ops.length > 0 && (() => {
            const ops = plan.ops.filter(o => o.order_id === highlight)
              .sort((a, b) => a.op_seq - b.op_seq || a.start_min - b.start_min)
            if (!ops.length) return null
            const h = m => (Math.round(m / 60 * 10) / 10)
            const start = Math.min(...ops.map(o => o.start_min))
            const end = Math.max(...ops.map(o => o.end_min))
            const work = ops.reduce((s, o) => s + o.duration_min, 0)
            return (
              <div className="card" style={{ borderColor: '#1b3a5e', boxShadow: '0 0 0 2px #e8f0fa' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <h3 style={{ margin: 0 }}>Order {highlight} — {ops[0].item_name}</h3>
                  <button className="chipbtn on" onClick={() => setHighlight(null)}>Clear selection ✕</button>
                </div>
                <div className="dp-grid" style={{ marginTop: 8 }}>
                  <div className="dp-cell"><div className="k">Operations</div><div className="v">{ops.length}</div></div>
                  <div className="dp-cell"><div className="k">Starts at</div><div className="v">{h(start)} h</div></div>
                  <div className="dp-cell"><div className="k">Finishes at</div><div className="v">{h(end)} h</div></div>
                  <div className="dp-cell"><div className="k">Machine work</div><div className="v">{h(work)} h</div></div>
                </div>
                <table className="tbl" style={{ marginTop: 12 }}>
                  <thead><tr><th>Step</th><th>Machine</th><th>Start</th><th>End</th><th>Duration</th></tr></thead>
                  <tbody>
                    {ops.map((o, i) => (
                      <tr key={i}>
                        <td>#{o.op_seq}</td>
                        <td>{o.work_center}</td>
                        <td>{h(o.start_min)} h</td>
                        <td>{h(o.end_min)} h</td>
                        <td>{h(o.duration_min)} h</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted" style={{ marginTop: 8 }}>
                  This order flows through {ops.length} machine{ops.length > 1 ? 's' : ''} in routing order. Gaps between steps are waiting time while other jobs use the next machine.
                </p>
              </div>
            )
          })()}

          {plan.ops.length > 0 && (() => {
            const busy = {}
            plan.ops.forEach(o => { busy[o.work_center] = (busy[o.work_center] || 0) + o.duration_min })
            const top = Object.entries(busy).sort((a, b) => b[1] - a[1])[0]
            const topWc = top[0], topH = Math.round(top[1] / 60 * 10) / 10
            const recs = [{
              icon: '⚖', title: `Busiest machine in this plan: ${topWc} (${topH}h of work)`,
              detail: `It drives the ${plan.makespan_hours}h makespan. Offloading some of its operations to a backup would finish sooner.`,
              cta: 'Rebalance →', onClick: () => navigate('allocation', week),
            }, {
              icon: '▶', title: 'Release orders in the sequence shown',
              detail: `Following this order finishes all ${plan.orders_scheduled} scheduled orders in ${plan.makespan_hours}h without any machine clash.`,
            }]
            if (plan.status !== 'OPTIMAL') recs.push({
              icon: '⏱', title: 'Solver stopped at a feasible (not proven-optimal) plan',
              detail: 'Reduce the number of orders, or accept this schedule — it is valid and respects every constraint.',
            })
            return <RecommendationList items={recs} />
          })()}
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button className="btn-ghost" onClick={() => navigate('priority', week)}>← See which orders are most urgent</button>
            <button className="btn-ghost" onClick={() => navigate('capacity', week)}>Check capacity for this week</button>
          </div>
        </>
      )}
    </>
  )
}
