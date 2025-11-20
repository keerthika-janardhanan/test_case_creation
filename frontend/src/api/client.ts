import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout to prevent hanging
});

export function buildWebSocketUrl(path: string): string {
  const base = new URL(API_BASE_URL);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  base.pathname = normalizedPath;
  return base.toString();
}
