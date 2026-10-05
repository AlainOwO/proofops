import { useState } from "react";

export function ReviewActions({
  busy,
  onCompareCommit,
  onDisposition,
}: {
  busy: string;
  onCompareCommit: (commit: string) => void;
  onDisposition: (disposition: string, reason: string) => Promise<boolean>;
}) {
  const [commit, setCommit] = useState("");
  const [disposition, setDisposition] = useState("rejected");
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);

  return (
    <>
      <details>
        <summary>Check applicability to another commit</summary>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            onCompareCommit(commit);
          }}
        >
          <label htmlFor="new-commit">Candidate commit</label>
          <input
            id="new-commit"
            value={commit}
            onChange={(event) => setCommit(event.target.value)}
            pattern="[a-f0-9]{40,64}"
            required
            placeholder="Full candidate commit hash"
          />
          <button className="button secondary small" type="submit">
            Check applicability
          </button>
        </form>
      </details>
      <details>
        <summary>Record an operator disposition</summary>
        <p className="muted">
          Records your decision at the current time. This does not record
          measured performance or billed savings.
        </p>
        <form
          className="disposition-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setSaved(false);
            setSaved(await onDisposition(disposition, reason));
          }}
        >
          <label htmlFor="disposition">Disposition</label>
          <select
            id="disposition"
            value={disposition}
            onChange={(event) => setDisposition(event.target.value)}
          >
            <option value="rejected">Rejected</option>
            <option value="adopted">Adopted</option>
            <option value="insufficient_evidence">Insufficient evidence</option>
            <option value="reverted">Reverted</option>
          </select>
          <label htmlFor="disposition-reason">Reason</label>
          <input
            id="disposition-reason"
            value={reason}
            maxLength={200}
            required
            onChange={(event) => {
              setReason(event.target.value);
              setSaved(false);
            }}
          />
          <button className="button secondary small" disabled={!!busy}>
            Save disposition
          </button>
          {saved && !busy && (
            <span className="muted">
              Check Outcomes for the recorded disposition.
            </span>
          )}
        </form>
      </details>
    </>
  );
}
