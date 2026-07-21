import React from 'react'

export default function OrdersTable({ orders }) {
  const shown = orders.slice(0, 12)
  return (
    <div className="card">
      <h3>Orders due this week ({orders.length})</h3>
      <table className="tbl">
        <thead>
          <tr>
            <th>Order</th><th>Valve</th><th>Qty</th><th>Due</th><th>Priority</th>
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
      {orders.length > shown.length && (
        <p className="muted" style={{ marginTop: 8 }}>Showing first {shown.length} of {orders.length} orders.</p>
      )}
    </div>
  )
}
