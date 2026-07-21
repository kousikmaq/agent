import React, { useEffect, useState } from 'react'
import { getOverview, getScenarios } from '../api'
import WeekChips from '../components/WeekChips'

function ScenarioCard({ s, best }) {
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
    </div>
  )
}

export default function ScenariosPage({ week, setWeek }) {
  const [weeks, setWeeks] = useState(null)
  const [data, setData] = useState(null)
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
    setData(null)
    getScenarios(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  // best = fewest overloaded, then lowest bottleneck
  let bestKey = null
  if (data) {
    const best = [...data.scenarios].sort(
      (a, b) => a.overloaded_count - b.overloaded_count || a.bottleneck_util - b.bottleneck_util)[0]
    bestKey = best.key
  }

  return (
    <>
      <div className="pagehead">
        <h1>What-if Scenarios</h1>
        <p>Compare planning options for the week side by side, before you commit to one.</p>
      </div>

      <WeekChips weeks={weeks} week={week} setWeek={setWeek} />

      {!data && <div className="loading">Running scenarios…</div>}

      {data && (
        <>
          <div className="info"><b>{data.summary}</b></div>
          <div className="grid cards3">
            {data.scenarios.map(s => (
              <ScenarioCard key={s.key} s={s} best={s.key === bestKey} />
            ))}
          </div>
          <p className="muted" style={{ marginTop: 12 }}>
            All three use the same capacity engine - only the inputs change (extra shift, or fewer orders).
            The "best" tag marks the option that clears the most overload.
          </p>
        </>
      )}
    </>
  )
}
