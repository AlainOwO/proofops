export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(typeof init?.body === "string"
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  });
  const content = await response
    .json()
    .catch(() => ({ detail: "The backend returned an unreadable response." }));
  if (!response.ok) {
    const detail =
      typeof content.detail === "string"
        ? content.detail
        : JSON.stringify(content.detail || content);
    throw new Error(`${response.status}: ${detail}`);
  }
  return content as T;
}

export function money(
  value: string | null | undefined,
  currency = "USD",
  precision = 2,
): string {
  if (value === null || value === undefined) return "Not available";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(Number(value));
}
export function date(value: string) {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
export const originLabel: Record<string, string> = {
  synthetic_fixture: "Synthetic fixture",
  benchmark: "Benchmark data",
  local_observation: "Local observation",
  aws_observation: "AWS observation",
};
