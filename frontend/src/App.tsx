import { useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { ShopFloorPage } from "./pages/ShopFloorPage";

type Page = "planning" | "shopfloor";

/** Application root. Switches between the Planning and Shop Floor pages. */
export default function App() {
  const [page, setPage] = useState<Page>("planning");

  return (
    <div className="shell">
      <nav className="top-nav">
        <span className="brand">PPO Agent</span>
        <div className="top-nav-links">
          <button
            className={page === "planning" ? "nav-link active" : "nav-link"}
            onClick={() => setPage("planning")}
          >
            Planning
          </button>
          <button
            className={page === "shopfloor" ? "nav-link active" : "nav-link"}
            onClick={() => setPage("shopfloor")}
          >
            Live Operations
          </button>
        </div>
      </nav>
      {page === "planning" ? <DashboardPage /> : <ShopFloorPage />}
    </div>
  );
}
