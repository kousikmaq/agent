import React, { useEffect, useState } from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, Cell
} from 'recharts'
import { getDemand } from '../api'

function Stat({ label, value, cls, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={`value ${cls || ''}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export default function DemandPage() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    getDemand().then(setData).catch(e => setErr(String(e)))
  }, [])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!data) return <div className="loading">Checking the order book…</div>

  const verdictClass = !data.overall_feasible ? 'amber' : (data.overloaded_weeks ? 'amber' : '')
  const chartData = data.departments.map(d => ({
    name: d.department, Required: d.required_hours, Available: d.available_hours, over: !d.feasible
  }))

  return (
    <>
      <div className="pagehead">
        <h1>Demand vs Capacity</h1>
        <p>Can we commit to the whole {data.horizon_weeks}-week order book? Total work required vs total capacity available.</p>
      </div>

      <div className={`info ${verdictClass}`}>
        <b>Verdict:</b> {data.verdict}
      </div>

      <div className="grid cards4">
        <Stat label="Total load (horizon)" value={`${data.overall_utilization_pct}%`}
              cls={data.overall_feasible ? 'green' : 'red'} sub="required ÷ available" />
        <Stat label="Work required" value={`${data.overall_required_hours.toLocaleString()} h`} cls="navy" />
        <Stat label="Capacity available" value={`${data.overall_available_hours.toLocaleString()} h`} cls="navy" />
        <Stat label="Overloaded weeks" value={data.overloaded_weeks}
              cls={data.overloaded_weeks ? 'amber' : 'green'} sub="peaks to smooth" />
      </div>

      <h2 className="section-title">Demand vs capacity by department</h2>
      <div className="card">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="name" tick={{ fontSize: 11.5, fill: '#5a6778' }} />
            <YAxis tick={{ fontSize: 11, fill: '#5a6778' }} label={{ value: 'hours (horizon)', angle: -90, position: 'insideLeft', fill: '#5a6778', fontSize: 11 }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Available" fill="#c7d2de" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Required" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {chartData.map((d, i) => <Cell key={i} fill={d.over ? '#c0392b' : '#2e7d46'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="muted">Over the whole horizon, every department fits within capacity — the challenge is weekly peaks, not total volume.</p>
      </div>

      <div className="grid two-13">
        <div className="card">
          <h3>Per-machine load (whole horizon)</h3>
          <table className="tbl">
            <thead><tr><th>Machine</th><th>Dept</th><th>Required</th><th>Available</th><th>Load</th></tr></thead>
            <tbody>
              {data.resources.map(r => (
                <tr key={r.work_center}>
                  <td>{r.work_center}</td>
                  <td className="muted">{r.department}</td>
                  <td>{r.required_hours} h</td>
                  <td>{r.available_hours} h</td>
                  <td style={{ color: r.feasible ? '#2e7d46' : '#c0392b', fontWeight: 700 }}>{r.utilization_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>What to do</h3>
          {data.fixes.map((f, i) => (
            <div className="rec" key={i}>
              <span className="rec-ico">→</span>
              <div className="rec-d">{f}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
