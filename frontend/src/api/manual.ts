import { apiClient } from "./client";

export interface ManualTableRequest {
  story: string;
  dbQuery?: string;
  scope?: string;
  coverage?: "grouped" | "full";
  includeUnlabeled?: boolean;
  includeLogin?: boolean;
}

export async function generateManualTable(payload: ManualTableRequest) {
  const { data } = await apiClient.post<{ markdown: string }>("/manual/table", payload);
  return data.markdown;
}
