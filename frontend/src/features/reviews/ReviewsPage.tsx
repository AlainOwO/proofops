import { Plus } from "lucide-react";
import { Metric } from "../../components/Metric";
import type { Analytics, Outcome, Summary } from "../../types";
import { ReviewList } from "./ReviewList";
import { ReviewForm, type ReviewFormProps } from "./ReviewForm";
import { WorkflowPath } from "./WorkflowPath";

export function ReviewsPage({
  reviews,
  total,
  analytics,
  loaded,
  query,
  onQueryChange,
  onOpen,
  form,
}: {
  reviews: Summary[];
  total: number | null;
  analytics: Analytics | null;
  loaded: boolean;
  query: string;
  onQueryChange: (query: string) => void;
  onOpen: (id: string) => void;
  form: ReviewFormProps;
}) {
  const count = (value: Outcome) =>
    analytics ? (analytics.review_counts[value] ?? 0) : "Unavailable";
  const filtered = reviews.filter((item) =>
    `${item.service} ${item.candidate_commit} ${item.outcome} ${item.state}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CHANGE INTELLIGENCE</div>
          <h1>Review with evidence.</h1>
          <p>
            Understand the saving. Check the contract. Make the next decision.
          </p>
        </div>
        <button
          className="button primary"
          onClick={() => document.getElementById("replay-choice")?.focus()}
        >
          <Plus size={16} />
          New review
        </button>
      </div>
      <div className="metric-grid four">
        <Metric
          label="TOTAL REVIEWS"
          value={total ?? "Unavailable"}
          note="Saved in this workspace"
        />
        <Metric
          label="READY FOR REVIEW"
          value={count("request_review")}
          note="Required checks passed"
          accent
        />
        <Metric
          label="CHANGES TO REVISE"
          value={count("revise_change")}
          note="Known contract violations"
        />
        <Metric
          label="NEED MORE EVIDENCE"
          value={count("collect_evidence")}
          note="Incomplete or incompatible inputs"
        />
      </div>
      <div className="review-layout">
        <ReviewList
          reviews={reviews}
          filtered={filtered}
          total={total}
          loaded={loaded}
          query={query}
          onQueryChange={onQueryChange}
          onOpen={onOpen}
        />
        <ReviewForm {...form} />
      </div>
      <WorkflowPath />
    </>
  );
}
