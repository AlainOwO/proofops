import { TableScroll } from "../../components/TableScroll";
import type { ReactNode } from "react";
import { FileCheck2 } from "lucide-react";
import { date, human, money } from "../../lib/format";
import type { CoreReport, Detail } from "../../types";

export function ExplanationPanel({
  detail,
  children,
}: {
  detail: Detail;
  children: ReactNode;
}) {
  const r = detail.report as CoreReport;
  const cost = r.cost;
  const scope = r.change.service_map.scope;
  const explanation =
    detail.explanation?.output || detail.explanation?.fallback?.output;
  return (
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
          <TableScroll label="Cited facts table">
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
          </TableScroll>
          {cost && (
            <>
              <h4>Cost assumptions</h4>
              <ul>
                {cost.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <p>
                <strong>Excluded:</strong> {cost.excluded.map(human).join(", ")}
                .
              </p>
              <p>
                Task-hours: baseline {cost.baseline_task_hours ?? "unknown"};
                candidate {cost.candidate_task_hours ?? "unknown"}. Rate date:{" "}
                {date(cost.price_date)}.
              </p>
              <p>
                Cost per correctly completed request: baseline{" "}
                {money(
                  cost.cost_per_correct_request?.baseline,
                  cost.currency,
                  8,
                )}
                ; candidate{" "}
                {money(
                  cost.cost_per_correct_request?.candidate,
                  cost.currency,
                  8,
                )}
                . This comparison requires matching cost and workload windows.
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
        {children}
      </div>
    </section>
  );
}
