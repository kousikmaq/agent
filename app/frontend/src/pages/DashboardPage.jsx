import React, { useEffect, useState } from 'react'
import { getOverview, getHeatmap, getDatasetSummary, getFeatures } from '../api'
import WeeklyOverviewChart from '../components/WeeklyOverviewChart'
import HeatmapCard from '../components/HeatmapCard'
import FeatureList from '../components/FeatureList'

function Stat({ label, value, cls, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={`value ${cls || ''}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export default function DashboardPage({ onSelectWeek }) {
  const [ov, setOv] = useState(null)
  const [hm, setHm] = useState(null)
  const [ds, setDs] = useState(null)
  const [feat, setFeat] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    Promise.all([getOverview(), getHeatmap(), getDatasetSummary(), getFeatures()])
      .then(([o, h, d, f]) => { setOv(o); setHm(h); setDs(d); setFeat(f) })
      .catch(e => setErr(String(e)))
  }, [])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!ov || !hm || !ds || !feat) return <div className="loading">Loading dashboard…</div>

  const attention = ov.weeks.filter(w => w.status !== 'OK')

  return (
    <>
      <div className="pagehead">
        <h1>Dashboard</h1>
        <p>A one-look view of the whole order book. Capacity is analysed for every week in a single pass (bulk processing).</p>
      </div>

      <div className="info">
        <b>How to read this:</b> the chart shows the busiest machine's load for each week.
        Green weeks are fine, red weeks are overloaded. Click any red/amber week to see what to do.
      </div>

      <div className="grid cards4">
        <Stat label="Orders in the book" value={ds.total_orders} cls="navy" sub={`across ${ov.weeks.length} weeks`} />
        <Stat label="Products (items)" value={ds.tables.items} cls="navy" sub={`${ds.tables.work_centers} work centres`} />
        <Stat label="Overloaded weeks" value={ov.overloaded_weeks}
              cls={ov.overloaded_weeks ? 'red' : 'green'} sub={ov.overloaded_weeks ? 'need attention' : 'all clear'} />
        <Stat label="Weeks to watch" value={attention.length} cls="amber" sub="tight or overloaded" />
      </div>

      <h2 className="section-title">Capacity across all weeks</h2>
      <WeeklyOverviewChart weeks={ov.weeks} onSelectWeek={onSelectWeek} />

      <h2 className="section-title">Capacity heatmap</h2>
      <HeatmapCard heatmap={hm} onSelectWeek={onSelectWeek} />

      <div className="grid two-13">
        <div className="card">
          <h3>Weeks that need attention</h3>
          {attention.length === 0 && <p className="muted">Nothing overloaded — the plan is comfortable.</p>}
          {attention.map(w => (
            <div className="feature" key={w.week_start} style={{ cursor: 'pointer' }} onClick={() => onSelectWeek(w.week_start)}>
              <span className={`dot ${w.status === 'OVERLOADED' ? 'over' : 'tight'}`} style={{ marginTop: 5 }} />
              <div>
                <div className="fname">Week of {w.week_start} — {w.bottleneck_wc} at {w.bottleneck_util}%</div>
                <div className="fdesc">{w.orders} orders · {w.status === 'OVERLOADED' ? `${w.overloaded_count} machine(s) over capacity` : 'running tight'}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <h3>Dataset (all tables connected)</h3>
          {Object.entries(ds.tables).map(([k, v]) => (
            <div className="feature" key={k}>
              <span className="badge live" style={{ minWidth: 46, textAlign: 'center' }}>{v}</span>
              <div className="fname" style={{ textTransform: 'capitalize' }}>{k.replace('_', ' ')}</div>
            </div>
          ))}
        </div>
      </div>

      <h2 className="section-title">Feature roadmap</h2>
      <FeatureList features={feat} />
    </>
  )
}
