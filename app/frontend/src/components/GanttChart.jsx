import React from 'react'

const PALETTE = [
  '#1b3a5e', '#0f766e', '#b47a1e', '#6a4c9c', '#2e7d46', '#c0392b',
  '#2874a6', '#117a65', '#a04000', '#7d3c98', '#1e8449', '#b03a2e'
]

export default function GanttChart({ plan, animate, highlight, onSelectOrder }) {
  const { machines, ops, makespan_min } = plan
  const span = makespan_min || 1

  // consistent colour per order (in first-seen order)
  const orderColors = {}
  let ci = 0
  ops.forEach(o => {
    if (!(o.order_id in orderColors)) orderColors[o.order_id] = PALETTE[ci++ % PALETTE.length]
  })
  const orders = Object.keys(orderColors)

  // hour tick labels
  const totalH = Math.ceil(span / 60)
  const ticks = 6
  const tickList = Array.from({ length: ticks + 1 }, (_, i) => ({
    left: (i / ticks) * 100,
    label: Math.round((totalH * i) / ticks) + 'h'
  }))

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>Optimised schedule (Gantt) — one row per machine</h3>
        {highlight && (
          <button className="chipbtn on" onClick={() => onSelectOrder && onSelectOrder(null)}>
            Focused on {highlight} · clear
          </button>
        )}
      </div>
      <p className="muted" style={{ marginTop: 4 }}>
        Time runs left → right (hours from the start). Each coloured block is one operation on that machine.
        Blocks never overlap on a row (a machine does one job at a time), and an order's blocks always run in routing order.
      </p>

      <div className="gantt">
        <div className="gantt-row gantt-head">
          <div className="gantt-label" />
          <div className="gantt-track">
            {tickList.map((t, i) => (
              <div key={i} className="gantt-tick" style={{ left: `${t.left}%` }}>{t.label}</div>
            ))}
          </div>
        </div>

        {machines.map(m => (
          <div className="gantt-row" key={m}>
            <div className="gantt-label">{m}</div>
            <div className="gantt-track">
              {tickList.map((t, i) => (
                <div key={i} className="gantt-grid" style={{ left: `${t.left}%` }} />
              ))}
              {ops.filter(o => o.work_center === m).map((o, i) => {
                const left = (o.start_min / span) * 100
                const width = Math.max((o.duration_min / span) * 100, 0.6)
                const dim = highlight && o.order_id !== highlight
                return (
                  <div key={i}
                    className={`gantt-op editable ${animate ? 'animate' : ''} ${dim ? 'dimmed' : ''}`}
                    onClick={() => onSelectOrder && onSelectOrder(o.order_id)}
                    style={{ left: `${left}%`, width: `${width}%`, background: orderColors[o.order_id],
                             animationDelay: animate ? `${Math.min(i * 30, 600)}ms` : undefined }}
                    title={`${o.order_id} · ${o.item_name}\nop ${o.op_seq} on ${m}\n${Math.round(o.start_min / 60 * 10) / 10}h – ${Math.round(o.end_min / 60 * 10) / 10}h`}>
                    {width > 4 ? o.order_id.replace('SO-', '') : ''}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="legend" style={{ marginTop: 14 }}>
        {orders.map(oid => (
          <span key={oid} style={{ cursor: 'pointer', opacity: highlight && oid !== highlight ? 0.4 : 1 }}
            onClick={() => onSelectOrder && onSelectOrder(oid === highlight ? null : oid)}>
            <i className="sw" style={{ background: orderColors[oid] }} />{oid}
          </span>
        ))}
      </div>
      <p className="muted" style={{ marginTop: 8 }}>Tip: click an order (block or legend) to focus just its operations across the machines.</p>
    </div>
  )
}
