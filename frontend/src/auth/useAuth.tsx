/**
 * Lightweight client-side authentication.
 *
 * For now this is a local gate: any email on the allowed corporate domain may
 * sign in. The signed-in user is persisted in localStorage so returning users
 * stay signed in, and their address is remembered to pre-fill the login form.
 *
 * NOTE: This is a convenience gate, not a security boundary. It performs no
 * server-side verification; protected data should still be secured server-side.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/** Domain allowed to sign in. */
export const ALLOWED_DOMAIN = "maqsoftware.com";

const USER_KEY = "ppo_user";
const LAST_EMAIL_KEY = "ppo_last_email";

export interface User {
  email: string;
  name: string;
}

interface AuthState {
  user: User | null;
  lastEmail: string | null;
  signIn: (email: string) => { ok: boolean; error?: string };
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

/** Turn an email into a friendly display name ("kousikm" → "Kousikm"). */
function nameFromEmail(email: string): string {
  const local = email.split("@")[0] ?? email;
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

/** Validate an email and its domain. Returns an error message when invalid. */
export function validateEmail(email: string): string | null {
  const trimmed = email.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
    return "Please enter a valid email address.";
  }
  if (!trimmed.endsWith(`@${ALLOWED_DOMAIN}`)) {
    return `Only @${ALLOWED_DOMAIN} accounts can sign in.`;
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [lastEmail, setLastEmail] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(USER_KEY);
      if (raw) setUser(JSON.parse(raw) as User);
      setLastEmail(localStorage.getItem(LAST_EMAIL_KEY));
    } catch {
      /* ignore corrupt storage */
    }
  }, []);

  const signIn = useCallback((email: string) => {
    const error = validateEmail(email);
    if (error) return { ok: false, error };
    const normalized = email.trim().toLowerCase();
    const next: User = { email: normalized, name: nameFromEmail(normalized) };
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(next));
      localStorage.setItem(LAST_EMAIL_KEY, normalized);
    } catch {
      /* storage may be unavailable; sign in for the session anyway */
    }
    setUser(next);
    setLastEmail(normalized);
    return { ok: true };
  }, []);

  const signOut = useCallback(() => {
    try {
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, lastEmail, signIn, signOut }),
    [user, lastEmail, signIn, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
