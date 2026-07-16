import { useState } from "react";
import { motion } from "framer-motion";

// Full-screen sign-in gate. `onLogin` triggers the Microsoft account picker (or demo sign-in).
export default function Login({ onLogin, demo }) {
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try { await onLogin(); } finally { setBusy(false); }
  }
  return (
    <div className="login-screen">
      <div className="login-bg">
        <span className="orb orb-1" /><span className="orb orb-2" /><span className="orb orb-3" />
      </div>
      <motion.div className="login-card"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
        <div className="login-logo">⬢</div>
        <h1 className="login-title">Production Planning</h1>
        <p className="login-sub">Schedule Optimization &amp; Intelligence Agent</p>
        <motion.button className="ms-btn" onClick={go} disabled={busy}
          whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
          {busy ? (
            <span className="ms-spin" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 21 21" aria-hidden="true">
              <rect x="1" y="1" width="9" height="9" fill="#F25022" />
              <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
              <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
              <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
            </svg>
          )}
          <span>{busy ? "Signing in…" : "Sign in with Microsoft"}</span>
        </motion.button>
        <p className="login-note">
          {demo
            ? "Demo mode — single sign-on activates once an Entra ID app is configured."
            : "Use your organisation account to continue."}
        </p>
      </motion.div>
      <div className="login-foot">Microsoft Agent Framework · Azure OpenAI</div>
    </div>
  );
}
