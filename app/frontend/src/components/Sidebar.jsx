import React from 'react'

const ITEMS = [
  { key: 'dashboard', label: 'Dashboard', ic: '▦' },
  { key: 'capacity', label: 'Capacity Analysis', ic: '▤' },
  { key: 'priority', label: 'Order Prioritization', ic: '≡' },
  { key: 'allocation', label: 'Resource Allocation', ic: '⇄' },
  { key: 'schedule', label: 'Schedule (Gantt)', ic: '☷' },
  { key: 'risk', label: 'Delay Risk', ic: '⚠' },
  { key: 'demand', label: 'Demand vs Capacity', ic: '⚖' },
  { key: 'scenarios', label: 'What-if Scenarios', ic: '⚙' },
]

export default function Sidebar({ page, setPage }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="logo">⬢</span>
        <div>
          <div className="t">Production Planner</div>
          <div className="s">Scheduling Agent</div>
        </div>
      </div>
      <nav className="nav">
        {ITEMS.map(i => (
          <button
            key={i.key}
            className={`navitem ${page === i.key ? 'active' : ''}`}
            onClick={() => setPage(i.key)}
          >
            <span className="ic">{i.ic}</span>{i.label}
          </button>
        ))}
      </nav>
      <div className="foot">
        v0.7 · valve-factory demo<br />
        9 features · full set
      </div>
    </aside>
  )
}
