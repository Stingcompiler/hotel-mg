import { useQuery } from "@tanstack/react-query";

import { api, data } from "./client";
import { session } from "./session";

/** Query keys in one place so mutations can invalidate them (spec §10.5). */
export const keys = {
  systemStatus: ["system", "status"] as const,
  settings: ["system", "settings"] as const,
  me: ["auth", "me"] as const,
  currentShift: ["shifts", "current"] as const,
  taskCount: ["followups", "tasks", "count"] as const,
  importRuns: ["owner", "import", "runs"] as const,
};

/** Read before login: decides the reception or owner shell. */
export function useSystemStatus() {
  return useQuery({
    queryKey: keys.systemStatus,
    queryFn: () => data(api.GET("/api/v1/system/status")),
    refetchInterval: 60_000,
  });
}

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => data(api.GET("/api/v1/auth/me")),
    enabled: !!session.token,
  });
}

export function useHotelSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => data(api.GET("/api/v1/system/settings")),
    enabled: !!session.token,
    staleTime: 5 * 60_000,
  });
}

export function useCurrentShift(enabled = true) {
  return useQuery({
    queryKey: keys.currentShift,
    queryFn: () => data(api.GET("/api/v1/shifts/current")),
    enabled: enabled && !!session.token,
  });
}

/** Follow-up badge; refetched every 30 s like the follow-ups screen. */
export function useTaskCount(enabled = true) {
  return useQuery({
    queryKey: keys.taskCount,
    queryFn: () => data(api.GET("/api/v1/followups/tasks/count")),
    enabled: enabled && !!session.token,
    refetchInterval: 30_000,
  });
}

export function useLatestImport(enabled = true) {
  return useQuery({
    queryKey: keys.importRuns,
    queryFn: () => data(api.GET("/api/v1/owner/import/runs")),
    enabled: enabled && !!session.token,
    select: (page) => page.results.find((run) => run.status === "ok") ?? null,
  });
}
