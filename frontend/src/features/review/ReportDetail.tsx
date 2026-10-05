import type { CoreReport, Detail } from "../../types";
import { ReportHeader } from "./ReportHeader";
import { ChangeSummary } from "./ChangeSummary";
import { FindingsPanel } from "./FindingsPanel";
import { WorkloadPanel } from "./WorkloadPanel";
import { EvidencePanel } from "./EvidencePanel";
import { GuardPanel } from "./GuardPanel";
import { ExplanationPanel } from "./ExplanationPanel";
import { ReviewActions } from "./ReviewActions";

export function ReportDetail({
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
  const floor = r.facts.find(
    (item) => item.fact_id === "approved.minimum_task_memory_mib",
  )?.value;
  return (
    <>
      <ReportHeader detail={detail} onBack={onBack} />
      <ChangeSummary report={r} floor={floor} />
      <FindingsPanel findings={r.findings} />
      <WorkloadPanel performance={r.performance} origin={r.origin} />
      <div className="report-grid evidence-grid">
        <EvidencePanel sources={r.coverage.sources} />
        <GuardPanel
          draft={detail.guard_drafts?.[0]}
          floor={floor}
          applicable={r.coverage.guard_applicable}
          busy={busy}
          onDraft={onDraft}
          onValidate={onValidate}
        />
      </div>
      <ExplanationPanel detail={detail}>
        <ReviewActions
          busy={busy}
          onCompareCommit={onCompareCommit}
          onDisposition={onDisposition}
        />
      </ExplanationPanel>
    </>
  );
}
