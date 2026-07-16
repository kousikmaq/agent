import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { AuthContext } from "./authContext";
import { loginRequest } from "./authConfig";
import Login from "./Login";

// Real Entra ID gate: shows the Microsoft account picker, then provides the user to the app.
// Loaded lazily so MSAL is only bundled when SSO is configured.
export function MsalGate({ children }) {
  const { instance, accounts } = useMsal();
  const isAuthed = useIsAuthenticated();

  async function login() {
    try { await instance.loginPopup(loginRequest); }
    catch (e) { console.error("Sign-in failed", e); }
  }
  function logout() {
    const account = instance.getActiveAccount() || accounts[0];
    instance.logoutPopup({ account }).catch(() => {});
  }

  if (!isAuthed) return <Login onLogin={login} />;

  const acct = accounts[0] || {};
  const user = { name: acct.name || acct.username || "User", username: acct.username || "" };
  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}
