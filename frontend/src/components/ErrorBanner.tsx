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
            <strong>Something needs attention</strong>
            <p>{error}</p>
          </div>
          <button className="text-button" onClick={onDismiss}>
            Dismiss
          </button>
        </div>
      )}
    </>
  );
}
