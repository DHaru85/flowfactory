import { createContext, useContext } from "react";

import type { AppVisibilityOut, MeOut } from "@/types";

export interface SessionState {
  me: MeOut | null;
  apps: AppVisibilityOut[];
  reload: () => Promise<void>;
}

export const SessionContext = createContext<SessionState>({
  me: null,
  apps: [],
  reload: async () => undefined,
});

export function useSession(): SessionState {
  return useContext(SessionContext);
}

export function findApp(apps: AppVisibilityOut[], key: string): AppVisibilityOut | undefined {
  return apps.find((item) => item.app_key === key);
}
