let csrfToken: string | null = null;
let authEpoch = 0;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
  authEpoch += 1;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

export async function apiResponse(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const epoch = authEpoch;
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (
    !["GET", "HEAD", "OPTIONS"].includes(
      (init?.method || "GET").toUpperCase(),
    ) &&
    csrfToken &&
    !headers.has("X-CSRF-Token")
  ) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    const content = await response.json().catch(() => ({
      detail: "The backend returned an unreadable response.",
    }));
    if (epoch === authEpoch) {
      if (
        response.status === 401 &&
        !["/api/v1/auth/login", "/api/v1/auth/session"].includes(path)
      ) {
        window.dispatchEvent(new Event("proofops:unauthorized"));
      } else if (response.status === 403 && !path.startsWith("/api/v1/auth/")) {
        window.dispatchEvent(new Event("proofops:forbidden"));
      }
    }
    const detail =
      typeof content.detail === "string"
        ? content.detail
        : JSON.stringify(content.detail || content);
    throw new ApiError(response.status, detail);
  }
  return response;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  return (await apiResponse(path, init)).json() as Promise<T>;
}
