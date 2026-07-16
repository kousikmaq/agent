// MSAL configuration. Real Entra ID (Azure AD) SSO activates when VITE_AAD_CLIENT_ID is set
// (register an SPA app with redirect URI = this app's origin). Until then the app runs in a
// local demo sign-in mode so the UI is fully usable and testable.
const clientId = import.meta.env.VITE_AAD_CLIENT_ID || "";
const tenant = import.meta.env.VITE_AAD_TENANT || "organizations";

export const authEnabled = Boolean(clientId);

export const msalConfig = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenant}`,
    redirectUri: typeof window !== "undefined" ? window.location.origin : "/",
    postLogoutRedirectUri: typeof window !== "undefined" ? window.location.origin : "/",
  },
  cache: { cacheLocation: "sessionStorage", storeAuthStateInCookie: false },
};

// Scopes requested at sign-in. User.Read lets us read the signed-in user's profile name.
export const loginRequest = { scopes: ["User.Read"] };
