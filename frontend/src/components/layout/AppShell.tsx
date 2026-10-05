import type { ReactNode } from "react";
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
  isOutcomes,
  reportId,
  busy,
  onRefresh,
  children,
}: {
  total: number | null;
  ready: boolean;
  isOutcomes: boolean;
  reportId?: string;
  busy: string;
  onRefresh: () => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
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
            <strong>Local workspace</strong>
            <small>Infrastructure review</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <a href="#/reviews" className={!isOutcomes ? "active" : ""}>
            <GitPullRequest size={18} />
            Reviews<span className="nav-count">{total ?? "—"}</span>
          </a>
          <a href="#/outcomes" className={isOutcomes ? "active" : ""}>
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
              {ready ? "Local backend ready" : "Connecting to backend"}
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
            <span className="local-pill">LOCAL / DEMO</span>
            <button
              className="icon-button"
              aria-label="Refresh backend data"
              onClick={onRefresh}
            >
              <RefreshCw
                size={17}
                className={busy === "refresh" ? "spin" : ""}
              />
            </button>
            <span className="avatar" title="Local demo operator">
              LO
            </span>
          </div>
        </header>
        <main>
          {children}
          <footer className="page-footer">
            <span>ProofOps · evidence before change</span>
            <span>
              Local, single-service review · estimates and observations stay
              separate
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
