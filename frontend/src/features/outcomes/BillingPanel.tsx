import { Database, LoaderCircle } from "lucide-react";
import { Empty } from "../../components/Empty";
import { money } from "../../lib/format";
import type { Analytics } from "../../types";

export function BillingPanel({
  data,
  busy,
  onLoadSample,
}: {
  data: Analytics | null;
  busy: string;
  onLoadSample: () => void;
}) {
  return (
    <section className="panel billing-panel">
      <div className="panel-heading">
        <div>
          <h2>Billing sample reconciliation</h2>
          <p>
            Licensed FOCUS benchmark rows. This is not the demo service’s bill.
          </p>
        </div>
        <button
          className="button secondary small"
          disabled={!!busy}
          onClick={onLoadSample}
        >
          {busy === "billing" ? (
            <LoaderCircle className="spin" size={15} />
          ) : (
            <Database size={15} />
          )}
          Load billing sample
        </button>
      </div>
      {!data?.billing.totals.length ? (
        <Empty
          title={data ? "No billing rows imported" : "Analytics unavailable"}
        >
          Load the supplied licensed sample to inspect arithmetic, credits and
          separate accounting measures.
        </Empty>
      ) : (
        <>
          <div className="billing-totals">
            {data.billing.totals.map((total) => (
              <div key={total.currency}>
                <div>
                  <span className="eyebrow">
                    {total.currency} · {total.rows.toLocaleString()} ROWS
                  </span>
                  <strong>{money(total.billed, total.currency, 5)}</strong>
                  <span>BilledCost</span>
                </div>
                <div>
                  <span className="eyebrow">SEPARATE ACCOUNTING BASIS</span>
                  <strong>{money(total.effective, total.currency, 5)}</strong>
                  <span>EffectiveCost</span>
                </div>
                <div>
                  <span className="eyebrow">CREDITS / ADJUSTMENTS</span>
                  <strong>{total.negative_billed_rows}</strong>
                  <span>Negative billed rows preserved</span>
                </div>
              </div>
            ))}
          </div>
          <p className="panel-footnote">
            {data.billing.note} Repeated imports are idempotent;
            identical-looking separate rows are preserved.
          </p>
          <details className="billing-details">
            <summary>Inspect service and currency totals</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Service</th>
                    <th>Currency</th>
                    <th>Rows</th>
                    <th>BilledCost</th>
                    <th>EffectiveCost</th>
                  </tr>
                </thead>
                <tbody>
                  {data.billing.groups.map((group, index) => (
                    <tr key={index}>
                      <td>{group.provider}</td>
                      <td>{group.service}</td>
                      <td>{group.currency}</td>
                      <td>{group.rows}</td>
                      <td>{money(group.billed, group.currency, 5)}</td>
                      <td>{money(group.effective, group.currency, 5)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
