import React from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, Cell
} from 'recharts'

// Grouped bars: hours needed vs hours available, per work centre.
// The "Needed" bar turns red when the machine is overloaded.
export default function CapacityChart({ resources }) {
  const data = resources.map(r => ({
    name: r.work_center,
    Needed: r.required_hours,
    Available: r.available_hours,
    overloaded: r.status === 'OVERLOADED'
  }))

  return (
    <div className="card">
      <h3>Hours needed vs. available (per work centre)</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 16, right: 12, left: 0, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
          <XAxis dataKey="name" tick={{ fontSize: 10.5, fill: '#5a6778' }} angle={-30} textAnchor="end" height={54} interval={0} />
          <YAxis tick={{ fontSize: 11, fill: '#5a6778' }} label={{ value: 'hours', angle: -90, position: 'insideLeft', fill: '#5a6778', fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Available" fill="#c7d2de" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="Needed" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.overloaded ? '#c0392b' : '#2e7d46'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="muted">Red bar = more work than the machine can do this week.</p>
    </div>
  )
}
