import { Layers } from "lucide-react";
import { date, human, originLabel } from "../../lib/format";
import type { CoreReport } from "../../types";

export function EvidencePanel({
  sources,
}: {
  sources: CoreReport["coverage"]["sources"];
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Evidence coverage</h2>
          <p>Collection, freshness and sufficiency stay distinct.</p>
        </div>
        <Layers size={20} />
      </div>
      <div className="evidence-list">
        {Object.entries(sources).map(([name, source]) => (
          <details key={name}>
            <summary>
              <span>{human(name)}</span>
              <span
                className={`badge ${source.coverage === "sufficient" ? "ready" : "collect"}`}
              >
                {source.coverage}
              </span>
            </summary>
            {source.records?.length ? (
              source.records.map((record) => (
                <div className="source-record" key={record.id}>
                  <strong>{record.source}</strong>
                  <p>
                    {human(record.collection)} · {record.freshness} ·{" "}
                    {originLabel[record.origin]}
                  </p>
                  <small>{date(record.observed_end)}</small>
                  <code>{record.id}</code>
                </div>
              ))
            ) : (
              <p className="muted">
                {name === "terraform"
                  ? "Sanitized plan fields and original byte hash retained."
                  : "No matching source record is available."}
              </p>
            )}
          </details>
        ))}
      </div>
    </section>
  );
}
