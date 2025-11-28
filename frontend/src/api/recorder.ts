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

export async function finalizeRecorderBySession(sessionId: string): Promise<any> {
  console.log('[API] Calling /recorder/finalize with sessionId:', sessionId);
  const startTime = Date.now();
  try {
    const { data } = await apiClient.post(
      "/recorder/finalize",
      { sessionId },
    );
    const duration = Date.now() - startTime;
    console.log(`[API] /recorder/finalize completed in ${duration}ms:`, data);
    return data;
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`[API] /recorder/finalize failed after ${duration}ms:`, error);
    throw error;
  }
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

// New modular endpoints (synchronous - no Celery needed)
export async function startRecorder(payload: { url: string; sessionName?: string; options?: Record<string, unknown> }) {
  const { data } = await apiClient.post<{ sessionId: string; status: string }>("/recorder-sync/start", payload);
  return data;
}

export async function stopRecorder(sessionId: string) {
  const { data } = await apiClient.post<{ status: string }>("/recorder-sync/stop", { sessionId });
  return data;
}

export async function getRecorderStatus(sessionId: string) {
  const { data } = await apiClient.get<{ status: string; artifacts: Record<string, string>; files: string[]; isRunning: boolean }>(
    `/recorder-sync/status/${encodeURIComponent(sessionId)}`,
  );
  return data;
}

export function buildArtifactUrl(sessionId: string, artifactPath: string) {
  // Use legacy download endpoint exposed by FastAPI main
  const encoded = encodeURIComponent(artifactPath);
  return `${API_BASE_URL}/api/recorder/${encodeURIComponent(sessionId)}/artifacts/${encoded}`;
}

