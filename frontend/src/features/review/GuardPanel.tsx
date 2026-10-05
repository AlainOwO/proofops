import {
  CheckCircle2,
  Download,
  FileCheck2,
  LoaderCircle,
  Plus,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Badge } from "../../components/Badge";
import { human } from "../../lib/format";
import type { CoreReport, Draft } from "../../types";

export function GuardPanel({
  draft,
  floor,
  applicable,
  busy,
  onDraft,
  onValidate,
}: {
  draft?: Draft;
  floor: CoreReport["facts"][number]["value"] | undefined;
  applicable: boolean;
  busy: string;
  onDraft: () => void;
  onValidate: (id: string) => void;
}) {
  return (
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
            disabled={!!busy || !applicable}
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
          Activation requires separate source-control review and a protected CI
          check.
        </small>
      </div>
    </section>
  );
}
