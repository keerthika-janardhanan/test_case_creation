import { apiClient } from "./client";

export interface JobDetail {
  jobId: string;
  type: string;
  status: string;
  payload?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const { data } = await apiClient.get<JobDetail>(
    `/api/jobs/${encodeURIComponent(jobId)}`,
  );
  return data;
}

