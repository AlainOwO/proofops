import { XCircle } from "lucide-react";

export function ErrorBanner({
  error,
  onDismiss,
}: {
  error: string;
  onDismiss: () => void;
}) {
  return (
    <>
      {error && (
        <div role="alert" className="error-banner">
          <XCircle size={18} />
          <div>
            <strong>Request failed</strong>
            <p>{error}</p>
          </div>
          <button
            className="text-button"
            onClick={onDismiss}
            aria-label="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}
    </>
  );
}
