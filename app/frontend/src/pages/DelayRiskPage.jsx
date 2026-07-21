import React, { useEffect, useState } from 'react'
import { getOverview, getRisk } from '../api'

function Stat({ label, value, cls, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={`value ${cls || ''}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export default function DelayRiskPage({ week, setWeek }) {
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
    getRisk(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')

  return (
    <>
      <div className="pagehead">
        <h1>Delay Risk</h1>
        <p>Orders likely to be late this week — from missing materials (BOM vs inventory) or tight capacity — each with a fix.</p>
      </div>

      <div className="weeks">
        {weeks.map(w => (
          <button key={w.week_start}
            className={`weekchip ${w.week_start === week ? 'active' : ''}`}
            onClick={() => setWeek(w.week_start)}>
            <span className={`dot ${statusClass(w.status)}`} />
            {w.week_start.slice(5)}
          </button>
        ))}
      </div>

      {!data && <div className="loading">Checking risk…</div>}

      {data && (
        <>
          <div className={`info ${data.at_risk_count ? 'amber' : ''}`}>
            <b>{data.summary}</b>
          </div>

          <div className="grid cards3">
            <Stat label="Orders at risk" value={data.at_risk_count}
                  cls={data.at_risk_count ? 'red' : 'green'} sub={`of ${data.orders_considered} this week`} />
            <Stat label="Material risk" value={data.material_risk_count} cls="amber" sub="missing components" />
            <Stat label="Capacity risk" value={data.capacity_risk_count} cls="amber" sub="not enough time" />
          </div>

          <div className="grid two-13">
            <div className="card">
              <h3>At-risk orders</h3>
              {data.orders.filter(o => o.at_risk).length === 0
                ? <p className="muted">No orders at risk this week.</p>
                : (
                  <table className="tbl">
                    <thead>
                      <tr><th>Order</th><th>Valve</th><th>Due</th><th>Why</th><th>Fix</th></tr>
                    </thead>
                    <tbody>
                      {data.orders.filter(o => o.at_risk).map(o => (
                        <tr key={o.order_id} style={{ background: '#fdf3f2' }}>
                          <td>{o.order_id}</td>
                          <td>{o.item_name}</td>
                          <td>{o.due_date.slice(5)}</td>
                          <td className="muted" style={{ maxWidth: 230 }}>{o.causes.join('; ')}</td>
                          <td className="muted" style={{ maxWidth: 220 }}>{o.fix}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
            </div>

            <div className="card">
              <h3>Short components</h3>
              {data.shortages.length === 0
                ? <p className="muted">All materials are covered this week.</p>
                : data.shortages.map(s => (
                  <div className="feature" key={s.component_id}>
                    <span className="badge planned" style={{ background: '#fdecea', color: '#c0392b', minWidth: 52, textAlign: 'center' }}>
                      -{s.shortfall}
                    </span>
                    <div>
                      <div className="fname">{s.component_name}</div>
                      <div className="fdesc">need {s.required} · have {s.available} · {s.note}</div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
