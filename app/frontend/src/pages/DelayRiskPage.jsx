import React, { useEffect, useState } from 'react'
import { getOverview, getRisk } from '../api'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

function Stat({ label, value, cls, sub, tip }) {
  return (
    <div className="card stat">
      <div className="label">{label}{tip && <InfoTip text={tip} />}</div>
      <div className={`value ${cls || ''}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export default function DelayRiskPage({ week, setWeek, navigate }) {
  const [weeks, setWeeks] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [cause, setCause] = useState('all')   // all | material | capacity

  useEffect(() => {
    getOverview()
      .then(ov => {
        setWeeks(ov.weeks)
        if (!week) {
          const current = [...ov.weeks].sort((a, b) => a.week_start.localeCompare(b.week_start))[0]
          setWeek(current.week_start)
        }
      })
      .catch(e => setErr(String(e)))
  }, [])

  useEffect(() => {
    if (!week) return
    setData(null)
    getRisk(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  let atRiskOrders = data ? data.orders.filter(o => o.at_risk) : []
  if (cause === 'material') atRiskOrders = atRiskOrders.filter(o => o.causes.some(c => /material|component|stock|part/i.test(c)))
  if (cause === 'capacity') atRiskOrders = atRiskOrders.filter(o => o.causes.some(c => /time|capacity|hours|machine/i.test(c)))

  return (
    <>
      <div className="pagehead">
        <h1>Delay Risk</h1>
        <p>Orders likely to be late this week — from missing materials or tight capacity — each with a fix.</p>
      </div>

      <HelpBox title="New here? Where delay risk comes from">
        <ul>
          <li><b>Material risk</b> — the parts (bill of materials) needed aren't in stock and won't arrive in time.</li>
          <li><b>Capacity risk</b> — there isn't enough machine time before the due date (critical ratio below 1).</li>
          <li>Each at-risk order lists the <b>cause</b> and a suggested <b>fix</b> (expedite a part, add a shift, re-sequence, etc.).</li>
        </ul>
      </HelpBox>

      <WeekBar weeks={weeks} week={week} setWeek={setWeek} />

      {!data && <div className="loading">Checking risk…</div>}

      {data && (
        <>
          <div className={`info ${data.at_risk_count ? 'amber' : ''}`}>
            <b>{data.summary}</b>
          </div>

          <div className="grid cards3">
            <Stat label="Orders at risk" value={data.at_risk_count}
                  cls={data.at_risk_count ? 'red' : 'green'} sub={`of ${data.orders_considered} this week`} />
            <Stat label="Material risk" value={data.material_risk_count} cls="amber" sub="missing components"
                  tip="Parts from the bill of materials are short and won't arrive before the order is due." />
            <Stat label="Capacity risk" value={data.capacity_risk_count} cls="amber" sub="not enough time"
                  tip="Not enough machine time before the due date (critical ratio below 1)." />
          </div>

          <div className="toolbar">
            <span className="t-lbl">Filter by cause</span>
            <div className="seg">
              <button className={cause === 'all' ? 'on' : ''} onClick={() => setCause('all')}>All</button>
              <button className={cause === 'material' ? 'on' : ''} onClick={() => setCause('material')}>Material</button>
              <button className={cause === 'capacity' ? 'on' : ''} onClick={() => setCause('capacity')}>Capacity</button>
            </div>
            <button className="btn-ghost" style={{ marginLeft: 'auto' }} onClick={() => navigate('priority', week)}>See order priorities →</button>
          </div>

          <div className="grid two-13">
            <div className="card">
              <h3>At-risk orders</h3>
              {atRiskOrders.length === 0
                ? <p className="muted">No orders at risk for this filter.</p>
                : (
                  <table className="tbl">
                    <thead>
                      <tr><th>Order</th><th>Valve</th><th>Due</th><th>Why</th><th>Fix</th></tr>
                    </thead>
                    <tbody>
                      {atRiskOrders.map(o => (
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
              <h3>Short components <InfoTip text="Parts needed by this week's orders where demand exceeds what's on hand plus what arrives in time." /></h3>
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
