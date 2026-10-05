import { Activity } from "lucide-react";
import { Metric } from "../../components/Metric";
import { StatePanel } from "../../components/StatePanel";
import { money } from "../../lib/format";
import type { Analytics } from "../../types";
import { ProjectedComparisons } from "./ProjectedComparisons";
import { ObservedOutcomes } from "./ObservedOutcomes";
import { BillingPanel } from "./BillingPanel";

export function OutcomesPage({
  data,
  busy,
  loading,
  onRetry,
  onLoadSample,
  onOpen,
}: {
  data: Analytics | null;
  busy: string;
  loading: boolean;
  onRetry: () => void;
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
          loading={loading}
        />
        <Metric
          label="RECORDED DISPOSITIONS"
          value={data?.observed_outcomes.length ?? "Unavailable"}
          note="Operator-reported decisions"
          loading={loading}
        />
        <Metric
          label="MODEL SPEND"
          value={money(data?.model.actual_usd, "USD", 4)}
          note={`${data?.model.attempts ?? "Unknown"} recorded provider attempts`}
          loading={loading}
        />
        <Metric
          label="UNRECONCILED RESERVATIONS"
          value={money(data?.model.pending_reserved_usd, "USD", 4)}
          note="Pending charges remain reserved"
          loading={loading}
        />
      </div>
      {data ? (
        <>
          <p className="muted analytics-note">
            Provider call latency: p50{" "}
            {data?.model.p50_seconds == null
              ? "not measured"
              : `${data.model.p50_seconds.toFixed(2)} s`}
            {" · "}p95{" "}
            {data?.model.p95_seconds == null
              ? "not measured"
              : `${data.model.p95_seconds.toFixed(2)} s`}
            . Call timings exclude queue time; saved evaluation results report
            full task latency.
          </p>
          <ProjectedComparisons data={data} onOpen={onOpen} />
          <ObservedOutcomes data={data} onOpen={onOpen} />
          <BillingPanel data={data} busy={busy} onLoadSample={onLoadSample} />
          <p className="muted analytics-note">
            {data?.bounds} {data?.model.basis}
          </p>
        </>
      ) : (
        <section className="panel">
          <StatePanel
            title={loading ? "Loading outcomes" : "Outcomes unavailable"}
            kind={loading ? "loading" : "error"}
            action={
              !loading && (
                <button
                  className="button secondary"
                  onClick={onRetry}
                  disabled={!!busy}
                >
                  Retry loading outcomes
                </button>
              )
            }
          >
            {loading
              ? "Fetching projections, operator decisions and billing data."
              : "Check that the local backend is running, then try again. Missing analytics do not mean zero activity or spend."}
          </StatePanel>
        </section>
      )}
    </>
  );
}
