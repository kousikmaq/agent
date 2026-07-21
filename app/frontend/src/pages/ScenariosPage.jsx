import React, { useEffect, useState } from 'react'
import { getOverview, getScenarios } from '../api'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

function ScenarioCard({ s, best, onCreate }) {
  const over = s.bottleneck_util > 100
  return (
    <div className="card scen" style={best ? { borderColor: '#2e7d46', boxShadow: '0 0 0 2px #eaf6ec' } : undefined}>
      <div className="scen-head">
        <h3 style={{ margin: 0 }}>{s.name}</h3>
        {best && <span className="badge live">best</span>}
      </div>
      <p className="muted" style={{ marginTop: 4 }}>{s.description}</p>
      <div className="scen-metric">
        <div className={`value ${over ? 'red' : 'green'}`} style={{ fontSize: 30 }}>{s.bottleneck_util}%</div>
        <div className="sub">bottleneck {s.bottleneck_wc || '-'}</div>
      </div>
      <div className="scen-row">
        <span><b style={{ color: s.overloaded_count ? '#c0392b' : '#2e7d46' }}>{s.overloaded_count}</b> overloaded</span>
        <span><b>{s.orders_planned}</b> orders</span>
      </div>
      <div className="info" style={{ margin: '10px 0 0', background: '#f7f9fb', border: '1px solid #e3e8ee', color: '#1f2a37' }}>
        {s.outcome}
      </div>
      <div className="scen-actions">
        <button className="btn-primary" onClick={() => onCreate(s)}>Create plan from this →</button>
      </div>
    </div>
  )
}

export default function ScenariosPage({ week, setWeek, navigate }) {
  const [weeks, setWeeks] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [metric, setMetric] = useState('overload')  // overload | bottleneck

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

  useEffect(() => {
    if (!week) return
    setData(null)
    getScenarios(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  // "best" depends on the metric the user chooses to optimise for
  let bestKey = null
  let ordered = []
  if (data) {
    const sorters = {
      overload: (a, b) => a.overloaded_count - b.overloaded_count || a.bottleneck_util - b.bottleneck_util,
      bottleneck: (a, b) => a.bottleneck_util - b.bottleneck_util || a.overloaded_count - b.overloaded_count,
    }
    ordered = [...data.scenarios].sort(sorters[metric])
    bestKey = ordered[0].key
  }

  // "create a plan" from a scenario: jump to the schedule optimiser for this week
  function createPlan(s) { navigate('schedule', week) }

  return (
    <>
      <div className="pagehead">
        <h1>What-if Scenarios</h1>
        <p>Compare planning options for the week side by side, then turn the one you like into a machine schedule.</p>
      </div>

      <HelpBox title="New here? What these scenarios mean">
        <ul>
          <li><b>Baseline</b> — today's plan with no changes. The reference point.</li>
          <li><b>Add a shift</b> — give the bottleneck department one extra shift, raising its capacity. Costs overtime but clears load.</li>
          <li><b>Defer orders</b> — push the least-urgent orders to a later week to relieve this week.</li>
          <li>Lower <b>bottleneck %</b> and fewer <b>overloaded</b> machines are better. Pick what to optimise for below, then press <b>Create plan</b> to schedule it.</li>
        </ul>
      </HelpBox>

      <WeekBar weeks={weeks} week={week} setWeek={setWeek} />

      {!data && <div className="loading">Running scenarios…</div>}

      {data && (
        <>
          <div className="info"><b>{data.summary}</b></div>

          <div className="toolbar">
            <span className="t-lbl">Rank “best” by
              <InfoTip text="Choose the goal. 'Fewest overloaded' minimises machines over 100%. 'Lowest bottleneck' minimises the busiest machine's load." />
            </span>
            <div className="seg">
              <button className={metric === 'overload' ? 'on' : ''} onClick={() => setMetric('overload')}>Fewest overloaded</button>
              <button className={metric === 'bottleneck' ? 'on' : ''} onClick={() => setMetric('bottleneck')}>Lowest bottleneck</button>
            </div>
          </div>

          <div className="grid cards3">
            {ordered.map(s => (
              <ScenarioCard key={s.key} s={s} best={s.key === bestKey} onCreate={createPlan} />
            ))}
          </div>
          <p className="muted" style={{ marginTop: 12 }}>
            All three use the same capacity engine — only the inputs change (extra shift, or fewer orders).
            The “best” tag marks the option that wins on your chosen goal. “Create plan” builds an optimised
            machine schedule for the selected week on the Schedule page.
          </p>
        </>
      )}
    </>
  )
}
