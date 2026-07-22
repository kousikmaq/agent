/**
 * Login screen. A classy, minimal sign-in gate: enter a corporate email
 * (@maqsoftware.com) to continue. The last-used address is pre-filled and the
 * browser can autofill it too.
 */
import { useState, type FormEvent } from "react";
import { ALLOWED_DOMAIN, useAuth } from "../../auth/useAuth";

export function LoginPage() {
  const { signIn, lastEmail } = useAuth();
  const [email, setEmail] = useState(lastEmail ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const result = signIn(email);
    if (!result.ok) {
      setError(result.error ?? "Sign-in failed.");
      setBusy(false);
    }
    // On success the AuthProvider re-renders and unmounts this page.
  };

  return (
    <div className="login-shell">
      <div className="login-aurora" aria-hidden />
      <form className="login-card" onSubmit={onSubmit}>
        <div className="login-brand">
          <span className="login-logo">◆</span>
          <span className="login-brand-name">PPO Agent</span>
        </div>
        <h1 className="login-title">Production Planning &amp; Optimization</h1>
        <p className="login-sub">
          Sign in with your company account to access the planning workspace.
        </p>

        <label className="login-field">
          <span>Work email</span>
          <input
            type="email"
            name="email"
            autoComplete="email"
            inputMode="email"
            placeholder={`you@${ALLOWED_DOMAIN}`}
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (error) setError(null);
            }}
            autoFocus
            required
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button className="login-submit" type="submit" disabled={busy}>
          <span>Continue</span>
          <span className="login-arrow" aria-hidden>
            →
          </span>
        </button>

        <p className="login-hint">
          Access is limited to <strong>@{ALLOWED_DOMAIN}</strong> accounts.
        </p>
      </form>
    </div>
  );
}
