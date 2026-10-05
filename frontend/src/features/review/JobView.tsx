import { ArrowLeft, LoaderCircle, XCircle } from "lucide-react";
import { human } from "../../lib/format";
import type { Detail } from "../../types";

export function JobView({
  detail,
  onBack,
}: {
  detail: Detail | null;
  onBack: () => void;
}) {
  return (
    <div className="job-view">
      <button className="back-link" onClick={onBack}>
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
        {detail?.job.error_code && <code>{detail.job.error_code}</code>}
        <p className="muted">
          A queued job needs the ProofOps worker running. Completed findings
          will appear here.
        </p>
      </div>
    </div>
  );
}
