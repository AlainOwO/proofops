import { TableScroll } from "../../components/TableScroll";
import { Activity } from "lucide-react";
import { Origin } from "../../components/Origin";
import { human } from "../../lib/format";
import { StatePanel } from "../../components/StatePanel";
import type { Analytics } from "../../types";

export function ObservedOutcomes({
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
          <h2>Observed outcomes</h2>
          <p>
            Operator disposition and evidence basis, separate from the original
            estimate.
          </p>
        </div>
        <Activity size={20} />
      </div>
      {!data.observed_outcomes.length ? (
        <StatePanel title="No observed outcomes recorded">
          Record a disposition from a review. Measured performance and billed
          savings require their own evidence.
        </StatePanel>
      ) : (
        <TableScroll label="Observed outcomes table">
          <table>
            <thead>
              <tr>
                <th>Review</th>
                <th>Disposition</th>
                <th>Reason</th>
                <th>Cost evidence</th>
                <th>Origin</th>
              </tr>
            </thead>
            <tbody>
              {data.observed_outcomes.map((item) => (
                <tr key={item.id}>
                  <td>
                    <button
                      className="review-link"
                      onClick={() => onOpen(item.review_id)}
                    >
                      {item.review_id.slice(0, 8)}
                    </button>
                  </td>
                  <td>{human(item.disposition)}</td>
                  <td>{item.reason}</td>
                  <td>{human(item.cost_basis)}</td>
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
