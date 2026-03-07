import { API_BASE_URL } from "./config";

export const SERVER_ENDPOINTS = {
  conversations: `${API_BASE_URL}/conversations`,
};

type ApiFetchOptions = RequestInit & {
  headers?: Record<string, string>;
};

export async function apiFetch<T = unknown>(
  url: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { headers, ...rest } = options;

  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    ...rest,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  // Handle 204 / empty responses (e.g. DELETE)
  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  // Fallback for non‑JSON payloads
  return (await response.text()) as T;
}

