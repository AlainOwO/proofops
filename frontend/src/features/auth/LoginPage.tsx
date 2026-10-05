import { useState } from "react";
import { LoaderCircle, ShieldCheck } from "lucide-react";
import { api, ApiError } from "../../api";
import type { SessionInfo } from "../../types";

export function LoginPage({
  notice,
  onSignedIn,
}: {
  notice: string;
  onSignedIn: (session: SessionInfo) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <main className="auth-page">
      <section className="panel auth-panel" aria-labelledby="login-heading">
        <div className="auth-brand">
          <ShieldCheck size={28} aria-hidden="true" />
          <span>ProofOps.</span>
        </div>
        <h1 id="login-heading">Sign in to ProofOps</h1>
        <p>Review changes and evidence in your workspace.</p>
        {notice && <p role="status">{notice}</p>}
        {error && (
          <p role="alert" className="auth-error">
            {error}
          </p>
        )}
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            setError("");
            try {
              const challenge = await api<{
                csrf_token: string | null;
                public_demo: boolean;
              }>("/api/v1/auth/login");
              const session = challenge.public_demo
                ? await api<SessionInfo>("/api/v1/auth/session")
                : await api<SessionInfo>("/api/v1/auth/login", {
                    method: "POST",
                    headers: { "X-CSRF-Token": challenge.csrf_token! },
                    body: JSON.stringify({ username, password }),
                  });
              onSignedIn(session);
            } catch (error) {
              setError(
                error instanceof ApiError && error.status === 429
                  ? "Unable to sign in. Try again later."
                  : error instanceof ApiError && error.status === 401
                    ? "Invalid username or password."
                    : "Unable to sign in. Please try again.",
              );
            } finally {
              setPassword("");
              setBusy(false);
            }
          }}
        >
          <label htmlFor="login-username">Username</label>
          <input
            id="login-username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            maxLength={64}
            required
            disabled={busy}
          />
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            maxLength={128}
            required
            disabled={busy}
          />
          <button className="button primary full" disabled={busy}>
            {busy && (
              <LoaderCircle size={16} className="spin" aria-hidden="true" />
            )}
            Sign in
          </button>
        </form>
        <p className="auth-help">
          Need access? Ask your workspace administrator.
        </p>
      </section>
    </main>
  );
}
