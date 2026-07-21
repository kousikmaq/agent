import React, { useEffect, useState } from 'react'
import { getOverview, getHeatmap, getDatasetSummary, getFeatures } from '../api'
import WeeklyOverviewChart from '../components/WeeklyOverviewChart'
import HeatmapCard from '../components/HeatmapCard'
import FeatureList from '../components/FeatureList'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

function Stat({ label, value, cls, sub, tip, onClick }) {
  return (
    <div className={`card stat ${onClick ? 'clickable' : ''}`} onClick={onClick} style={onClick ? { cursor: 'pointer' } : undefined}>
      <div className="label">{label}{tip && <InfoTip text={tip} />}</div>
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

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!ov || !hm || !ds || !feat) return <div className="loading">Loading dashboard…</div>

  const sorted = [...ov.weeks].sort((a, b) => a.week_start.localeCompare(b.week_start))
  const current = sorted[0]
  const attention = ov.weeks.filter(w => w.status !== 'OK')
  const comfy = ov.weeks.length - attention.length
  const peak = [...ov.weeks].sort((a, b) => b.bottleneck_util - a.bottleneck_util)[0]
  const avgPeak = Math.round(ov.weeks.reduce((s, w) => s + w.bottleneck_util, 0) / ov.weeks.length)
  const curOver = current && current.status === 'OVERLOADED'
  const curTight = current && current.status === 'TIGHT'

  return (
    <>
      <div className="pagehead">
        <h1>Dashboard</h1>
        <p>A one-look view of the whole order book. Capacity is analysed for every week in a single pass (bulk processing).</p>
      </div>

      <HelpBox title="New here? Start with this 30-second tour">
        <ul>
          <li>Your factory has <b>{ds.tables.work_centers} machines</b> and a book of <b>{ds.total_orders} orders</b> spread over <b>{ov.weeks.length} weeks</b> (~4 months). That window is the <b>planning horizon</b>.</li>
          <li>Each week has a <b>bottleneck</b> — its busiest machine. If that machine is over 100%, the week is <b>overloaded</b> (red) and something will be late.</li>
          <li>Green = comfortable, amber = tight, red = overloaded. <b>Click any week</b> (chart, heatmap or list) to drill into it.</li>
          <li>Use the left menu to prioritise orders, rebalance machines, build a schedule, or check delay risk. The floating <b>assistant</b> answers questions in plain language.</li>
        </ul>
      </HelpBox>

      {/* This week at a glance */}
      {current && (
        <div className={`callout ${curOver ? 'red' : curTight ? '' : 'green'}`} style={curTight ? { background: '#fcf3e3', borderColor: '#efe0c0' } : undefined}>
          <span className="co-ico">{curOver ? '⛔' : curTight ? '⚠️' : '✅'}</span>
          <div>
            <div className="co-t">This week (of {current.week_start}) — {curOver ? 'overloaded' : curTight ? 'running tight' : 'comfortable'}</div>
            <div className="co-d">
              {current.orders} orders due · busiest machine {current.bottleneck_wc} at {current.bottleneck_util}%.{' '}
              <span style={{ color: '#0f766e', cursor: 'pointer', fontWeight: 600 }} onClick={() => onSelectWeek(current.week_start)}>Open this week →</span>
            </div>
          </div>
          <div className="co-metric">
            <div className="m-val" style={{ color: curOver ? '#c0392b' : curTight ? '#b47a1e' : '#2e7d46' }}>{current.bottleneck_util}%</div>
            <div className="m-lbl">this week's peak</div>
          </div>
        </div>
      )}

      <div className="grid cards4">
        <Stat label="Orders in the book" value={ds.total_orders} cls="navy" sub={`across ${ov.weeks.length} weeks`}
              tip="Every committed customer order in the planning horizon (about 4 months)." />
        <Stat label="Overloaded weeks" value={ov.overloaded_weeks}
              cls={ov.overloaded_weeks ? 'red' : 'green'} sub={ov.overloaded_weeks ? 'need attention' : 'all clear'}
              tip="Weeks where at least one machine is booked above 100% of its capacity." />
        <Stat label="Comfortable weeks" value={comfy} cls="green" sub={`of ${ov.weeks.length} total`}
              tip="Weeks where every machine is within capacity — no action needed." />
        <Stat label="Peak load" value={`${peak.bottleneck_util}%`} cls={peak.bottleneck_util > 100 ? 'red' : 'amber'}
              sub={`worst week: ${peak.week_start.slice(5)}`} onClick={() => onSelectWeek(peak.week_start)}
              tip="The single busiest machine-week in the whole horizon. Click to open it." />
      </div>

      <div className="grid cards4">
        <Stat label="Products (items)" value={ds.tables.items} cls="navy" sub={`${ds.tables.work_centers} work centres`}
              tip="Distinct valve types you make. Each has a routing (sequence of machine operations)." />
        <Stat label="Average peak load" value={`${avgPeak}%`} cls={avgPeak > 100 ? 'red' : avgPeak >= 85 ? 'amber' : 'green'}
              sub="mean of weekly bottlenecks" tip="Average of each week's busiest-machine load — a sense of overall pressure." />
        <Stat label="Weeks to watch" value={attention.length} cls="amber" sub="tight or overloaded"
              tip="Weeks that are overloaded or running close to full and worth a look." />
        <Stat label="Machines" value={ds.tables.work_centers} cls="navy" sub="across departments"
              tip="Work centres (machines/cells) available to do the work." />
      </div>

      <h2 className="section-title">Capacity across all weeks <InfoTip text="Each bar is a week; height is its busiest machine's load. Red bars are overloaded. Click a bar to drill in." /></h2>
      <WeeklyOverviewChart weeks={ov.weeks} onSelectWeek={onSelectWeek} />

      <h2 className="section-title">Capacity heatmap <InfoTip text="Rows are machines, columns are weeks. Colour shows how loaded each machine is that week. Click a cell to open the week." /></h2>
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
          <h3>Dataset (all tables connected) <InfoTip text="The demo runs on a connected dataset: orders link to items, items to routings and bills of materials, and those to inventory and customers." /></h3>
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
