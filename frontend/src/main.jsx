import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { authEnabled, msalConfig } from "./auth/authConfig";
import { DemoGate } from "./auth/gates";
import "./styles.css";

const root = ReactDOM.createRoot(document.getElementById("root"));

if (authEnabled) {
  // Real Entra ID single sign-on.
  Promise.all([
    import("@azure/msal-browser"),
    import("@azure/msal-react"),
    import("./auth/MsalGate.jsx"),
  ]).then(([{ PublicClientApplication }, { MsalProvider }, { MsalGate }]) => {
    const pca = new PublicClientApplication(msalConfig);
    pca.initialize().then(() => {
      const acct = pca.getAllAccounts()[0];
      if (acct) pca.setActiveAccount(acct);
      root.render(
        <React.StrictMode>
          <MsalProvider instance={pca}>
            <MsalGate><App /></MsalGate>
          </MsalProvider>
        </React.StrictMode>
      );
    });
  });
} else {
  // Local demo sign-in (no app registration required).
  root.render(
    <React.StrictMode>
      <DemoGate><App /></DemoGate>
    </React.StrictMode>
  );
}

