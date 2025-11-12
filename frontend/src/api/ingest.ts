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

export async function deleteVectorDoc(docId: string): Promise<JobResponse> {
  const { data } = await apiClient.delete<JobResponse>(
    `/api/vector/docs/${encodeURIComponent(docId)}`,
  );
  return data;
}

export async function deleteVectorSource(source: string): Promise<JobResponse> {
  const { data } = await apiClient.delete<JobResponse>("/api/vector/docs", {
    params: { source },
  });
  return data;
}
