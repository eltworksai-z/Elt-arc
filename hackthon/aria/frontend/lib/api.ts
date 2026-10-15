import type { ServerEvent } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail), response.status);
  }
  return response.json() as Promise<T>;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export function subscribe(path: string, onEvent: (event: ServerEvent) => void): () => void {
  let lastSeq = 0;
  let source: EventSource | null = null;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    source = new EventSource(`${API_URL}${path}?after=${lastSeq}`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as ServerEvent;
      if (event.seq <= lastSeq) return;
      lastSeq = event.seq;
      onEvent(event);
    };
    source.onerror = () => {
      source?.close();
      if (!closed) retry = setTimeout(open, 1500);
    };
  };
  open();
  return () => {
    closed = true;
    clearTimeout(retry);
    source?.close();
  };
}
