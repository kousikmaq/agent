import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { EmailGate } from "./auth/gates";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <EmailGate>
      <App />
    </EmailGate>
  </React.StrictMode>
);


