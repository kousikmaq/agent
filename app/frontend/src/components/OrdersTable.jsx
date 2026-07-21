import React, { useState } from 'react'
import InfoTip from './InfoTip'

const PRIO_RANK = { High: 0, Normal: 1, Low: 2 }

export default function OrdersTable({ orders }) {
  const [sort, setSort] = useState('due')   // due | qty | priority | order
  const [dir, setDir] = useState('asc')
  const [all, setAll] = useState(false)

  function toggle(col) {
    if (sort === col) setDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSort(col); setDir('asc') }
  }

  const sorters = {
    order: (a, b) => a.order_id.localeCompare(b.order_id),
    qty: (a, b) => a.quantity - b.quantity,
    due: (a, b) => a.due_date.localeCompare(b.due_date),
    priority: (a, b) => (PRIO_RANK[a.priority] ?? 9) - (PRIO_RANK[b.priority] ?? 9),
  }
  const sorted = [...orders].sort(sorters[sort])
  if (dir === 'desc') sorted.reverse()
  const shown = all ? sorted : sorted.slice(0, 12)

  const Arrow = ({ col }) => sort === col ? <span className="sortarrow">{dir === 'asc' ? '▲' : '▼'}</span> : null

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>
          Orders due this week ({orders.length})
          <InfoTip text="Every active order due in this week. Click a column header to sort by quantity, due date or priority." />
        </h3>
        {orders.length > 12 && (
          <button className="chipbtn" onClick={() => setAll(a => !a)}>{all ? 'Show first 12' : `Show all ${orders.length}`}</button>
        )}
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th className="sortable" onClick={() => toggle('order')}>Order<Arrow col="order" /></th>
            <th>Valve</th>
            <th className="sortable" onClick={() => toggle('qty')}>Qty<Arrow col="qty" /></th>
            <th className="sortable" onClick={() => toggle('due')}>Due<Arrow col="due" /></th>
            <th className="sortable" onClick={() => toggle('priority')}>Priority<Arrow col="priority" /></th>
          </tr>
        </thead>
        <tbody>
          {shown.map(o => (
            <tr key={o.order_id}>
              <td>{o.order_id}</td>
              <td>{o.item_name}</td>
              <td>{o.quantity}</td>
              <td>{o.due_date}</td>
              <td><span className={`pill ${o.priority}`}>{o.priority}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!all && orders.length > shown.length && (
        <p className="muted" style={{ marginTop: 8 }}>Showing first {shown.length} of {orders.length} orders — sorted by {sort} ({dir}).</p>
      )}
    </div>
  )
}
