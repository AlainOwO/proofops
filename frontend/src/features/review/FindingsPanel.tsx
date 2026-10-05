import { human } from "../../lib/format";
import type { Finding } from "../../types";

export function FindingsPanel({ findings }: { findings: Finding[] }) {
  return (
    <section className="panel findings-panel">
      <div className="panel-heading">
        <div>
          <h2>What determines the result</h2>
          <p>Policy, evidence and performance checks run in code.</p>
        </div>
        <span className="count-pill">{findings.length} findings</span>
      </div>
      <div className="findings">
        {findings.map((finding, index) => (
          <div
            className={`finding ${finding.severity}`}
            key={`${finding.code}-${index}`}
          >
            <span className="finding-dot" />
            <div>
              <strong>{human(finding.code.toLowerCase())}</strong>
              <p>{finding.message}</p>
              <code>{finding.code}</code>
            </div>
            <span className="finding-level">{finding.severity}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
