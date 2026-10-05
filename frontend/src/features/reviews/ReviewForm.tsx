import {
  ArrowRight,
  FileCheck2,
  Info,
  Layers,
  LoaderCircle,
  ShieldCheck,
  Upload,
} from "lucide-react";

export interface ReviewFormProps {
  replay: string;
  file: File | null;
  ai: string;
  mode: string;
  busy: string;
  onReplayChange: (replay: string) => void;
  onFileChange: (file: File | null) => void;
  onAiChange: (ai: string) => void;
  onModeChange: (mode: string) => void;
  onRunReview: () => void;
}

export function ReviewForm({
  replay,
  file,
  ai,
  mode,
  busy,
  onReplayChange,
  onFileChange,
  onAiChange,
  onModeChange,
  onRunReview,
}: ReviewFormProps) {
  return (
    <aside
      className="panel start-panel"
      aria-labelledby="start-review-heading"
      aria-busy={busy === "review"}
    >
      <div className="start-icon">
        <Layers size={23} />
      </div>
      <h2 id="start-review-heading">Start with a replay</h2>
      <p>
        Explore a complete review with labelled synthetic evidence. No
        credentials needed.
      </p>
      <label htmlFor="replay-choice">Review scenario</label>
      <select
        id="replay-choice"
        aria-describedby="replay-evidence-note"
        value={replay}
        disabled={!!file}
        onChange={(event) => onReplayChange(event.target.value)}
      >
        <option value="valid-resize">Valid resize · 4 GiB → 2 GiB</option>
        <option value="unsafe-resize">Below the floor · 4 GiB → 1 GiB</option>
        <option value="incomplete-evidence">Missing candidate evidence</option>
      </select>
      <div className="fixture-note" id="replay-evidence-note">
        <Info size={14} />
        <span>
          Prices, approvals and workload results in these examples are
          synthetic.
        </span>
      </div>
      <details className="advanced">
        <summary>Import or configure a review</summary>
        <label className="file-upload">
          <Upload size={15} />
          <span>{file?.name || "Choose an input bundle (.zip)"}</span>
          <input
            type="file"
            accept=".zip"
            aria-label="Upload input bundle"
            onChange={(event) => onFileChange(event.target.files?.[0] || null)}
          />
        </label>
        {file && (
          <button className="text-button" onClick={() => onFileChange(null)}>
            Use supplied replay instead
          </button>
        )}
        <label htmlFor="execution-mode">Evaluation time</label>
        <select
          id="execution-mode"
          value={mode}
          onChange={(event) => onModeChange(event.target.value)}
        >
          <option value="replay">Recorded replay time</option>
          <option value="live">Current decision · AWS evidence required</option>
        </select>
        <label htmlFor="ai-mode">Explanation</label>
        <select
          id="ai-mode"
          value={ai}
          onChange={(event) => onAiChange(event.target.value)}
        >
          <option value="off">Deterministic template · no AI call</option>
          <option value="auto">Use configured model and budget</option>
        </select>
      </details>
      <button
        className="button primary full"
        onClick={onRunReview}
        disabled={!!busy}
      >
        {busy === "review" ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <FileCheck2 size={16} />
        )}
        Run review
        <ArrowRight size={16} />
      </button>
      {busy === "review" && (
        <p className="form-status" role="status">
          Importing inputs and queueing your review…
        </p>
      )}
      <div className="start-footer">
        <ShieldCheck size={13} />
        The report requests engineering review.
      </div>
    </aside>
  );
}
