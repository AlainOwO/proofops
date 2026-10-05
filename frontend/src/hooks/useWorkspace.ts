import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Analytics, Detail, Summary } from "../types";

export function useWorkspace() {
  const [route, setRoute] = useState(
    window.location.hash.slice(1) || "/reviews",
  );
  const [reviews, setReviews] = useState<Summary[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [replay, setReplay] = useState("valid-resize");
  const [file, setFile] = useState<File | null>(null);
  const [ai, setAi] = useState("off");
  const [mode, setMode] = useState("replay");
  const [ready, setReady] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const reportId = route.match(/^\/reviews\/([a-f0-9-]{36})/)?.[1];
  const isOutcomes = route === "/outcomes";
  const routeRef = useRef(route);
  routeRef.current = route;
  const navigate = (value: string) => {
    window.location.hash = value;
  };
  useEffect(() => {
    const listener = () =>
      setRoute(window.location.hash.slice(1) || "/reviews");
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);

  const refresh = useCallback(async () => {
    const [listing, stats, health] = await Promise.all([
      api<{ items: Summary[]; total: number }>("/api/v1/reviews?limit=100"),
      api<Analytics>("/api/v1/analytics"),
      api<{ status: string }>("/readyz"),
    ]);
    setReviews(listing.items);
    setTotal(listing.total);
    setAnalytics(stats);
    setReady(health.status === "ready");
    setLoaded(true);
  }, []);
  useEffect(() => {
    refresh().catch((error) => {
      setError(error.message);
      setLoaded(true);
      setReady(false);
    });
  }, [refresh]);
  const refreshDetail = useCallback(async () => {
    if (!reportId) return;
    const suffix = route.includes("?") ? "?" + route.split("?")[1] : "";
    const response = await api<Detail>(`/api/v1/reviews/${reportId}${suffix}`);
    if (routeRef.current === route) setDetail(response);
    return response;
  }, [reportId, route]);
  useEffect(() => {
    if (!reportId) {
      setDetail(null);
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    setDetail(null);
    const poll = async () => {
      try {
        const value = await refreshDetail();
        if (
          !stopped &&
          value &&
          ["queued", "running"].includes(value.job.state)
        )
          timer = setTimeout(poll, 700);
        else if (!stopped) await refresh();
      } catch (error) {
        if (!stopped) setError((error as Error).message);
      }
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [reportId, refreshDetail, refresh]);

  async function runReview() {
    setError("");
    setBusy("review");
    try {
      const imported = file
        ? await api<{ bundle_id: string }>("/api/v1/bundles", {
            method: "POST",
            headers: { "Content-Type": "application/zip" },
            body: file,
          })
        : await api<{ bundle_id: string }>("/api/v1/bundles", {
            method: "POST",
            body: JSON.stringify({ replay }),
          });
      const queued = await api<{ review_id: string }>("/api/v1/reviews", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          bundle_id: imported.bundle_id,
          mode,
          ai_preference: ai,
        }),
      });
      navigate(`/reviews/${queued.review_id}`);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function action(key: string, callback: () => Promise<unknown>) {
    setBusy(key);
    setError("");
    try {
      await callback();
      await refreshDetail();
      await refresh();
      return true;
    } catch (error) {
      setError((error as Error).message);
      return false;
    } finally {
      setBusy("");
    }
  }
  return {
    reviews,
    total,
    analytics,
    detail,
    error,
    busy,
    query,
    replay,
    file,
    ai,
    mode,
    ready,
    loaded,
    reportId,
    isOutcomes,
    navigate,
    refresh,
    action,
    runReview,
    setError,
    setQuery,
    setReplay,
    setFile,
    setAi,
    setMode,
  };
}
