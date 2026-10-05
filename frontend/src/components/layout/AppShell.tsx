import type { ReactNode } from "react";
import { useAuth } from "../../features/auth/AuthGate";
import {
  Activity,
  ChevronRight,
  GitPullRequest,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

export function AppShell({
  total,
  ready,
  loading,
  isOutcomes,
  reportId,
  busy,
  onRefresh,
  children,
}: {
  total: number | null;
  ready: boolean;
  loading: boolean;
  isOutcomes: boolean;
  reportId?: string;
  busy: string;
  onRefresh: () => void;
  children: ReactNode;
}) {
  const { session, logout, signingOut } = useAuth();
  return (
    <div className="app-shell">
      <a
        href="#main-content"
        className="skip-link"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className="sidebar">
        <a className="brand" href="#/reviews" aria-label="ProofOps home">
          <span className="brand-mark">
            <ShieldCheck size={25} />
          </span>
          <span>
            ProofOps<span className="brand-dot">.</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">P</span>
          <div>
            <strong>{session.public_demo ? "Public demo" : "Workspace"}</strong>
            <small>Infrastructure review</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <a
            href="#/reviews"
            className={!isOutcomes ? "active" : ""}
            aria-current={!isOutcomes ? "page" : undefined}
          >
            <GitPullRequest size={18} />
            Reviews<span className="nav-count">{total ?? "—"}</span>
          </a>
          <a
            href="#/outcomes"
            className={isOutcomes ? "active" : ""}
            aria-current={isOutcomes ? "page" : undefined}
          >
            <Activity size={18} />
            Outcomes
          </a>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={19} />
          <strong>Evidence before change.</strong>
          <p>
            Connect each proposed saving to a workload contract and an
            inspectable result.
          </p>
        </div>
        <div className="sidebar-bottom">
          <span className={`connection-dot ${ready ? "connected" : ""}`} />
          <div>
            <strong>
              {ready
                ? "Backend ready"
                : loading
                  ? "Connecting to backend"
                  : "Backend unavailable"}
            </strong>
            <small>Advisory · no deployment access</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <span>
              {isOutcomes ? "Outcomes" : reportId ? "Review detail" : "Reviews"}
            </span>
          </div>
          <div className="topbar-right">
            <span className="local-pill">
              {session.public_demo
                ? "DEMO · READ-ONLY"
                : session.role === "admin"
                  ? "ADMIN"
                  : "VIEWER · READ-ONLY"}
            </span>
            <button
              className="icon-button"
              aria-label="Refresh backend data"
              disabled={!!busy}
              onClick={onRefresh}
            >
              <RefreshCw
                size={17}
                className={busy === "refresh" ? "spin" : ""}
              />
            </button>
            {!session.public_demo && (
              <button
                className="button secondary small sign-out"
                onClick={() => {
                  void logout();
                }}
                disabled={signingOut}
              >
                Sign out
              </button>
            )}
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          {children}
          <footer className="page-footer">
            <span>ProofOps · evidence before change</span>
            <span>
              Single-service review · estimates and observations stay separate
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
