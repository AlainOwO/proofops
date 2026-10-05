import { Layers } from "lucide-react";
import { originLabel } from "../lib/format";

export function Origin({ value }: { value: string | null }) {
  return (
    <span className="origin">
      <Layers size={12} />
      {originLabel[value || ""] || "Awaiting report"}
    </span>
  );
}
