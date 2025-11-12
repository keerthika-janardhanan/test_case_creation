type SSEOptions = {
  method?: "GET" | "POST";
  headers?: Record<string, string>;
  body?: any;
  onEvent?: (event: unknown) => void;
  onRawLine?: (line: string) => void;
  signal?: AbortSignal;
};

/** Parse text/event-stream payloads and invoke onEvent with parsed JSON from `data:` lines. */
export async function readSSEStream(
  response: Response,
  { onEvent, onRawLine, signal }: Pick<SSEOptions, "onEvent" | "onRawLine" | "signal">
) {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const lines = frame.split(/\r?\n/).map((l) => l.trim());
        for (const line of lines) {
          if (!line) continue;
          onRawLine?.(line);
          if (line.startsWith("data:")) {
            const json = line.slice(5).trim();
            try {
              const payload = JSON.parse(json);
              onEvent?.(payload);
            } catch {
              // ignore parse errors on non-JSON frames
            }
          }
        }
      }
    }
  } finally {
    try { await reader.cancel(); } catch { /* noop */ }
  }
}

export async function fetchSSE(url: string, opts: SSEOptions = {}) {
  const { method = "GET", headers = {}, body, onEvent, onRawLine, signal } = opts;
  const init: RequestInit = {
    method,
    headers: {
      Accept: "text/event-stream",
      ...headers,
    },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
    signal,
  };
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`SSE request failed: ${res.status}`);
  await readSSEStream(res, { onEvent, onRawLine, signal });
}
