import React from 'react'

const PALETTE = [
  '#1b3a5e', '#0f766e', '#b47a1e', '#6a4c9c', '#2e7d46', '#c0392b',
  '#2874a6', '#117a65', '#a04000', '#7d3c98', '#1e8449', '#b03a2e'
]

export default function GanttChart({ plan }) {
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
      <h3>Optimised schedule (Gantt) — one row per machine</h3>

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
                return (
                  <div key={i} className="gantt-op"
                    style={{ left: `${left}%`, width: `${width}%`, background: orderColors[o.order_id] }}
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
          <span key={oid}><i className="sw" style={{ background: orderColors[oid] }} />{oid}</span>
        ))}
      </div>
    </div>
  )
}
