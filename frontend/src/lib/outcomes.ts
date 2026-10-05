import { CheckCircle2, XCircle, Clock3, Info } from "lucide-react";
import type { Outcome } from "../types";

export const outcomes: Record<
  Outcome,
  { label: string; short: string; icon: typeof CheckCircle2; className: string }
> = {
  request_review: {
    label: "Ready for engineering review",
    short: "Ready for review",
    icon: CheckCircle2,
    className: "ready",
  },
  revise_change: {
    label: "Revise the change",
    short: "Revise change",
    icon: XCircle,
    className: "revise",
  },
  collect_evidence: {
    label: "Collect more evidence",
    short: "Needs evidence",
    icon: Clock3,
    className: "collect",
  },
  out_of_scope: {
    label: "Outside supported scope",
    short: "Out of scope",
    icon: Info,
    className: "outside",
  },
};
