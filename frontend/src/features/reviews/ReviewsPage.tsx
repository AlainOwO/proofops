import { Plus } from "lucide-react";
import { Metric } from "../../components/Metric";
import type { Analytics, Outcome, Summary } from "../../types";
import { ReviewList } from "./ReviewList";
import { ReviewForm, type ReviewFormProps } from "./ReviewForm";
import { HowItWorks } from "./HowItWorks";
import { useCanWrite } from "../auth/AuthGate";

export function ReviewsPage({
  reviews,
  total,
  analytics,
  loading,
  onRetry,
  query,
  onQueryChange,
  onOpen,
  form,
}: {
  reviews: Summary[];
  total: number | null;
  analytics: Analytics | null;
  loading: boolean;
  onRetry: () => void;
  query: string;
  onQueryChange: (query: string) => void;
  onOpen: (id: string) => void;
  form: ReviewFormProps;
}) {
  const canWrite = useCanWrite();
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
        {canWrite && (
          <button
            className="button primary"
            onClick={() => document.getElementById("replay-choice")?.focus()}
          >
            <Plus size={16} />
            New review
          </button>
        )}
      </div>
      <div className="metric-grid four">
        <Metric
          label="TOTAL REVIEWS"
          value={total ?? "Unavailable"}
          note="Saved in this workspace"
          loading={loading}
        />
        <Metric
          label="READY FOR REVIEW"
          value={count("request_review")}
          note="Required checks passed"
          loading={loading}
          accent
        />
        <Metric
          label="CHANGES TO REVISE"
          value={count("revise_change")}
          note="Known contract violations"
          loading={loading}
        />
        <Metric
          label="NEED MORE EVIDENCE"
          value={count("collect_evidence")}
          note="Incomplete or incompatible inputs"
          loading={loading}
        />
      </div>
      <div className="review-layout">
        <ReviewList
          reviews={reviews}
          filtered={filtered}
          total={total}
          loading={loading}
          busy={!!form.busy}
          onRetry={onRetry}
          query={query}
          onQueryChange={onQueryChange}
          onOpen={onOpen}
        />
        <div className="review-sidebar">
          {canWrite && <ReviewForm {...form} />}
          <HowItWorks />
        </div>
      </div>
    </>
  );
}
