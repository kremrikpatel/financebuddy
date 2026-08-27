import axios from "axios";
import { useAuth } from "@/stores/auth";

export const API_URL =
  (import.meta as any).env?.VITE_API_URL ?? "/api/v1";

export const http = axios.create({ baseURL: API_URL });

let refreshPromise: Promise<string> | null = null;

http.interceptors.request.use((config) => {
  const token = useAuth.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retried) {
      original._retried = true;
      try {
        refreshPromise =
          refreshPromise ??
          useAuth.getState().refresh().finally(() => (refreshPromise = null));
        await refreshPromise;
        return http(original);
      } catch {
        useAuth.getState().logout();
      }
    }
    return Promise.reject(error);
  },
);
