import { useState, type ReactNode } from "react";
import { apiResponse } from "../api";

export function DownloadLink({
  href,
  filename,
  className,
  children,
}: {
  href: string;
  filename: string;
  className: string;
  children: ReactNode;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <a
        href={href}
        download={filename}
        className={className}
        aria-disabled={busy}
        onClick={async (event) => {
          event.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          try {
            const response = await apiResponse(href);
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 0);
          } catch (error) {
            setError((error as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {children}
      </a>
      {error && (
        <span role="alert" className="auth-error">
          {error}
        </span>
      )}
    </>
  );
}
