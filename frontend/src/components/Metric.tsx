import type { ReactNode } from "react";

export function Metric({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: ReactNode;
  note: string;
  accent?: boolean;
}) {
  return (
    <div className={`metric ${accent ? "accent" : ""}`}>
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
