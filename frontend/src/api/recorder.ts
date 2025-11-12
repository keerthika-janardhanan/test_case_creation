import { apiClient } from "./client";
import { API_BASE_URL } from "./client";

export interface FinalizeRecorderPayload {
  sessionDir: string;
}

export interface RecorderAutoIngest {
  status: string;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface RecorderSessionResponse {
  sessionDir: string;
  listing: Record<string, unknown>;
  metadata: Record<string, unknown> | null;
  warnings: string[];
  autoIngest: RecorderAutoIngest;
}

export interface RecorderSessionCreatePayload {
  url: string;
  flowName?: string;
  options?: Record<string, unknown>;
}

export interface RecorderSessionCreateResponse {
  jobId: string;
  sessionId: string;
}

export async function createRecorderSession(
  payload: RecorderSessionCreatePayload,
): Promise<RecorderSessionCreateResponse> {
  const { data } = await apiClient.post<RecorderSessionCreateResponse>(
    "/api/recorder/sessions",
    payload,
  );
  return data;
}

export async function stopRecorderSession(sessionId: string): Promise<{ jobId: string }> {
  const { data } = await apiClient.post<{ jobId: string }>(
    `/api/recorder/${encodeURIComponent(sessionId)}/stop`,
    {},
  );
  return data;
}

export async function finalizeRecorderSession(
  payload: FinalizeRecorderPayload,
): Promise<RecorderSessionResponse> {
  const { data } = await apiClient.post<RecorderSessionResponse>(
    "/api/refined-flows/finalize",
    payload,
  );
  return data;
}

export async function finalizeRecorderBySession(sessionId: string): Promise<RecorderSessionResponse> {
  const { data } = await apiClient.post<RecorderSessionResponse>(
    "/recorder/finalize",
    { sessionId },
  );
  return data;
}

export async function publishRecorderEvent(
  sessionId: string,
  message: string,
  level: "info" | "warning" | "error" = "info",
  details?: Record<string, unknown>,
): Promise<void> {
  await apiClient.post(`/api/recorder/${encodeURIComponent(sessionId)}/events`, {
    message,
    level,
    details,
  });
}

// New modular endpoints
export async function startRecorder(payload: { url: string; sessionName?: string; options?: Record<string, unknown> }) {
  const { data } = await apiClient.post<{ sessionId: string; status: string }>("/recorder/start", payload);
  return data;
}

export async function stopRecorder(sessionId: string) {
  const { data } = await apiClient.post<{ status: string }>("/recorder/stop", { sessionId });
  return data;
}

export async function getRecorderStatus(sessionId: string) {
  const { data } = await apiClient.get<{ status: string; artifacts: Record<string, string>; files: string[] }>(
    `/recorder/status/${encodeURIComponent(sessionId)}`,
  );
  return data;
}

export function buildArtifactUrl(sessionId: string, artifactPath: string) {
  // Use legacy download endpoint exposed by FastAPI main
  const encoded = encodeURIComponent(artifactPath);
  return `${API_BASE_URL}/api/recorder/${encodeURIComponent(sessionId)}/artifacts/${encoded}`;
}

