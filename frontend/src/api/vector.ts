import { apiClient } from "./client";

export interface VectorRecord {
  id?: string;
  content: string;
  metadata: Record<string, any>;
}

export interface VectorQueryResponse {
  results: VectorRecord[];
}

export async function queryVectorAll(limit = 1000): Promise<VectorRecord[]> {
  const { data } = await apiClient.post<VectorQueryResponse>("/vector/query", {
    query: "",
    topK: limit,
  });
  return data.results ?? [];
}
