import { apiClient } from "./client";

export interface TestCaseRecord {
  [key: string]: unknown;
}

export interface TestCaseResponse {
  records: TestCaseRecord[];
  excel?: string;
}

export interface TestCaseRequestPayload {
  story: string;
  llmOnly?: boolean;
  asExcel?: boolean;
}

export async function generateTestCases(
  payload: TestCaseRequestPayload,
): Promise<TestCaseResponse> {
  const { data } = await apiClient.post<TestCaseResponse>(
    "/api/test-cases/generate",
    payload,
  );
  return data;
}

export async function generateTestCasesWithTemplate(
  story: string,
  llmOnly: boolean,
  file: File,
): Promise<TestCaseResponse> {
  const form = new FormData();
  form.append("story", story);
  form.append("llmOnly", String(llmOnly));
  form.append("template", file);
  const { data } = await apiClient.post<TestCaseResponse>(
    "/api/test-cases/generate-upload",
    form,
  );
  return data;
}
