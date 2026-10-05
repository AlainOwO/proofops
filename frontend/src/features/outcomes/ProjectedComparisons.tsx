import { TableScroll } from "../../components/TableScroll";
import { ArrowDownRight } from "lucide-react";
import { Badge } from "../../components/Badge";
import { Origin } from "../../components/Origin";
import { date, money } from "../../lib/format";
import { StatePanel } from "../../components/StatePanel";
import type { Analytics } from "../../types";

export function ProjectedComparisons({
  data,
  onOpen,
}: {
  data: Analytics;
  onOpen: (id: string) => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Projected comparisons</h2>
          <p>
            Each row is a separate alternative. These amounts are not added into
            realized savings.
          </p>
        </div>
        <ArrowDownRight size={20} />
      </div>
      {!data.projected_comparisons.length ? (
        <StatePanel title="No projections yet">
          Complete a review to compare its scoped baseline and candidate
          estimates.
        </StatePanel>
      ) : (
        <TableScroll label="Projected comparisons table">
          <table>
            <thead>
              <tr>
                <th>Review</th>
                <th>Outcome</th>
                <th>Baseline estimate</th>
                <th>Candidate estimate</th>
                <th>Projected difference</th>
                <th>Origin</th>
              </tr>
            </thead>
            <tbody>
              {data.projected_comparisons.map((item) => (
                <tr key={item.review_id}>
                  <td>
                    <button
                      className="review-link"
                      onClick={() => onOpen(item.review_id)}
                    >
                      <code>{item.review_id.slice(0, 8)}</code>
                      <span>{date(item.evaluated_at)}</span>
                    </button>
                  </td>
                  <td>
                    <Badge outcome={item.outcome} />
                  </td>
                  <td>
                    {money(item.cost?.baseline_amount, item.cost?.currency)}
                  </td>
                  <td>
                    {money(item.cost?.candidate_amount, item.cost?.currency)}
                  </td>
                  <td>
                    <strong>
                      {money(
                        item.cost?.projected_difference,
                        item.cost?.currency,
                      )}
                    </strong>
                  </td>
                  <td>
                    <Origin value={item.origin} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}
    </section>
  );
}
