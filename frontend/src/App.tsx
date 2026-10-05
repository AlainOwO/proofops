import { api } from "./api";
import { useWorkspace } from "./hooks/useWorkspace";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBanner } from "./components/ErrorBanner";
import { ReviewsPage } from "./features/reviews/ReviewsPage";
import { ReportDetail } from "./features/review/ReportDetail";
import { JobView } from "./features/review/JobView";
import { OutcomesPage } from "./features/outcomes/OutcomesPage";

export function App() {
  const {
    reviews,
    total,
    analytics,
    detail,
    error,
    busy,
    query,
    replay,
    file,
    ai,
    mode,
    ready,
    loaded,
    workspaceLoading,
    detailError,
    retryDetail,
    reportId,
    isOutcomes,
    navigate,
    refresh,
    action,
    runReview,
    setError,
    setQuery,
    setReplay,
    setFile,
    setAi,
    setMode,
  } = useWorkspace();
  return (
    <AppShell
      total={total}
      ready={ready}
      loading={workspaceLoading}
      isOutcomes={isOutcomes}
      reportId={reportId}
      busy={busy}
      onRefresh={() =>
        detailError && !detail?.report
          ? retryDetail()
          : action("refresh", refresh)
      }
    >
      <ErrorBanner error={error} onDismiss={() => setError("")} />
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
          <JobView
            detail={detail}
            error={detailError}
            onRetry={retryDetail}
            onBack={() => navigate("/reviews")}
          />
        )
      ) : isOutcomes ? (
        <OutcomesPage
          data={analytics}
          busy={busy}
          loading={!loaded || (workspaceLoading && analytics === null)}
          onRetry={() => action("refresh", refresh)}
          onLoadSample={() =>
            action("billing", () =>
              api("/api/v1/billing/import-sample", { method: "POST" }),
            )
          }
          onOpen={(id) => navigate(`/reviews/${id}`)}
        />
      ) : (
        <ReviewsPage
          reviews={reviews}
          total={total}
          analytics={analytics}
          loading={!loaded || (workspaceLoading && total === null)}
          onRetry={() => action("refresh", refresh)}
          query={query}
          onQueryChange={setQuery}
          onOpen={(id) => navigate(`/reviews/${id}`)}
          form={{
            replay,
            file,
            ai,
            mode,
            busy,
            onReplayChange: setReplay,
            onFileChange: setFile,
            onAiChange: setAi,
            onModeChange: setMode,
            onRunReview: runReview,
          }}
        />
      )}
    </AppShell>
  );
}
