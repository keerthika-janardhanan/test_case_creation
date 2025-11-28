import { API_BASE_URL } from "./client";
import { fetchSSE } from "../hooks/useSSE";

export async function streamTrial(
  spec: string,
  token: string,
  headed = true,
  frameworkRoot?: string,
  onEvent?: (evt: any) => void,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  params.set("spec", spec);
  if (headed) params.set("headed", "true");
  if (frameworkRoot) params.set("frameworkRoot", frameworkRoot);
  const url = `${API_BASE_URL}/trial/stream?${params.toString()}`;
  await fetchSSE(url, {
    method: "GET",
    headers: {
      Authorization: token ? `Bearer ${token}` : "",
    },
    onEvent,
    signal,
  });
}
