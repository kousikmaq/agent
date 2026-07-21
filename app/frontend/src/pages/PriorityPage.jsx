import React, { useEffect, useState } from 'react'
import { getOverview, getPriority } from '../api'

function ScoreBar({ score }) {
  const color = score >= 80 ? '#c0392b' : score >= 55 ? '#e08a2e' : '#2e7d46'
  return (
    <div className="scorebar">
      <div className="scorebar-fill" style={{ width: `${score}%`, background: color }} />
      <span className="scorebar-txt">{score}</span>
    </div>
  )
}

export default function PriorityPage({ week, setWeek }) {
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
    getPriority(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')
  const atRisk = data ? data.orders.filter(o => o.at_risk).length : 0

  return (
    <>
      <div className="pagehead">
        <h1>Order Prioritization</h1>
        <p>Which orders to run first this week, and why — ranked by due date, critical ratio, customer tier and penalty.</p>
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

      {!data && <div className="loading">Ranking orders…</div>}

      {data && (
        <>
          <div className={`info ${atRisk ? 'amber' : ''}`}>
            <b>{data.orders_considered} orders</b> due the week of {data.week_start}.{' '}
            {atRisk > 0
              ? `${atRisk} are at risk (not enough time for the work) — run the top of the list first.`
              : 'None are at risk this week.'}
          </div>

          <div className="card">
            <h3>Priority list (highest urgency first)</h3>
            <table className="tbl">
              <thead>
                <tr>
                  <th>#</th><th>Order</th><th>Valve</th><th>Cust</th><th>Qty</th>
                  <th>Due in</th><th>Work</th><th>Crit. ratio</th><th>Urgency</th><th>Why</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map(o => (
                  <tr key={o.order_id} style={o.at_risk ? { background: '#fdf3f2' } : undefined}>
                    <td><b>{o.rank}</b></td>
                    <td>{o.order_id}</td>
                    <td>{o.item_name}</td>
                    <td><span className={`tierdot t${o.tier}`}>{o.tier}</span></td>
                    <td>{o.quantity}</td>
                    <td>{o.days_to_due}d</td>
                    <td>{o.processing_hours}h</td>
                    <td style={{ color: o.at_risk ? '#c0392b' : '#5a6778', fontWeight: o.at_risk ? 700 : 400 }}>
                      {o.critical_ratio}{o.at_risk ? ' ⚠' : ''}
                    </td>
                    <td style={{ minWidth: 90 }}><ScoreBar score={o.score} /></td>
                    <td className="muted" style={{ maxWidth: 220 }}>{o.reasons.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ marginTop: 8 }}>
              Critical ratio below 1 (⚠) means there is not enough production time before the due date.
            </p>
          </div>
        </>
      )}
    </>
  )
}
