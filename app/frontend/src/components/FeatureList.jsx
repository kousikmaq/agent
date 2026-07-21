import React from 'react'

export default function FeatureList({ features }) {
  return (
    <div className="card">
      <h3>Features (what is live vs. planned)</h3>
      {features.map(f => (
        <div className="feature" key={f.key}>
          <span className={`badge ${f.status === 'implemented' ? 'live' : 'planned'}`}>
            {f.status === 'implemented' ? 'LIVE' : 'PLANNED'}
          </span>
          <div>
            <div className="fname">{f.name}</div>
            <div className="fdesc">{f.description}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
