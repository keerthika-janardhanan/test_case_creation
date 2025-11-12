import { apiClient } from "./client";

export async function uploadFile(
  file: File,
  target: "uploads" | "framework-data",
  token: string,
  frameworkRoot?: string,
) {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams();
  params.set("target", target);
  if (frameworkRoot) params.set("frameworkRoot", frameworkRoot);

  const { data } = await apiClient.post<{ path: string }>(
    `/files/upload?${params.toString()}`,
    form,
    {
      headers: {
        Authorization: token ? `Bearer ${token}` : "",
        "Content-Type": "multipart/form-data",
      },
    },
  );
  return data.path;
}
