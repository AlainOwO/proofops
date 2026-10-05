import type { ReactNode } from "react";

export function Metric({
  label,
  value,
  note,
  accent,
  loading = false,
}: {
  label: string;
  value: ReactNode;
  note: string;
  accent?: boolean;
  loading?: boolean;
}) {
  return (
    <div className={`metric ${accent ? "accent" : ""}`} aria-busy={loading}>
      <span className="eyebrow">{label}</span>
      <strong
        className={
          typeof value === "string" &&
          ["Unavailable", "Not available"].includes(value)
            ? "metric-unavailable"
            : undefined
        }
      >
        {loading ? (
          <>
            <span className="sr-only">Loading</span>
            <span className="metric-placeholder" aria-hidden="true" />
          </>
        ) : (
          value
        )}
      </strong>
      <small>{note}</small>
    </div>
  );
}
