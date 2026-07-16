import { useState } from "react";
import { motion } from "framer-motion";
import { ALLOWED_DOMAIN, isAllowedEmail } from "./authConfig";

// Email-only sign-in. Only addresses on the company domain are allowed.
export default function Login({ onLogin, lastEmail = "" }) {
  const [email, setEmail] = useState(lastEmail);
  const [error, setError] = useState("");

  function submit(e) {
    e.preventDefault();
    const value = email.trim().toLowerCase();
    if (!isAllowedEmail(value)) {
      setError(`Please use your @${ALLOWED_DOMAIN} email address.`);
      return;
    }
    setError("");
    onLogin(value);
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
        <h1 className="login-title">Production &amp; Scheduling Assistant</h1>
        <p className="login-sub">Sign in with your work email to continue</p>

        <form onSubmit={submit} className="login-form">
          <input
            className="login-input"
            type="email"
            autoFocus
            placeholder={`you@${ALLOWED_DOMAIN}`}
            value={email}
            onChange={(e) => { setEmail(e.target.value); setError(""); }}
          />
          {error && <div className="login-error">{error}</div>}
          <motion.button type="submit" className="login-submit"
            whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
            Continue →
          </motion.button>
        </form>

        <p className="login-note">Access is restricted to <b>@{ALLOWED_DOMAIN}</b> accounts.</p>
      </motion.div>
      <div className="login-foot">Microsoft Agent Framework · Azure OpenAI</div>
    </div>
  );
}
