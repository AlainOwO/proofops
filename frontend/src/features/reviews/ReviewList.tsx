import { ArrowUpRight, Search } from "lucide-react";
import { Badge } from "../../components/Badge";
import { StatePanel } from "../../components/StatePanel";
import { Origin } from "../../components/Origin";
import { date, human } from "../../lib/format";
import type { Summary } from "../../types";
import { useCanWrite } from "../auth/AuthGate";

export interface ReviewListProps {
  reviews: Summary[];
  filtered: Summary[];
  total: number | null;
  loading: boolean;
  busy: boolean;
  onRetry: () => void;
  query: string;
  onQueryChange: (query: string) => void;
  onOpen: (id: string) => void;
}

export function ReviewList({
  reviews,
  filtered,
  total,
  loading,
  busy,
  onRetry,
  query,
  onQueryChange,
  onOpen,
}: ReviewListProps) {
  const canWrite = useCanWrite();
  return (
    <section
      className="panel reviews-panel"
      aria-labelledby="recent-reviews-heading"
    >
      <div className="panel-heading">
        <div>
          <h2 id="recent-reviews-heading">Recent reviews</h2>
          <p>
            {loading
              ? "Fetching saved reviews…"
              : total === null
                ? "Saved reviews could not be loaded."
                : query
                  ? `${filtered.length} matching of ${reviews.length} displayed reviews`
                  : `Latest ${reviews.length} of ${total} reviews`}
          </p>
        </div>
        <label className="search">
          <Search size={15} />
          <input
            type="search"
            aria-label="Filter displayed reviews"
            placeholder="Filter reviews"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
        </label>
      </div>
      {loading ? (
        <StatePanel title="Loading reviews" kind="loading">
          Fetching saved reviews from the workspace.
        </StatePanel>
      ) : total === null ? (
        <StatePanel
          title="Reviews unavailable"
          kind="error"
          action={
            <button
              className="button secondary"
              onClick={onRetry}
              disabled={busy}
            >
              Retry loading reviews
            </button>
          }
        >
          Check that the backend is running, then try again.
        </StatePanel>
      ) : !filtered.length ? (
        <StatePanel
          title={
            query
              ? "No matching reviews"
              : canWrite
                ? "Your first review starts here"
                : "No saved reviews"
          }
          action={
            query ? (
              <button
                className="button secondary"
                onClick={() => onQueryChange("")}
              >
                Clear filter
              </button>
            ) : canWrite ? (
              <button
                className="button secondary"
                onClick={() =>
                  document.getElementById("replay-choice")?.focus()
                }
              >
                Choose a scenario
              </button>
            ) : undefined
          }
        >
          {query
            ? "Try another service, commit or outcome, or clear the filter to see your saved reviews."
            : canWrite
              ? "Run a supplied replay or import a sanitized bundle to see the evidence behind a change."
              : "An administrator can add reviews to this workspace."}
        </StatePanel>
      ) : (
        <div className="table-scroll">
          <table className="reviews-table" aria-label="Recent reviews">
            <thead>
              <tr>
                <th>Service / change</th>
                <th>Decision</th>
                <th>Evidence origin</th>
                <th aria-label="Open review" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id}>
                  <td>
                    <button
                      className="review-link"
                      onClick={() => onOpen(item.id)}
                    >
                      {item.service || "Queued review"}
                      <span>
                        <code>
                          {item.candidate_commit?.slice(0, 8) ||
                            item.id.slice(0, 8)}
                        </code>{" "}
                        · {date(item.created_at)}
                      </span>
                    </button>
                  </td>
                  <td data-label="Decision">
                    <Badge outcome={item.outcome} state={human(item.state)} />
                  </td>
                  <td data-label="Evidence">
                    <Origin value={item.origin} />
                  </td>
                  <td className="review-open">
                    <button
                      className="icon-button"
                      aria-label={`Open review ${item.id}`}
                      onClick={() => onOpen(item.id)}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
