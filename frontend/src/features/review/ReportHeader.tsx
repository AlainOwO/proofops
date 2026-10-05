import { ArrowLeft, Clock3, Download, Info } from "lucide-react";
import { Origin } from "../../components/Origin";
import { date } from "../../lib/format";
import { outcomes } from "../../lib/outcomes";
import type { CoreReport, Detail } from "../../types";

export function ReportHeader({
  detail,
  onBack,
}: {
  detail: Detail;
  onBack: () => void;
}) {
  const r = detail.report as CoreReport;
  const entry = outcomes[r.outcome];
  const Icon = entry.icon;
  const scope = r.change.service_map.scope;
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
    </>
  );
}
