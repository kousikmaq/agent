import React, { useState } from 'react'
import { askAgent } from '../api'

const SAMPLES = [
  'Which week is the most overloaded?',
  'What is the bottleneck?',
  'How many weeks are overloaded?'
]

export default function AssistantWidget() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState([]) // {role:'me'|'bot', text, used_llm}

  async function send(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setMsgs(m => [...m, { role: 'me', text }])
    setQ(''); setBusy(true)
    try {
      const r = await askAgent(text)
      setMsgs(m => [...m, { role: 'bot', text: r.answer, used_llm: r.used_llm }])
    } catch (e) {
      setMsgs(m => [...m, { role: 'bot', text: 'Could not reach the assistant. Is the backend running on port 8001?' }])
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button className="fab" onClick={() => setOpen(true)}>
        <span className="ico">💬</span> Ask the assistant
      </button>
    )
  }

  return (
    <div className="assistant">
      <div className="ahead">
        <div>
          <div className="at">Planning copilot</div>
          <div className="as">Answers use real numbers from the engine</div>
        </div>
        <button className="x" onClick={() => setOpen(false)}>×</button>
      </div>

      <div className="body">
        {msgs.length === 0 && (
          <div className="muted" style={{ marginBottom: 10 }}>
            Ask about capacity, bottlenecks or which weeks are busy.
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role === 'me' ? 'me' : ''}`}>
            {m.role === 'bot' && m.used_llm !== undefined && (
              <div style={{ marginBottom: 6 }}>
                <span className={`tag ${m.used_llm ? 'llm' : 'fallback'}`}>
                  {m.used_llm ? 'Azure OpenAI' : 'engine (no key)'}
                </span>
              </div>
            )}
            {m.text}
          </div>
        ))}
        {busy && <div className="muted">Thinking…</div>}
      </div>

      <div className="foot">
        <div className="chips">
          {SAMPLES.map(s => <span key={s} className="chip" onClick={() => send(s)}>{s}</span>)}
        </div>
        <div className="arow">
          <input
            placeholder="Type a question…"
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
          />
          <button className="btn" disabled={busy} onClick={() => send()}>Send</button>
        </div>
      </div>
    </div>
  )
}
