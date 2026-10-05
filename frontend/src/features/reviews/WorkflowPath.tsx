import { ArrowRight } from "lucide-react";

export function WorkflowPath() {
  return (
    <div className="workflow-strip">
      <span className="eyebrow">THE REVIEW PATH</span>
      <span>
        <span className="step-number">1</span>Proposed change
      </span>
      <ArrowRight size={15} />
      <span>
        <span className="step-number">2</span>Cost + workload evidence
      </span>
      <ArrowRight size={15} />
      <span>
        <span className="step-number">3</span>Approved constraints
      </span>
      <ArrowRight size={15} />
      <span>
        <span className="step-number">4</span>Engineering review
      </span>
    </div>
  );
}
