import React from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  CartesianGrid, Cell, ReferenceLine, LabelList
} from 'recharts'

// Horizontal bars of how busy each machine is (%). Over 100% = the bottleneck.
export default function BottleneckChart({ resources }) {
  const data = [...resources]
    .sort((a, b) => a.utilization_pct - b.utilization_pct)
    .map(r => ({ name: r.work_center, util: r.utilization_pct, over: r.utilization_pct > 100 }))

  return (
    <div className="card">
      <h3>How busy each machine is (%)</h3>
      <ResponsiveContainer width="100%" height={340}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 46, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
          <XAxis type="number" domain={[0, 150]} tick={{ fontSize: 11, fill: '#5a6778' }} unit="%" />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#1b3a5e' }} width={66} />
          <Tooltip formatter={(v) => `${v}%`} />
          <ReferenceLine x={100} stroke="#1b3a5e" strokeDasharray="4 3"
            label={{ value: '100%', fontSize: 10, fill: '#1b3a5e', position: 'top' }} />
          <Bar dataKey="util" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.over ? '#c0392b' : '#2e7d46'} />
            ))}
            <LabelList dataKey="util" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 10.5, fill: '#1f2a37' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="muted">The bar past the 100% line is your bottleneck.</p>
    </div>
  )
}
