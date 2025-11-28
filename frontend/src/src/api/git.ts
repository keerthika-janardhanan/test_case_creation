import { apiClient } from "./client";

export interface GitPushRequest {
  repoUrl: string;
  branch: string;
  commitMessage: string;
}

export interface GitPushResponse {
  success: boolean;
  message: string;
}

export async function pushToGit(request: GitPushRequest): Promise<GitPushResponse> {
  const { data } = await apiClient.post<GitPushResponse>("/api/git/push", request);
  return data;
}
