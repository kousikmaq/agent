import React from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  CartesianGrid, Cell, ReferenceLine
} from 'recharts'

const COLOR = { OK: '#2e7d46', TIGHT: '#b47a1e', OVERLOADED: '#c0392b' }

// BULK view: bottleneck utilisation for every week of the order book.
export default function WeeklyOverviewChart({ weeks, onSelectWeek }) {
  const data = weeks.map(w => ({
    name: w.week_start.slice(5),        // MM-DD
    util: w.bottleneck_util,
    status: w.status,
    week: w.week_start
  }))

  return (
    <div className="card">
      <h3>Bottleneck utilisation by week (whole order book, analysed in one pass)</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#5a6778' }} />
          <YAxis unit="%" domain={[0, 130]} tick={{ fontSize: 11, fill: '#5a6778' }} />
          <Tooltip formatter={(v, n, p) => [`${v}%  (${p.payload.status})`, 'bottleneck']} />
          <ReferenceLine y={100} stroke="#1b3a5e" strokeDasharray="4 3"
            label={{ value: '100%', fontSize: 10, fill: '#1b3a5e', position: 'right' }} />
          <Bar dataKey="util" radius={[4, 4, 0, 0]} cursor="pointer" isAnimationActive={false}
            onClick={(d) => onSelectWeek && onSelectWeek(d.week)}>
            {data.map((d, i) => <Cell key={i} fill={COLOR[d.status]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="muted">Green = fine, amber = tight, red = overloaded. Click a bar to open that week.</p>
    </div>
  )
}
