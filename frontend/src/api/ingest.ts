import { apiClient } from "./client";

export interface JobResponse {
  jobId: string;
}

export interface IngestJiraPayload {
  jql: string;
}

export interface IngestWebsitePayload {
  url: string;
  maxDepth: number;
}

export async function ingestJira(payload: IngestJiraPayload): Promise<JobResponse> {
  const { data } = await apiClient.post<JobResponse>("/api/ingest/jira", payload);
  return data;
}

export async function ingestWebsite(payload: IngestWebsitePayload): Promise<JobResponse> {
  const { data } = await apiClient.post<JobResponse>("/api/ingest/website", payload);
  return data;
}

export async function ingestDocuments(files: FileList): Promise<JobResponse> {
  const formData = new FormData();
  Array.from(files).forEach((file) => {
    formData.append("files", file, file.name);
  });
  const { data } = await apiClient.post<JobResponse>("/api/ingest/documents", formData);
  return data;
}

export async function deleteVectorDoc(docId: string): Promise<any> {
  const { data } = await apiClient.delete(
    `/api/vector/docs/sync/${encodeURIComponent(docId)}`,
  );
  return data;
}

export async function deleteVectorSource(source: string): Promise<any> {
  const { data } = await apiClient.delete("/api/vector/docs/sync", {
    params: { source },
  });
  return data;
}

export interface VectorDocument {
  id: string;
  content: string;
  metadata: Record<string, any>;
}

export interface VectorQueryResponse {
  results: VectorDocument[];
  total?: number;
}

export async function queryVectorAll(limit: number = 100): Promise<VectorQueryResponse> {
  const { data } = await apiClient.post<VectorQueryResponse>("/vector/query", {
    query: "",
    topK: limit,
  });
  return data;
}
