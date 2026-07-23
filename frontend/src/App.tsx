import { useEffect, useRef, useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { ShopFloorPage } from "./pages/ShopFloorPage";
import { Toaster } from "./components/Toast";
import { LoginPage } from "./components/LoginPage";
import { AuthProvider, useAuth } from "./auth/useAuth";

type Page = "planning" | "shopfloor";

/** User menu shown top-right once signed in. */
function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (!user) return null;
  const initials = user.name
    .split(" ")
    .map((p) => p.charAt(0))
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="user-menu" ref={ref}>
      <button className="user-chip" onClick={() => setOpen((o) => !o)}>
        <span className="user-avatar">{initials}</span>
        <span className="user-caret" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <div className="user-dropdown">
          <div className="user-dropdown-head">
            <div className="user-dropdown-name">{user.name}</div>
            <div className="user-dropdown-email">{user.email}</div>
          </div>
          <button className="user-signout" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/** Authenticated application shell (nav + pages). */
function Workspace() {
  const [page, setPage] = useState<Page>("planning");
  // A tab to open on the planning page (e.g. from a Live Ops "view materials").
  const [planningTab, setPlanningTab] = useState<string | null>(null);

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
        <UserMenu />
      </nav>
      {page === "planning" ? (
        <DashboardPage
          requestedTab={planningTab}
          onRequestedTabConsumed={() => setPlanningTab(null)}
        />
      ) : (
        <ShopFloorPage
          onViewMaterials={() => {
            setPlanningTab("materials");
            setPage("planning");
          }}
        />
      )}
      <Toaster />
    </div>
  );
}

/** Gate the workspace behind sign-in. */
function Gate() {
  const { user } = useAuth();
  return user ? <Workspace /> : <LoginPage />;
}

/** Application root. */
export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
