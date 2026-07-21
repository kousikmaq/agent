import React from 'react'

export default function RecommendationsCard({ recommendations }) {
  return (
    <div className="card">
      <h3>Recommended actions</h3>
      {recommendations.length === 0 ? (
        <p className="muted">No offload needed this week — nothing is overloaded, or no free backup machine is available.</p>
      ) : (
        recommendations.map((r, i) => (
          <div className="rec" key={i}>
            <span className="rec-ico">↪</span>
            <div>
              <div className="rec-t">{r.from_wc} → {r.to_wc}</div>
              <div className="rec-d">{r.text}</div>
            </div>
          </div>
        ))
      )}
      <p className="muted" style={{ marginTop: 8 }}>
        Backups come from each product's routing (its listed alternate machine).
      </p>
    </div>
  )
}
