import type { TokenPair } from "@/types";

const ACCESS_KEY = "ff.access_token";
const REFRESH_KEY = "ff.refresh_token";

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY);
}

export function setSession(pair: TokenPair): void {
  sessionStorage.setItem(ACCESS_KEY, pair.access_token);
  sessionStorage.setItem(REFRESH_KEY, pair.refresh_token);
}

export function clearSession(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

export function isLoggedIn(): boolean {
  return getAccessToken() !== null;
}
