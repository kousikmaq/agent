import React from 'react'

// Small hoverable "?" that explains a term in plain language.
// Used across pages so people new to manufacturing can understand each metric.
export default function InfoTip({ text, label }) {
  return (
    <span className="infotip" tabIndex={0} role="button" aria-label={text}>
      <span className="infotip-ico">{label || 'i'}</span>
      <span className="infotip-bubble">{text}</span>
    </span>
  )
}
