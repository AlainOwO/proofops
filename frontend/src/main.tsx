import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  Download,
  FileCheck2,
  GitPullRequest,
  Info,
  Layers,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  XCircle,
} from "lucide-react";
import { api, date, money, originLabel } from "./api";
import type { Analytics, CoreReport, Detail, Outcome, Summary } from "./types";
import "./styles.css";

const outcomes: Record<
  Outcome,
  { label: string; short: string; icon: typeof CheckCircle2; className: string }
> = {
  request_review: {
    label: "Ready for engineering review",
    short: "Ready for review",
    icon: CheckCircle2,
    className: "ready",
  },
  revise_change: {
    label: "Revise the change",
    short: "Revise change",
    icon: XCircle,
    className: "revise",
  },
  collect_evidence: {
    label: "Collect more evidence",
    short: "Needs evidence",
    icon: Clock3,
    className: "collect",
  },
  out_of_scope: {
    label: "Outside supported scope",
    short: "Out of scope",
    icon: Info,
    className: "outside",
  },
};
function Badge({
  outcome,
  state,
}: {
  outcome: Outcome | null;
  state?: string;
}) {
  const entry = outcome ? outcomes[outcome] : null;
  const Icon = entry?.icon || LoaderCircle;
  return (
    <span className={`badge ${entry?.className || "outside"}`}>
      <Icon size={13} />
      {entry?.short || state || "Queued"}
    </span>
  );
}
function Origin({ value }: { value: string | null }) {
  return (
    <span className="origin">
      <Layers size={12} />
      {originLabel[value || ""] || "Awaiting report"}
    </span>
  );
}
function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <FileCheck2 size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Metric({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  note: string;
  accent?: boolean;
}) {
  return (
    <div className={`metric ${accent ? "accent" : ""}`}>
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
function memory(value: number | null | undefined) {
  return value == null ? "Unknown" : `${(value / 1024).toLocaleString()} GiB`;
}
function cpu(value: number | null | undefined) {
  return value == null ? "Unknown" : `${value / 1024} vCPU`;
}
function human(value: string) {
  return value.replaceAll("_", " ");
}

function App() {
  const [route, setRoute] = useState(
    window.location.hash.slice(1) || "/reviews",
  );
  const [reviews, setReviews] = useState<Summary[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [replay, setReplay] = useState("valid-resize");
  const [file, setFile] = useState<File | null>(null);
  const [ai, setAi] = useState("off");
  const [mode, setMode] = useState("replay");
  const [ready, setReady] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const reportId = route.match(/^\/reviews\/([a-f0-9-]{36})/)?.[1];
  const isOutcomes = route === "/outcomes";
  const routeRef = useRef(route);
  routeRef.current = route;
  const navigate = (value: string) => {
    window.location.hash = value;
  };
  useEffect(() => {
    const listener = () =>
      setRoute(window.location.hash.slice(1) || "/reviews");
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);

  const refresh = useCallback(async () => {
    const [listing, stats, health] = await Promise.all([
      api<{ items: Summary[]; total: number }>("/api/v1/reviews?limit=100"),
      api<Analytics>("/api/v1/analytics"),
      api<{ status: string }>("/readyz"),
    ]);
    setReviews(listing.items);
    setTotal(listing.total);
    setAnalytics(stats);
    setReady(health.status === "ready");
    setLoaded(true);
  }, []);
  useEffect(() => {
    refresh().catch((error) => {
      setError(error.message);
      setLoaded(true);
      setReady(false);
    });
  }, [refresh]);
  const refreshDetail = useCallback(async () => {
    if (!reportId) return;
    const suffix = route.includes("?") ? "?" + route.split("?")[1] : "";
    const response = await api<Detail>(`/api/v1/reviews/${reportId}${suffix}`);
    if (routeRef.current === route) setDetail(response);
    return response;
  }, [reportId, route]);
  useEffect(() => {
    if (!reportId) {
      setDetail(null);
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    setDetail(null);
    const poll = async () => {
      try {
        const value = await refreshDetail();
        if (
          !stopped &&
          value &&
          ["queued", "running"].includes(value.job.state)
        )
          timer = setTimeout(poll, 700);
        else if (!stopped) await refresh();
      } catch (error) {
        if (!stopped) setError((error as Error).message);
      }
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [reportId, refreshDetail, refresh]);

  async function runReview() {
    setError("");
    setBusy("review");
    try {
      const imported = file
        ? await api<{ bundle_id: string }>("/api/v1/bundles", {
            method: "POST",
            headers: { "Content-Type": "application/zip" },
            body: file,
          })
        : await api<{ bundle_id: string }>("/api/v1/bundles", {
            method: "POST",
            body: JSON.stringify({ replay }),
          });
      const queued = await api<{ review_id: string }>("/api/v1/reviews", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          bundle_id: imported.bundle_id,
          mode,
          ai_preference: ai,
        }),
      });
      navigate(`/reviews/${queued.review_id}`);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function action(key: string, callback: () => Promise<unknown>) {
    setBusy(key);
    setError("");
    try {
      await callback();
      await refreshDetail();
      await refresh();
      return true;
    } catch (error) {
      setError((error as Error).message);
      return false;
    } finally {
      setBusy("");
    }
  }
  const count = (value: Outcome) =>
    analytics ? (analytics.review_counts[value] ?? 0) : "Unavailable";
  const filtered = reviews.filter((item) =>
    `${item.service} ${item.candidate_commit} ${item.outcome} ${item.state}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

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
              onClick={() => action("refresh", refresh)}
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
          {error && (
            <div role="alert" className="error-banner">
              <XCircle size={18} />
              <div>
                <strong>Something needs attention</strong>
                <p>{error}</p>
              </div>
              <button className="text-button" onClick={() => setError("")}>
                Dismiss
              </button>
            </div>
          )}
          {reportId ? (
            detail?.report ? (
              <ReportDetail
                detail={detail}
                busy={busy}
                onBack={() => navigate("/reviews")}
                onDraft={() =>
                  action("draft", () =>
                    api(`/api/v1/reviews/${reportId}/guard-drafts`, {
                      method: "POST",
                      body: JSON.stringify({ ai_preference: "off" }),
                    }),
                  )
                }
                onValidate={(id) =>
                  action("validate", () =>
                    api(`/api/v1/guard-drafts/${id}/validate`, {
                      method: "POST",
                    }),
                  )
                }
                onCompareCommit={(commit) =>
                  navigate(
                    `/reviews/${reportId}?candidate_commit=${encodeURIComponent(commit)}`,
                  )
                }
                onDisposition={(disposition, reason) =>
                  action("outcome", () => {
                    const now = new Date().toISOString();
                    return api(`/api/v1/reviews/${reportId}/outcomes`, {
                      method: "POST",
                      body: JSON.stringify({
                        candidate_commit:
                          detail.report!.change.service_map.candidate_commit,
                        disposition,
                        reason,
                        origin: detail.report!.origin,
                        observed_start: now,
                        observed_end: now,
                        cost_basis: "not_measured",
                        evidence_ids: [],
                      }),
                    });
                  })
                }
              />
            ) : (
              <div className="job-view">
                <button
                  className="back-link"
                  onClick={() => navigate("/reviews")}
                >
                  <ArrowLeft size={16} />
                  All reviews
                </button>
                <div className="panel job-panel">
                  {detail?.job.state === "failed" ? (
                    <XCircle size={34} />
                  ) : (
                    <LoaderCircle className="spin" size={34} />
                  )}
                  <h1>
                    {detail?.job.state === "failed"
                      ? "Review could not complete"
                      : "Building the evidence report"}
                  </h1>
                  <p>
                    {detail
                      ? `Job ${detail.job.state} · ${human(detail.job.stage)}`
                      : "Loading review state…"}
                  </p>
                  {detail?.job.error_code && (
                    <code>{detail.job.error_code}</code>
                  )}
                  <p className="muted">
                    A queued job needs the ProofOps worker running. Completed
                    findings will appear here.
                  </p>
                </div>
              </div>
            )
          ) : isOutcomes ? (
            <Outcomes
              data={analytics}
              busy={busy}
              onLoadSample={() =>
                action("billing", () =>
                  api("/api/v1/billing/import-sample", { method: "POST" }),
                )
              }
              onOpen={(id) => navigate(`/reviews/${id}`)}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">CHANGE INTELLIGENCE</div>
                  <h1>Review with evidence.</h1>
                  <p>
                    Understand the saving. Check the contract. Make the next
                    decision.
                  </p>
                </div>
                <button
                  className="button primary"
                  onClick={() =>
                    document.getElementById("replay-choice")?.focus()
                  }
                >
                  <Plus size={16} />
                  New review
                </button>
              </div>
              <div className="metric-grid four">
                <Metric
                  label="TOTAL REVIEWS"
                  value={total ?? "Unavailable"}
                  note="Saved in this workspace"
                />
                <Metric
                  label="READY FOR REVIEW"
                  value={count("request_review")}
                  note="Required checks passed"
                  accent
                />
                <Metric
                  label="CHANGES TO REVISE"
                  value={count("revise_change")}
                  note="Known contract violations"
                />
                <Metric
                  label="NEED MORE EVIDENCE"
                  value={count("collect_evidence")}
                  note="Incomplete or incompatible inputs"
                />
              </div>
              <div className="review-layout">
                <section className="panel reviews-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Recent reviews</h2>
                      <p>
                        {loaded
                          ? `Latest ${reviews.length} of ${total} reviews`
                          : "Loading backend state…"}
                      </p>
                    </div>
                    <label className="search">
                      <Search size={15} />
                      <input
                        aria-label="Filter displayed reviews"
                        placeholder="Filter reviews"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                      />
                    </label>
                  </div>
                  {!filtered.length ? (
                    <Empty
                      title={
                        query
                          ? "No matching reviews"
                          : !loaded
                            ? "Loading reviews"
                            : total === null
                              ? "Reviews unavailable"
                              : "Your first review starts here"
                      }
                    >
                      {query
                        ? "Try another service, commit or outcome."
                        : "Run a supplied replay or import a sanitized bundle to see the evidence behind a change."}
                    </Empty>
                  ) : (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Service / change</th>
                            <th>Decision</th>
                            <th>Evidence origin</th>
                            <th aria-label="Open review" />
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.map((item) => (
                            <tr key={item.id}>
                              <td>
                                <button
                                  className="review-link"
                                  onClick={() =>
                                    navigate(`/reviews/${item.id}`)
                                  }
                                >
                                  {item.service || "Queued review"}
                                  <span>
                                    <code>
                                      {item.candidate_commit?.slice(0, 8) ||
                                        item.id.slice(0, 8)}
                                    </code>{" "}
                                    · {date(item.created_at)}
                                  </span>
                                </button>
                              </td>
                              <td>
                                <Badge
                                  outcome={item.outcome}
                                  state={human(item.state)}
                                />
                              </td>
                              <td>
                                <Origin value={item.origin} />
                              </td>
                              <td>
                                <button
                                  className="icon-button"
                                  aria-label={`Open review ${item.id}`}
                                  onClick={() =>
                                    navigate(`/reviews/${item.id}`)
                                  }
                                >
                                  <ArrowUpRight size={17} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
                <aside className="panel start-panel">
                  <div className="start-icon">
                    <Layers size={23} />
                  </div>
                  <h2>Start with a replay</h2>
                  <p>
                    Explore a complete review with labelled synthetic evidence.
                    No credentials needed.
                  </p>
                  <label htmlFor="replay-choice">Review scenario</label>
                  <select
                    id="replay-choice"
                    value={replay}
                    disabled={!!file}
                    onChange={(event) => setReplay(event.target.value)}
                  >
                    <option value="valid-resize">
                      Valid resize · 4 GiB → 2 GiB
                    </option>
                    <option value="unsafe-resize">
                      Below the floor · 4 GiB → 1 GiB
                    </option>
                    <option value="incomplete-evidence">
                      Missing candidate evidence
                    </option>
                  </select>
                  <div className="fixture-note">
                    <Info size={14} />
                    <span>
                      Prices, approvals and workload results in these examples
                      are synthetic.
                    </span>
                  </div>
                  <details className="advanced">
                    <summary>Import or configure a review</summary>
                    <label className="file-upload">
                      <Upload size={15} />
                      <span>
                        {file?.name || "Choose an input bundle (.zip)"}
                      </span>
                      <input
                        type="file"
                        accept=".zip"
                        aria-label="Upload input bundle"
                        onChange={(event) =>
                          setFile(event.target.files?.[0] || null)
                        }
                      />
                    </label>
                    {file && (
                      <button
                        className="text-button"
                        onClick={() => setFile(null)}
                      >
                        Use supplied replay instead
                      </button>
                    )}
                    <label htmlFor="execution-mode">Evaluation time</label>
                    <select
                      id="execution-mode"
                      value={mode}
                      onChange={(event) => setMode(event.target.value)}
                    >
                      <option value="replay">Recorded replay time</option>
                      <option value="live">
                        Current decision · AWS evidence required
                      </option>
                    </select>
                    <label htmlFor="ai-mode">Explanation</label>
                    <select
                      id="ai-mode"
                      value={ai}
                      onChange={(event) => setAi(event.target.value)}
                    >
                      <option value="off">
                        Deterministic template · no AI call
                      </option>
                      <option value="auto">
                        Use configured model and budget
                      </option>
                    </select>
                  </details>
                  <button
                    className="button primary full"
                    onClick={runReview}
                    disabled={!!busy}
                  >
                    {busy === "review" ? (
                      <LoaderCircle size={16} className="spin" />
                    ) : (
                      <FileCheck2 size={16} />
                    )}
                    Run review
                    <ArrowRight size={16} />
                  </button>
                  <div className="start-footer">
                    <ShieldCheck size={13} />
                    The report requests engineering review.
                  </div>
                </aside>
              </div>
              <div className="workflow-strip">
                <span className="eyebrow">THE REVIEW PATH</span>
                <span>
                  <span className="step-number">1</span>Proposed change
                </span>
                <ArrowRight size={15} />
                <span>
                  <span className="step-number">2</span>Cost + workload evidence
                </span>
                <ArrowRight size={15} />
                <span>
                  <span className="step-number">3</span>Approved constraints
                </span>
                <ArrowRight size={15} />
                <span>
                  <span className="step-number">4</span>Engineering review
                </span>
              </div>
            </>
          )}
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

function ReportDetail({
  detail,
  busy,
  onBack,
  onDraft,
  onValidate,
  onCompareCommit,
  onDisposition,
}: {
  detail: Detail;
  busy: string;
  onBack: () => void;
  onDraft: () => void;
  onValidate: (id: string) => void;
  onCompareCommit: (commit: string) => void;
  onDisposition: (disposition: string, reason: string) => Promise<boolean>;
}) {
  const r = detail.report as CoreReport;
  const entry = outcomes[r.outcome];
  const Icon = entry.icon;
  const cost = r.cost;
  const scope = r.change.service_map.scope;
  const explanation =
    detail.explanation?.output || detail.explanation?.fallback?.output;
  const floor = r.facts.find(
    (item) => item.fact_id === "approved.minimum_task_memory_mib",
  )?.value;
  const draft = detail.guard_drafts?.[0];
  const [commit, setCommit] = useState("");
  const [disposition, setDisposition] = useState("rejected");
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);
  const revisionInvalid =
    detail.applicability?.candidate_changed ||
    detail.applicability?.policy_changed;
  return (
    <>
      <div className="report-nav">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} />
          All reviews
        </button>
        <a
          className="button secondary small"
          href={`/api/v1/reviews/${r.review_id}/bundle`}
          download
        >
          <Download size={15} />
          Export review bundle
        </a>
      </div>
      <div className="page-heading report-heading">
        <div>
          <div className="eyebrow">
            EVIDENCE REPORT ·{" "}
            <code>{r.change.service_map.candidate_commit.slice(0, 8)}</code>
          </div>
          <h1>
            {scope.service}
            <span className="heading-separator">/</span>Task resize
          </h1>
          <p>
            {scope.region} <span className="dot-separator">·</span>{" "}
            {scope.environment} <span className="dot-separator">·</span>{" "}
            <Origin value={r.origin} />
          </p>
        </div>
        <div className="report-date">
          Evaluated at recorded {r.mode === "replay" ? "replay" : "decision"}{" "}
          time<strong>{date(r.evaluation_reference_time)}</strong>
        </div>
      </div>
      <div className={`decision-banner ${entry.className}`}>
        <span className="decision-icon">
          <Icon size={26} />
        </span>
        <div>
          <span className="eyebrow">
            {revisionInvalid
              ? "HISTORICAL RESULT · APPLICABILITY CHANGED"
              : "DETERMINISTIC RESULT"}
          </span>
          <h2>{entry.label}</h2>
          <p>{r.next_steps[0]}</p>
        </div>
        <span className="decision-tag">
          {r.coverage.supported ? "Scoped ECS review" : "Coverage result"}
        </span>
      </div>
      {revisionInvalid && (
        <div role="alert" className="warning-banner">
          <Info size={18} />
          <span>
            Candidate or trusted policy changed. This saved result does not
            apply to the new revision. Collect matching evidence and rerun.
          </span>
        </div>
      )}
      {detail.applicability?.stale_now && (
        <div className="warning-banner">
          <Clock3 size={18} />
          <span>
            This is a historical snapshot. Its evidence is stale for a decision
            made now.
          </span>
        </div>
      )}
      <div className="report-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>The proposed change</h2>
              <p>Requested resources per Fargate task</p>
            </div>
            <GitPullRequest size={19} />
          </div>
          <div className="configuration">
            <div>
              <span className="eyebrow">BASELINE</span>
              <strong>{cpu(r.change.before?.cpu_units)}</strong>
              <span>{memory(r.change.before?.memory_mib)} memory</span>
            </div>
            <ArrowRight size={21} />
            <div>
              <span className="eyebrow">CANDIDATE</span>
              <strong>{cpu(r.change.after?.cpu_units)}</strong>
              <span>{memory(r.change.after?.memory_mib)} memory</span>
            </div>
          </div>
          <div className="contract-row">
            <ShieldCheck size={17} />
            <div>
              <strong>
                {typeof floor === "number"
                  ? `${floor.toLocaleString()} MiB approved floor`
                  : "No applicable memory floor"}
              </strong>
              <small>Bound to the named service, image and workload.</small>
            </div>
          </div>
        </section>
        <section className="panel cost-panel">
          <div className="panel-heading">
            <div>
              <h2>Projected compute difference</h2>
              <p>Task CPU and memory only</p>
            </div>
            <ArrowDownRight size={20} />
          </div>
          <div className="cost-highlight">
            <strong>{money(cost?.projected_difference, cost?.currency)}</strong>
            <span>
              {cost?.projected_reduction_fraction != null
                ? `${(Number(cost.projected_reduction_fraction) * 100).toFixed(1)}% estimated reduction`
                : "Percentage unavailable"}
            </span>
          </div>
          <div className="cost-comparison">
            <div>
              <span>Baseline</span>
              <strong>{money(cost?.baseline_amount, cost?.currency)}</strong>
            </div>
            <ArrowRight size={15} />
            <div>
              <span>Candidate</span>
              <strong>{money(cost?.candidate_amount, cost?.currency)}</strong>
            </div>
          </div>
          <div className="cost-caption">
            <Info size={13} />
            {cost?.origin === "synthetic_fixture"
              ? "Synthetic rate card · illustrative projection"
              : "Dated estimate · not realized savings"}
          </div>
        </section>
      </div>
      <section className="panel findings-panel">
        <div className="panel-heading">
          <div>
            <h2>What determines the result</h2>
            <p>Policy, evidence and performance checks run in code.</p>
          </div>
          <span className="count-pill">{r.findings.length} findings</span>
        </div>
        <div className="findings">
          {r.findings.map((finding, index) => (
            <div
              className={`finding ${finding.severity}`}
              key={`${finding.code}-${index}`}
            >
              <span className="finding-dot" />
              <div>
                <strong>{human(finding.code.toLowerCase())}</strong>
                <p>{finding.message}</p>
                <code>{finding.code}</code>
              </div>
              <span className="finding-level">{finding.severity}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Workload comparison</h2>
            <p>Each run and request class must satisfy the contract.</p>
          </div>
          <span
            className={`badge ${r.performance.passed ? "ready" : "collect"}`}
          >
            {r.performance.passed
              ? "Contract checks passed"
              : "Checks require attention"}
          </span>
        </div>
        {!r.performance.runs.length ? (
          <Empty title="Workload evidence is missing">
            Add compatible baseline and candidate artifacts before requesting
            review.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table className="workload-table">
              <thead>
                <tr>
                  <th>Run / population</th>
                  <th>Correct / offered</th>
                  <th>p95 latency</th>
                  <th>Dropped</th>
                  <th>Restarts</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {r.performance.runs.map((run) => (
                  <tr key={run.run_id}>
                    <td>
                      <strong className="role-label">{run.role}</strong>
                      <small>{run.run_id}</small>
                    </td>
                    <td>
                      {run.correct.toLocaleString()}{" "}
                      <span className="muted">
                        / {run.offered.toLocaleString()}
                      </span>
                    </td>
                    <td>
                      {run.p95_latency_ms == null
                        ? "Missing"
                        : `${run.p95_latency_ms} ms`}
                    </td>
                    <td>{run.dropped_iterations}</td>
                    <td>{run.restarts}</td>
                    <td>
                      <span
                        className={`badge ${run.passed ? "ready" : "collect"}`}
                      >
                        {run.passed
                          ? "Pass"
                          : run.valid_evidence
                            ? "Breach"
                            : "Inconclusive"}
                      </span>
                      <details className="class-details">
                        <summary>Request classes</summary>
                        {Object.entries(run.request_classes).map(
                          ([name, value]) => (
                            <p key={name}>
                              {name}: {value.correct.toLocaleString()} correct ·
                              p95 {value.p95_latency_ms ?? "unknown"} ms
                            </p>
                          ),
                        )}
                        {run.reasons.map((reason) => (
                          <p key={reason}>{reason}</p>
                        ))}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="panel-footnote">
          {r.performance.aggregation} Origin: {originLabel[r.origin]}. A smoke
          test does not establish capacity.
        </p>
      </section>
      <div className="report-grid evidence-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Evidence coverage</h2>
              <p>Collection, freshness and sufficiency stay distinct.</p>
            </div>
            <Layers size={20} />
          </div>
          <div className="evidence-list">
            {Object.entries(r.coverage.sources).map(([name, source]) => (
              <details key={name}>
                <summary>
                  <span>{human(name)}</span>
                  <span
                    className={`badge ${source.coverage === "sufficient" ? "ready" : "collect"}`}
                  >
                    {source.coverage}
                  </span>
                </summary>
                {source.records?.length ? (
                  source.records.map((record) => (
                    <div className="source-record" key={record.id}>
                      <strong>{record.source}</strong>
                      <p>
                        {human(record.collection)} · {record.freshness} ·{" "}
                        {originLabel[record.origin]}
                      </p>
                      <small>{date(record.observed_end)}</small>
                      <code>{record.id}</code>
                    </div>
                  ))
                ) : (
                  <p className="muted">
                    {name === "terraform"
                      ? "Sanitized plan fields and original byte hash retained."
                      : "No matching source record is available."}
                  </p>
                )}
              </details>
            ))}
          </div>
        </section>
        <section className="panel guard-panel">
          <div className="panel-heading">
            <div>
              <h2>Keep the lesson</h2>
              <p>A reviewed constraint can catch a repeat change.</p>
            </div>
            <ShieldCheck size={22} />
          </div>
          <div className="guard-content">
            <span className="tag">ECS TASK MEMORY FLOOR</span>
            <h3>
              {typeof floor === "number"
                ? `${floor.toLocaleString()} MiB`
                : "Scoped memory guard"}
            </h3>
            <p>
              Prepare the supported rule from the existing approved facts, then
              verify its failure and healthy fixtures.
            </p>
            {draft ? (
              <>
                <div className="guard-state">
                  <Badge outcome={null} state={human(draft.state)} />
                  <strong>Not active</strong>
                </div>
                <p className="muted">
                  Incident reference: <code>{draft.spec.incident_id}</code>
                </p>
                <button
                  className="button secondary full"
                  onClick={() => onValidate(draft.id)}
                  disabled={!!busy}
                >
                  {busy === "validate" ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : (
                    <FileCheck2 size={15} />
                  )}
                  Run guard fixtures
                </button>
                {draft.fixture_results.fixtures && (
                  <div className="fixture-results">
                    {draft.fixture_results.fixtures.map((fixture) => (
                      <span key={fixture.id}>
                        {fixture.passed ? (
                          <CheckCircle2 size={13} />
                        ) : (
                          <XCircle size={13} />
                        )}
                        {human(fixture.id)}
                      </span>
                    ))}
                  </div>
                )}
                {draft.fixture_results.passed && (
                  <a
                    className="button secondary full"
                    href={`/api/v1/guard-drafts/${draft.id}/bundle`}
                    download
                  >
                    <Download size={15} />
                    Export guard draft
                  </a>
                )}
              </>
            ) : (
              <button
                className="button secondary full"
                onClick={onDraft}
                disabled={!!busy || !r.coverage.guard_applicable}
              >
                {busy === "draft" ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Plus size={15} />
                )}
                Prepare guard draft
              </button>
            )}
            <small className="guard-notice">
              Activation requires separate source-control review and a protected
              CI check.
            </small>
          </div>
        </section>
      </div>
      <section className="panel explanation-panel">
        <div className="panel-heading">
          <div>
            <h2>Review explanation</h2>
            <p>
              {detail.explanation?.status === "template"
                ? "Generated from deterministic findings · no model call"
                : `Explanation status: ${human(detail.explanation?.status || "unavailable")}`}
            </p>
          </div>
          <FileCheck2 size={20} />
        </div>
        <div className="explanation-content">
          <p>
            {explanation?.summary ||
              detail.explanation?.summary ||
              r.next_steps[0]}
          </p>
          {detail.explanation?.status === "explanation_unavailable" && (
            <p className="warning-text">
              AI explanation unavailable: {detail.explanation.reason}. The
              deterministic report remains available.
            </p>
          )}
          <details>
            <summary>Inspect cited facts and assumptions</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Fact ID</th>
                    <th>Exact value</th>
                    <th>Basis</th>
                  </tr>
                </thead>
                <tbody>
                  {r.facts.map((fact) => (
                    <tr key={fact.fact_id}>
                      <td>
                        <code>{fact.fact_id}</code>
                      </td>
                      <td>{String(fact.value)}</td>
                      <td>{human(fact.kind)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {cost && (
              <>
                <h4>Cost assumptions</h4>
                <ul>
                  {cost.assumptions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p>
                  <strong>Excluded:</strong>{" "}
                  {cost.excluded.map(human).join(", ")}.
                </p>
                <p>
                  Task-hours: baseline {cost.baseline_task_hours ?? "unknown"};
                  candidate {cost.candidate_task_hours ?? "unknown"}. Rate date:{" "}
                  {date(cost.price_date)}.
                </p>
              </>
            )}
            {explanation?.limitations && (
              <ul>
                {explanation.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </details>
          <details>
            <summary>Provenance and model trace</summary>
            <p>
              Account: {scope.account_id} · Cluster: {scope.cluster}
            </p>
            <p>
              Resource: <code>{scope.terraform_address}</code>
            </p>
            <p>
              Trusted revision: <code>{r.trusted_revision_hash}</code>
            </p>
            {Object.entries(r.input_hashes).map(([name, hash]) => (
              <p className="hash-row" key={name}>
                {name}
                <code>{hash}</code>
              </p>
            ))}
            <pre>{JSON.stringify(detail.explanation, null, 2)}</pre>
          </details>
          <details>
            <summary>Check applicability to another commit</summary>
            <form
              className="inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                onCompareCommit(commit);
              }}
            >
              <label htmlFor="new-commit">Candidate commit</label>
              <input
                id="new-commit"
                value={commit}
                onChange={(event) => setCommit(event.target.value)}
                pattern="[a-f0-9]{40,64}"
                required
                placeholder="Full candidate commit hash"
              />
              <button className="button secondary small" type="submit">
                Check applicability
              </button>
            </form>
          </details>
          <details>
            <summary>Record an operator disposition</summary>
            <p className="muted">
              Records your decision at the current time. This does not record
              measured performance or billed savings.
            </p>
            <form
              className="disposition-form"
              onSubmit={async (event) => {
                event.preventDefault();
                setSaved(false);
                setSaved(await onDisposition(disposition, reason));
              }}
            >
              <label htmlFor="disposition">Disposition</label>
              <select
                id="disposition"
                value={disposition}
                onChange={(event) => setDisposition(event.target.value)}
              >
                <option value="rejected">Rejected</option>
                <option value="adopted">Adopted</option>
                <option value="insufficient_evidence">
                  Insufficient evidence
                </option>
                <option value="reverted">Reverted</option>
              </select>
              <label htmlFor="disposition-reason">Reason</label>
              <input
                id="disposition-reason"
                value={reason}
                maxLength={200}
                required
                onChange={(event) => {
                  setReason(event.target.value);
                  setSaved(false);
                }}
              />
              <button className="button secondary small" disabled={!!busy}>
                Save disposition
              </button>
              {saved && !busy && (
                <span className="muted">
                  Check Outcomes for the recorded disposition.
                </span>
              )}
            </form>
          </details>
        </div>
      </section>
    </>
  );
}

function Outcomes({
  data,
  busy,
  onLoadSample,
  onOpen,
}: {
  data: Analytics | null;
  busy: string;
  onLoadSample: () => void;
  onOpen: (id: string) => void;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CLOSE THE LOOP</div>
          <h1>Outcomes, with context.</h1>
          <p>
            Keep projections, observed results and model spend on their own
            terms.
          </p>
        </div>
        <span className="tag">
          <Activity size={14} />
          WORKSPACE ANALYTICS
        </span>
      </div>
      <div className="metric-grid four">
        <Metric
          label="REVIEWED CHANGES"
          value={data?.review_count ?? "Unavailable"}
          note="All saved report outcomes"
        />
        <Metric
          label="RECORDED DISPOSITIONS"
          value={data?.observed_outcomes.length ?? "Unavailable"}
          note="Operator-reported decisions"
        />
        <Metric
          label="MODEL SPEND"
          value={money(data?.model.actual_usd, "USD", 4)}
          note={`${data?.model.attempts ?? "Unknown"} recorded provider attempts`}
        />
        <Metric
          label="UNRECONCILED RESERVATIONS"
          value={money(data?.model.pending_reserved_usd, "USD", 4)}
          note="Pending charges remain reserved"
        />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Projected comparisons</h2>
            <p>
              Each row is a separate alternative. These amounts are not added
              into realized savings.
            </p>
          </div>
          <ArrowDownRight size={20} />
        </div>
        {!data?.projected_comparisons.length ? (
          <Empty title={data ? "No projections yet" : "Analytics unavailable"}>
            Complete a review to compare its scoped baseline and candidate
            estimates.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Review</th>
                  <th>Outcome</th>
                  <th>Baseline estimate</th>
                  <th>Candidate estimate</th>
                  <th>Projected difference</th>
                  <th>Origin</th>
                </tr>
              </thead>
              <tbody>
                {data.projected_comparisons.map((item) => (
                  <tr key={item.review_id}>
                    <td>
                      <button
                        className="review-link"
                        onClick={() => onOpen(item.review_id)}
                      >
                        <code>{item.review_id.slice(0, 8)}</code>
                        <span>{date(item.evaluated_at)}</span>
                      </button>
                    </td>
                    <td>
                      <Badge outcome={item.outcome} />
                    </td>
                    <td>
                      {money(item.cost?.baseline_amount, item.cost?.currency)}
                    </td>
                    <td>
                      {money(item.cost?.candidate_amount, item.cost?.currency)}
                    </td>
                    <td>
                      <strong>
                        {money(
                          item.cost?.projected_difference,
                          item.cost?.currency,
                        )}
                      </strong>
                    </td>
                    <td>
                      <Origin value={item.origin} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Observed outcomes</h2>
            <p>
              Operator disposition and evidence basis, separate from the
              original estimate.
            </p>
          </div>
          <Activity size={20} />
        </div>
        {!data?.observed_outcomes.length ? (
          <Empty
            title={
              data ? "No observed outcomes recorded" : "Analytics unavailable"
            }
          >
            Record a disposition from a review. Measured performance and billed
            savings require their own evidence.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Review</th>
                  <th>Disposition</th>
                  <th>Reason</th>
                  <th>Cost evidence</th>
                  <th>Origin</th>
                </tr>
              </thead>
              <tbody>
                {data.observed_outcomes.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <button
                        className="review-link"
                        onClick={() => onOpen(item.review_id)}
                      >
                        {item.review_id.slice(0, 8)}
                      </button>
                    </td>
                    <td>{human(item.disposition)}</td>
                    <td>{item.reason}</td>
                    <td>{human(item.cost_basis)}</td>
                    <td>
                      <Origin value={item.origin} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel billing-panel">
        <div className="panel-heading">
          <div>
            <h2>Billing sample reconciliation</h2>
            <p>
              Licensed FOCUS benchmark rows. This is not the demo service’s
              bill.
            </p>
          </div>
          <button
            className="button secondary small"
            disabled={!!busy}
            onClick={onLoadSample}
          >
            {busy === "billing" ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Database size={15} />
            )}
            Load billing sample
          </button>
        </div>
        {!data?.billing.totals.length ? (
          <Empty
            title={data ? "No billing rows imported" : "Analytics unavailable"}
          >
            Load the supplied licensed sample to inspect arithmetic, credits and
            separate accounting measures.
          </Empty>
        ) : (
          <>
            <div className="billing-totals">
              {data.billing.totals.map((total) => (
                <div key={total.currency}>
                  <div>
                    <span className="eyebrow">
                      {total.currency} · {total.rows.toLocaleString()} ROWS
                    </span>
                    <strong>{money(total.billed, total.currency, 5)}</strong>
                    <span>BilledCost</span>
                  </div>
                  <div>
                    <span className="eyebrow">SEPARATE ACCOUNTING BASIS</span>
                    <strong>{money(total.effective, total.currency, 5)}</strong>
                    <span>EffectiveCost</span>
                  </div>
                  <div>
                    <span className="eyebrow">CREDITS / ADJUSTMENTS</span>
                    <strong>{total.negative_billed_rows}</strong>
                    <span>Negative billed rows preserved</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="panel-footnote">
              {data.billing.note} Repeated imports are idempotent;
              identical-looking separate rows are preserved.
            </p>
            <details className="billing-details">
              <summary>Inspect service and currency totals</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Provider</th>
                      <th>Service</th>
                      <th>Currency</th>
                      <th>Rows</th>
                      <th>BilledCost</th>
                      <th>EffectiveCost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.billing.groups.map((group, index) => (
                      <tr key={index}>
                        <td>{group.provider}</td>
                        <td>{group.service}</td>
                        <td>{group.currency}</td>
                        <td>{group.rows}</td>
                        <td>{money(group.billed, group.currency, 5)}</td>
                        <td>{money(group.effective, group.currency, 5)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </section>
      <p className="muted analytics-note">
        {data?.bounds} {data?.model.basis}
      </p>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
