import { ArrowLeft, LoaderCircle, XCircle } from "lucide-react";
import { human } from "../../lib/format";
import type { Detail } from "../../types";

export function JobView({
  detail,
  error,
  onRetry,
  onBack,
}: {
  detail: Detail | null;
  error: string;
  onRetry: () => void;
  onBack: () => void;
}) {
  const failed = detail?.job.state === "failed";
  const pending = !detail || ["queued", "running"].includes(detail.job.state);
  const unavailable = !!error || (!pending && !failed);
  const title = unavailable
    ? "Review unavailable"
    : failed
      ? "Review could not complete"
      : !detail
        ? "Loading review"
        : detail.job.state === "queued"
          ? "Review queued"
          : "Building the evidence report";
  return (
    <div className="job-view">
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        All reviews
      </button>
      <section
        className={`panel job-panel ${failed || unavailable ? "state-error" : ""}`}
        aria-labelledby="job-heading"
      >
        <div role="status">
          {failed || unavailable ? (
            <XCircle size={34} aria-hidden="true" />
          ) : (
            <LoaderCircle className="spin" size={34} aria-hidden="true" />
          )}
          <h1 id="job-heading">{title}</h1>
          {detail && (
            <p>
              {unavailable ? "Last known state" : "Job"}:{" "}
              {human(detail.job.state)} · {human(detail.job.stage)}
            </p>
          )}
          {detail?.job.error_code && <code>{detail.job.error_code}</code>}
          <p className="muted">
            {unavailable
              ? "The saved review could not be loaded. Retry loading its state or return to all reviews."
              : failed
                ? "No review result was produced. Check the error code and input bundle before starting another review."
                : !detail
                  ? "Reading the saved job and its report."
                  : detail.job.state === "queued"
                    ? "A queued job needs the ProofOps worker running. Completed findings will appear here."
                    : "The worker is checking the saved inputs. This page updates automatically."}
          </p>
        </div>
        {unavailable && (
          <button className="button secondary" onClick={onRetry}>
            Retry loading review
          </button>
        )}
      </section>
    </div>
  );
}
