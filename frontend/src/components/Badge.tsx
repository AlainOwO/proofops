import { LoaderCircle } from "lucide-react";
import { outcomes } from "../lib/outcomes";
import type { Outcome } from "../types";

export function Badge({
  outcome,
  state,
}: {
  outcome: Outcome | null;
  state?: string;
}) {
  const entry = outcome ? outcomes[outcome] : null;
  const Icon = entry?.icon || LoaderCircle;
  return (
    <span className={`badge ${entry?.className || "outside"}`}>
      <Icon size={13} />
      {entry?.short || state || "Queued"}
    </span>
  );
}
