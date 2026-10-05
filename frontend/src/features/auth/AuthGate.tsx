import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ShieldCheck } from "lucide-react";
import { api, ApiError, setCsrfToken } from "../../api";
import type { SessionInfo } from "../../types";
import { LoginPage } from "./LoginPage";

const AuthContext = createContext<{
  session: SessionInfo;
  logout: () => Promise<void>;
  signingOut: boolean;
} | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("Authenticated workspace required.");
  return value;
}

export function useCanWrite() {
  const { session } = useAuth();
  return session.role === "admin" && !session.public_demo;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [message, setMessage] = useState("");
  const [signingOut, setSigningOut] = useState(false);
  const attempt = useRef(0);

  const accept = useCallback((value: SessionInfo | null) => {
    attempt.current += 1;
    setCsrfToken(value?.csrf_token ?? null);
    setSession(value);
    setLoading(false);
    setUnavailable(false);
  }, []);

  const expire = useCallback(() => {
    accept(null);
    setMessage("Your session expired. Sign in again.");
  }, [accept]);

  const load = useCallback(
    async (initial = false) => {
      const current = ++attempt.current;
      if (initial) setLoading(true);
      try {
        const value = await api<SessionInfo>("/api/v1/auth/session");
        if (current === attempt.current) accept(value);
      } catch (error) {
        if (current !== attempt.current) return;
        if (error instanceof ApiError && error.status === 401) {
          accept(null);
        } else if (initial) {
          setLoading(false);
          setUnavailable(true);
        }
      }
    },
    [accept],
  );

  useEffect(() => {
    void load(true);
    const refreshIdentity = () => {
      void load();
    };
    window.addEventListener("proofops:unauthorized", expire);
    window.addEventListener("proofops:forbidden", refreshIdentity);
    window.addEventListener("focus", refreshIdentity);
    return () => {
      attempt.current += 1;
      window.removeEventListener("proofops:unauthorized", expire);
      window.removeEventListener("proofops:forbidden", refreshIdentity);
      window.removeEventListener("focus", refreshIdentity);
    };
  }, [expire, load]);

  useEffect(() => {
    if (!session?.expires_at) return;
    const timeout = setTimeout(
      expire,
      Math.max(0, Date.parse(session.expires_at) - Date.now()),
    );
    return () => clearTimeout(timeout);
  }, [session?.expires_at, expire]);

  const logout = async () => {
    setSigningOut(true);
    setMessage("");
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
      accept(null);
      window.location.hash = "/login";
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) accept(null);
      else setMessage("Sign out failed. Try again.");
    } finally {
      setSigningOut(false);
    }
  };

  if (loading || unavailable) {
    return (
      <main className="auth-page">
        <section className="panel auth-panel">
          <ShieldCheck size={28} aria-hidden="true" />
          <h1>
            {loading ? "Checking your session" : "Sign-in service unavailable"}
          </h1>
          <p role="status">
            {loading
              ? "Connecting to ProofOps…"
              : "The workspace cannot verify access. Try again when the backend is available."}
          </p>
          {unavailable && (
            <button
              className="button primary"
              onClick={() => {
                void load(true);
              }}
            >
              Retry sign-in service
            </button>
          )}
        </section>
      </main>
    );
  }
  if (!session) {
    return (
      <LoginPage
        notice={message}
        onSignedIn={(value) => {
          setMessage("");
          accept(value);
          if (window.location.hash === "#/login" || !window.location.hash)
            window.location.hash = "/reviews";
        }}
      />
    );
  }
  return (
    <AuthContext.Provider value={{ session, logout, signingOut }}>
      {message && (
        <div role="alert" className="auth-notice">
          {message}
        </div>
      )}
      {children}
    </AuthContext.Provider>
  );
}
