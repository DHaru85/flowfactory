import { http } from "@/api/client";
import { clearSession, getRefreshToken, setSession } from "@/auth/session";
import type { AppVisibilityOut, LoginBody, MeOut, RegisterBody, TokenPair } from "@/types";

export async function login(body: LoginBody): Promise<TokenPair> {
  const { data } = await http.post<TokenPair>("/auth/login", body);
  setSession(data);
  return data;
}

export async function register(body: RegisterBody): Promise<TokenPair> {
  const { data } = await http.post<TokenPair>("/auth/register", body);
  setSession(data);
  return data;
}

export async function logout(): Promise<void> {
  const refresh_token = getRefreshToken();
  try {
    await http.post("/auth/logout", { refresh_token });
  } finally {
    clearSession();
  }
}

export async function fetchMe(): Promise<MeOut> {
  const { data } = await http.get<MeOut>("/auth/me");
  return data;
}

export async function fetchApps(): Promise<AppVisibilityOut[]> {
  const { data } = await http.get<AppVisibilityOut[]>("/auth/apps");
  return data;
}
