import { useState } from "react";
import { AuthContext } from "./authContext";
import { nameFromEmail } from "./authConfig";
import Login from "./Login";

const USER_KEY = "pp_user";
const LAST_EMAIL_KEY = "pp_last_email";

// Email-only gate. Only company-domain addresses may sign in. The session is cached in
// localStorage so returning users are signed in automatically without re-entering their email.
export function EmailGate({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; }
  });

  function login(email) {
    const e = email.trim().toLowerCase();
    const u = { name: nameFromEmail(e), username: e };
    localStorage.setItem(USER_KEY, JSON.stringify(u));
    localStorage.setItem(LAST_EMAIL_KEY, e);
    setUser(u);
  }
  function logout() {
    localStorage.removeItem(USER_KEY); // keep LAST_EMAIL_KEY so the field stays pre-filled
    setUser(null);
  }

  if (!user) return <Login onLogin={login} lastEmail={localStorage.getItem(LAST_EMAIL_KEY) || ""} />;
  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}


