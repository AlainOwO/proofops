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
