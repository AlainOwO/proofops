import type { ReactNode } from "react";

export function TableScroll({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <>
      <p className="table-hint">Scroll horizontally to see all columns.</p>
      <div
        className="table-scroll"
        role="region"
        aria-label={label}
        tabIndex={0}
      >
        {children}
      </div>
    </>
  );
}
