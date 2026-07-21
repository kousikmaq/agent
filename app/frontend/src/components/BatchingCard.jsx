import React from 'react'

export default function BatchingCard({ batching }) {
  return (
    <div className="card">
      <h3>Batch / campaign insight</h3>
      <div className="stat">
        <div className="label">Setup hours saved if same-item orders run as one campaign</div>
        <div className="value green">{batching.setup_hours_saved.toFixed(1)} h</div>
        <div className="sub">
          {batching.naive_setup_hours.toFixed(1)} h of setups &rarr; {batching.batched_setup_hours.toFixed(1)} h when batched
        </div>
      </div>
      <p className="muted" style={{ marginTop: 10 }}>
        Grouping orders of the same valve into a single production run means the machine is set up
        once instead of once per order. That freed time goes straight back to the bottleneck.
      </p>
    </div>
  )
}
