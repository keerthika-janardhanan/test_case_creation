import { apiClient } from "./client";

export interface UpdateTestManagerPayload {
  scenario: string;
  datasheet?: string;
  referenceId?: string;
  idName?: string;
  frameworkRoot?: string;
  newDescription?: string; // optional TestCaseDescription override
  allowFreeformCreate?: boolean; // allow creating non-ID-like scenario as new TestCaseID
  execute?: string; // value for Execute column (e.g., Yes/No)
}

export async function updateTestManager(
  payload: UpdateTestManagerPayload,
  token: string,
) {
  const { data } = await apiClient.post<{ path: string; mode: string; description: string }>(
    "/config/update_test_manager",
    payload,
    { headers: { Authorization: token ? `Bearer ${token}` : "" } },
  );
  return data;
}

export interface TestManagerRow {
  TestCaseID: string;
  TestCaseDescription: string;
  Execute: string;
  DatasheetName: string;
  ReferenceID: string;
  IDName: string;
}

export async function listTestManager(frameworkRoot?: string) {
  const { data } = await apiClient.get<{ rows: TestManagerRow[] }>(
    "/config/list_test_manager",
    { params: { frameworkRoot } },
  );
  return data.rows || [];
}
