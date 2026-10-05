import {
  ArrowDownRight,
  ArrowRight,
  GitPullRequest,
  Info,
  ShieldCheck,
} from "lucide-react";
import { cpu, memory, money } from "../../lib/format";
import type { CoreReport } from "../../types";

export function ChangeSummary({
  report: r,
  floor,
}: {
  report: CoreReport;
  floor: CoreReport["facts"][number]["value"] | undefined;
}) {
  const cost = r.cost;
  const ineligibleReason =
    r.outcome === "revise_change"
      ? "Not eligible: resolve findings first"
      : r.outcome === "collect_evidence"
        ? "Not eligible: evidence incomplete"
        : null;
  return (
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
      <section
        className={`panel cost-panel${ineligibleReason ? " ineligible" : ""}`}
        aria-labelledby="cost-heading"
      >
        <div className="panel-heading">
          <div>
            <h2 id="cost-heading">Projected compute difference</h2>
            <p>Task CPU and memory only</p>
          </div>
          <ArrowDownRight size={20} />
        </div>
        {ineligibleReason && (
          <p className="cost-eligibility">{ineligibleReason}</p>
        )}
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
  );
}
