import React, { useEffect, useState } from 'react'
import { getOverview, getPriority } from '../api'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

function ScoreBar({ score }) {
  const color = score >= 80 ? '#c0392b' : score >= 55 ? '#e08a2e' : '#2e7d46'
  return (
    <div className="scorebar">
      <div className="scorebar-fill" style={{ width: `${score}%`, background: color }} />
      <span className="scorebar-txt">{score}</span>
    </div>
  )
}

export default function PriorityPage({ week, setWeek, navigate }) {
  const [weeks, setWeeks] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [filter, setFilter] = useState('all')      // all | risk | A
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('rank')          // rank | due | cr | qty
  const [openRow, setOpenRow] = useState(null)

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
    setData(null); setOpenRow(null)
    getPriority(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const atRisk = data ? data.orders.filter(o => o.at_risk).length : 0

  let rows = data ? [...data.orders] : []
  if (filter === 'risk') rows = rows.filter(o => o.at_risk)
  if (filter === 'A') rows = rows.filter(o => o.tier === 'A')
  if (q.trim()) {
    const s = q.trim().toLowerCase()
    rows = rows.filter(o => o.order_id.toLowerCase().includes(s) || o.item_name.toLowerCase().includes(s))
  }
  const sorters = {
    rank: (a, b) => a.rank - b.rank,
    due: (a, b) => a.days_to_due - b.days_to_due,
    cr: (a, b) => a.critical_ratio - b.critical_ratio,
    qty: (a, b) => b.quantity - a.quantity,
  }
  rows.sort(sorters[sort])
  const Arrow = ({ col }) => sort === col ? <span className="sortarrow">▼</span> : null

  return (
    <>
      <div className="pagehead">
        <h1>Order Prioritization</h1>
        <p>Which orders to run first this week, and why — ranked by due date, tightness of time, customer tier and late-penalty.</p>
      </div>

      <HelpBox title="New here? How orders are ranked">
        <ul>
          <li><b>Urgency score (0–100)</b> blends four things: how soon it is due, how tight the time is, how important the customer is, and the penalty for being late.</li>
          <li><b>Critical ratio</b> = time left ÷ time needed. <b>Below 1</b> means there isn't enough time to finish before the due date — the order is <b>at risk</b>.</li>
          <li><b>Tier A/B/C</b> is the customer's importance (A = most important).</li>
          <li>Run the top of the list first. Click any row to see the full reasoning.</li>
        </ul>
      </HelpBox>

      <WeekBar weeks={weeks} week={week} setWeek={setWeek} />

      {!data && <div className="loading">Ranking orders…</div>}

      {data && (
        <>
          <div className={`info ${atRisk ? 'amber' : ''}`}>
            <b>{data.orders_considered} orders</b> due the week of {data.week_start}.{' '}
            {atRisk > 0
              ? `${atRisk} are at risk (not enough time for the work) — run the top of the list first.`
              : 'None are at risk this week.'}
          </div>

          <div className="toolbar">
            <span className="t-lbl">Show</span>
            <div className="seg">
              <button className={filter === 'all' ? 'on' : ''} onClick={() => setFilter('all')}>All ({data.orders.length})</button>
              <button className={filter === 'risk' ? 'on' : ''} onClick={() => setFilter('risk')}>At risk ({atRisk})</button>
              <button className={filter === 'A' ? 'on' : ''} onClick={() => setFilter('A')}>Tier A</button>
            </div>
            <input className="search" placeholder="Search order or valve…" value={q} onChange={e => setQ(e.target.value)} />
            <span className="t-lbl" style={{ marginLeft: 'auto' }}>{rows.length} shown</span>
          </div>

          <div className="card">
            <table className="tbl">
              <thead>
                <tr>
                  <th>#</th><th>Order</th><th>Valve</th><th>Cust</th>
                  <th className="sortable" onClick={() => setSort('qty')}>Qty<Arrow col="qty" /></th>
                  <th className="sortable" onClick={() => setSort('due')}>Due in<Arrow col="due" /></th>
                  <th>Work</th>
                  <th className="sortable" onClick={() => setSort('cr')}>
                    Crit. ratio<InfoTip text="Time left ÷ time needed. Below 1 means not enough time — the order is at risk." /><Arrow col="cr" />
                  </th>
                  <th className="sortable" onClick={() => setSort('rank')}>Urgency<Arrow col="rank" /></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(o => {
                  const open = openRow === o.order_id
                  return (
                    <React.Fragment key={o.order_id}>
                      <tr className={`drill ${open ? 'open' : ''}`} onClick={() => setOpenRow(open ? null : o.order_id)}
                        style={o.at_risk ? { background: '#fdf3f2' } : undefined}>
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
                      </tr>
                      {open && (
                        <tr className="drillpanel">
                          <td colSpan={9}>
                            <div className="dp-inner">
                              <b>Why order {o.order_id} is ranked #{o.rank}:</b>
                              <div className="dp-grid">
                                <div className="dp-cell"><div className="k">Urgency score</div><div className="v">{o.score}/100</div></div>
                                <div className="dp-cell"><div className="k">Due in</div><div className="v">{o.days_to_due} days</div></div>
                                <div className="dp-cell"><div className="k">Work needed</div><div className="v">{o.processing_hours} h</div></div>
                                <div className="dp-cell"><div className="k">Critical ratio</div><div className="v" style={{ color: o.at_risk ? '#c0392b' : '#2e7d46' }}>{o.critical_ratio}</div></div>
                                <div className="dp-cell"><div className="k">Customer tier</div><div className="v">{o.tier}</div></div>
                                <div className="dp-cell"><div className="k">Quantity</div><div className="v">{o.quantity}</div></div>
                              </div>
                              <p className="muted" style={{ marginTop: 8 }}>{o.reasons.join(' · ')}</p>
                              {o.at_risk && (
                                <button className="btn-ghost" onClick={e => { e.stopPropagation(); navigate('risk', week) }}>
                                  See why it is at risk →
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
                {rows.length === 0 && <tr><td colSpan={9} className="muted" style={{ padding: 16 }}>No orders match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}
