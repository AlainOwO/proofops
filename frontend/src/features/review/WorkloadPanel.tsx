import { TableScroll } from "../../components/TableScroll";
import { StatePanel } from "../../components/StatePanel";
import { originLabel } from "../../lib/format";
import type { CoreReport } from "../../types";

export function WorkloadPanel({
  performance,
  origin,
}: {
  performance: CoreReport["performance"];
  origin: string;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Workload comparison</h2>
          <p>Each run and request class must satisfy the contract.</p>
        </div>
        <span className={`badge ${performance.passed ? "ready" : "collect"}`}>
          {performance.passed
            ? "Contract checks passed"
            : "Checks require attention"}
        </span>
      </div>
      {!performance.runs.length ? (
        <StatePanel title="Workload evidence is missing">
          Add compatible baseline and candidate artifacts before requesting
          review.
        </StatePanel>
      ) : (
        <TableScroll label="Workload comparison table">
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
              {performance.runs.map((run) => (
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
        </TableScroll>
      )}
      <p className="panel-footnote">
        {performance.aggregation} Origin: {originLabel[origin]}. A smoke test
        does not establish capacity.
      </p>
    </section>
  );
}
