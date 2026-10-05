import { Info } from "lucide-react";

export function HowItWorks() {
  return (
    <aside
      className="panel how-it-works"
      aria-labelledby="how-it-works-heading"
    >
      <h2 id="how-it-works-heading">
        <Info size={17} aria-hidden="true" />
        How this works
      </h2>
      <ol>
        <li>
          <strong>Choose a change</strong>
          <p>Use a synthetic replay or import a sanitized review bundle.</p>
        </li>
        <li>
          <strong>Check the evidence</strong>
          <p>
            Code checks costs, workload results and the scoped operating
            contract.
          </p>
        </li>
        <li>
          <strong>Inspect the result</strong>
          <p>
            Read the findings and next steps, then export the report for
            engineering review.
          </p>
        </li>
      </ol>
      <p className="how-it-works-note">
        Optional AI explains the result. A ready result requests review; it does
        not approve deployment.
      </p>
    </aside>
  );
}
