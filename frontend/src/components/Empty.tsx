import type { ReactNode } from "react";
import { FileCheck2 } from "lucide-react";

export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <FileCheck2 size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
