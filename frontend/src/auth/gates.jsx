import { useState } from "react";
import { AuthContext } from "./authContext";
import Login from "./Login";

// Demo gate used when no Entra ID app is configured. Signs in as the local user so the whole
// experience is usable and testable end-to-end.
export function DemoGate({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("demo_user") || "null"); } catch { return null; }
  });
  function login() {
    const u = { name: "Kousik Maity", username: "kousikm@maqsoftware.com" };
    sessionStorage.setItem("demo_user", JSON.stringify(u));
    setUser(u);
  }
  function logout() {
    sessionStorage.removeItem("demo_user");
    setUser(null);
  }
  if (!user) return <Login onLogin={login} demo />;
  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}

