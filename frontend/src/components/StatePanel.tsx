import type { ReactNode } from "react";
import { FileCheck2, LoaderCircle, XCircle } from "lucide-react";

export function StatePanel({
  title,
  children,
  kind = "empty",
  action,
}: {
  title: string;
  children: ReactNode;
  kind?: "empty" | "loading" | "error";
  action?: ReactNode;
}) {
  const Icon =
    kind === "loading" ? LoaderCircle : kind === "error" ? XCircle : FileCheck2;
  return (
    <div className={`empty state-${kind}`} role="status">
      <Icon
        size={30}
        className={kind === "loading" ? "spin" : undefined}
        aria-hidden="true"
      />
      <h3>{title}</h3>
      <p>{children}</p>
      {action && <div className="state-action">{action}</div>}
    </div>
  );
}
