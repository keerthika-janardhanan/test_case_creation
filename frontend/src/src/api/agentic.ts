import { API_BASE_URL, apiClient } from "./client";
import { fetchSSE } from "../hooks/useSSE";

export async function previewAgentic(scenario: string) {
  const { data } = await apiClient.post<{ preview: string }>("/agentic/preview", { scenario });
  return data.preview;
}

export async function previewAgenticStream(
  scenario: string,
  token: string,
  onEvent: (evt: any) => void,
  signal?: AbortSignal,
) {
  const url = `${API_BASE_URL}/agentic/preview/stream`;
  await fetchSSE(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: token ? `Bearer ${token}` : "",
    },
    body: { scenario },
    onEvent,
    signal,
  });
}

export async function generatePayload(scenario: string, acceptedPreview: string) {
  const { data } = await apiClient.post<{ locators: any[]; pages: any[]; tests: any[] }>(
    "/agentic/payload",
    { scenario, acceptedPreview },
  );
  return data;
}

export async function payloadAgenticStream(
  scenario: string,
  acceptedPreview: string,
  token: string,
  onEvent: (evt: any) => void,
  signal?: AbortSignal,
) {
  const url = `${API_BASE_URL}/agentic/payload/stream`;
  await fetchSSE(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: token ? `Bearer ${token}` : "",
    },
    body: { scenario, acceptedPreview },
    onEvent,
    signal,
  });
}

export async function persistFiles(
  files: { path: string; content: string }[],
  token: string,
  frameworkRoot?: string,
) {
  const { data } = await apiClient.post<{ written: string[] }>(
    "/agentic/persist",
    { files, frameworkRoot },
    {
      headers: { Authorization: token ? `Bearer ${token}` : "" },
    },
  );
  return data.written;
}

export async function pushChanges(
  branch: string,
  message: string,
  token: string,
  frameworkRoot?: string,
) {
  const { data } = await apiClient.post<{ success: boolean }>(
    "/agentic/push",
    { branch, message, frameworkRoot },
    { headers: { Authorization: token ? `Bearer ${token}` : "" } },
  );
  return data.success;
}

export async function trialRunAgentic(testFileContent: string, headed = false, frameworkRoot?: string) {
  const { data } = await apiClient.post<{ success: boolean; logs: string }>(
    "/agentic/trial-run",
    { testFileContent, headed, frameworkRoot },
  );
  return data;
}

export async function trialRunExisting(
  testFilePath: string,
  headed = true,
  frameworkRoot?: string,
  options?: { scenario?: string; datasheet?: string; referenceId?: string; idName?: string; update?: boolean },
) {
  const { data } = await apiClient.post<{ success: boolean; logs: string; updateInfo?: any }>(
    "/agentic/trial-run-existing",
    {
      testFilePath,
      headed,
      frameworkRoot,
      scenario: options?.scenario,
      updateTestManager: options?.update ?? false,
      datasheet: options?.datasheet,
      referenceId: options?.referenceId,
      idName: options?.idName,
    },
  );
  return data;
}

export async function trialRunAgenticStream(
  testFileContent: string,
  headed: boolean,
  frameworkRoot: string | undefined,
  token: string | undefined,
  onEvent: (evt: any) => void,
  signal?: AbortSignal,
  options?: { scenario?: string; datasheet?: string; referenceId?: string; idName?: string; update?: boolean },
) {
  const url = `${API_BASE_URL}/agentic/trial-run/stream`;
  
  console.log('[TrialRunStream] Starting trial run stream');
  console.log('[TrialRunStream] URL:', url);
  console.log('[TrialRunStream] Headed:', headed);
  console.log('[TrialRunStream] Framework root:', frameworkRoot);
  console.log('[TrialRunStream] Options:', options);
  console.log('[TrialRunStream] Test file length:', testFileContent?.length, 'chars');
  
  await fetchSSE(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: token ? `Bearer ${token}` : "",
    },
    body: {
      testFileContent,
      headed,
      frameworkRoot,
      scenario: options?.scenario,
      updateTestManager: options?.update ?? false,
      datasheet: options?.datasheet,
      referenceId: options?.referenceId,
      idName: options?.idName,
    },
    onEvent: (evt) => {
      console.log('[TrialRunStream] Event received:', evt);
      onEvent(evt);
    },
    signal,
  });
  
  console.log('[TrialRunStream] Stream completed');
}

export async function keywordInspect(keyword: string, repoPath: string, branch?: string, maxAssets = 5) {
  const { data } = await apiClient.post<{
    keyword: string;
    existingAssets: { path: string; snippet: string; isTest: boolean; relevance?: number }[];
    refinedRecorderFlow: { sourceSession?: string | null; steps: any[]; stabilityWarnings: string[] } | null;
    vectorContext: { flowAvailable: boolean; vectorStepsCount: number };
    status: string;
    messages: string[];
  }>(
    "/agentic/keyword-inspect",
    { keyword, repoPath, branch, maxAssets },
  );
  return data;
}

export async function uploadDatasheet(
  file: File,
  scenario: string,
  frameworkRoot: string | undefined,
  token?: string,
) {
  const form = new FormData();
  form.append("datasheetFile", file);
  form.append("scenario", scenario);
  if (frameworkRoot) form.append("frameworkRoot", frameworkRoot);
  const { data } = await apiClient.post<{ saved: string; filename: string; scenario: string }>(
    "/config/upload_datasheet",
    form,
    { headers: { "Content-Type": "multipart/form-data", Authorization: token ? `Bearer ${token}` : "" } },
  );
  return data;
}

export async function listDatasheets(frameworkRoot?: string) {
  const { data } = await apiClient.get<{ files: string[] }>(
    "/config/list_datasheets",
    { params: { frameworkRoot } },
  );
  return data.files || [];
}

export async function renameTestCaseId(
  oldTestCaseId: string,
  newTestCaseId: string,
  frameworkRoot?: string
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post<{ success: boolean; message: string }>(
    "/config/rename_test_case_id",
    {
      oldTestCaseId,
      newTestCaseId,
      frameworkRoot,
    }
  );
  return data;
}
