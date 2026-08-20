import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { message } from "antd";

import { clearSession, getAccessToken, getRefreshToken, setSession } from "@/auth/session";
import type { ErrorBody, TokenPair } from "@/types";

export function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const rec = value as Record<string, unknown>;
  return typeof rec.code === "string" && typeof rec.message === "string";
}

export function errorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err) && isErrorBody(err.response?.data)) {
    return err.response.data.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

export const http = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) {
    return null;
  }
  const { data } = await axios.post<TokenPair>("/api/v1/auth/refresh", { refresh_token });
  setSession(data);
  return data.access_token;
}

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<unknown>) => {
    const status = error.response?.status;
    const original = error.config as RetryConfig | undefined;
    if (
      status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes("/auth/login") &&
      !original.url?.includes("/auth/register")
    ) {
      original._retry = true;
      try {
        if (!refreshing) {
          refreshing = refreshAccess().finally(() => {
            refreshing = null;
          });
        }
        const next = await refreshing;
        if (!next) {
          clearSession();
          window.location.assign("/login");
          return Promise.reject(error);
        }
        original.headers.Authorization = `Bearer ${next}`;
        return http.request(original);
      } catch {
        clearSession();
        window.location.assign("/login");
        return Promise.reject(error);
      }
    }
    if (status === 403) {
      const body = error.response?.data;
      message.error(isErrorBody(body) ? body.message : "无权访问");
    }
    return Promise.reject(error);
  },
);
