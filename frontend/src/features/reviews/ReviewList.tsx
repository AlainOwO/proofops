import { ArrowUpRight, Search } from "lucide-react";
import { Badge } from "../../components/Badge";
import { Empty } from "../../components/Empty";
import { Origin } from "../../components/Origin";
import { date, human } from "../../lib/format";
import type { Summary } from "../../types";

export interface ReviewListProps {
  reviews: Summary[];
  filtered: Summary[];
  total: number | null;
  loaded: boolean;
  query: string;
  onQueryChange: (query: string) => void;
  onOpen: (id: string) => void;
}

export function ReviewList({
  reviews,
  filtered,
  total,
  loaded,
  query,
  onQueryChange,
  onOpen,
}: ReviewListProps) {
  return (
    <section className="panel reviews-panel">
      <div className="panel-heading">
        <div>
          <h2>Recent reviews</h2>
          <p>
            {loaded
              ? `Latest ${reviews.length} of ${total} reviews`
              : "Loading backend state…"}
          </p>
        </div>
        <label className="search">
          <Search size={15} />
          <input
            aria-label="Filter displayed reviews"
            placeholder="Filter reviews"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
        </label>
      </div>
      {!filtered.length ? (
        <Empty
          title={
            query
              ? "No matching reviews"
              : !loaded
                ? "Loading reviews"
                : total === null
                  ? "Reviews unavailable"
                  : "Your first review starts here"
          }
        >
          {query
            ? "Try another service, commit or outcome."
            : "Run a supplied replay or import a sanitized bundle to see the evidence behind a change."}
        </Empty>
      ) : (
        <div className="table-scroll">
          <table>
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
                  <td>
                    <Badge outcome={item.outcome} state={human(item.state)} />
                  </td>
                  <td>
                    <Origin value={item.origin} />
                  </td>
                  <td>
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
