import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, data } from "@/api/client";
import { keys } from "@/api/queries";

export const stayKey = (id: string) => ["stays", id] as const;
export const folioKey = (id: string) => ["folios", id] as const;

export function useStay(id: string) {
  return useQuery({ queryKey: stayKey(id), queryFn: () => data(api.GET("/api/v1/stays/{id}", { params: { path: { id } } })) });
}

export function useFolio(id: string | undefined) {
  return useQuery({
    queryKey: folioKey(id ?? ""),
    queryFn: () => data(api.GET("/api/v1/folios/{id}", { params: { path: { id: id! } } })),
    enabled: !!id,
  });
}

/** After any stay action: the stay, its folio, the board and the shift totals change. */
export function useRefreshStay(stayId: string, folioId: string | undefined) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: stayKey(stayId) });
    if (folioId) void queryClient.invalidateQueries({ queryKey: folioKey(folioId) });
    void queryClient.invalidateQueries({ queryKey: keys.roomBoard });
    void queryClient.invalidateQueries({ queryKey: keys.currentShift });
    void queryClient.invalidateQueries({ queryKey: keys.taskCount });
    // Alerts are re-planned and the timeline/list show the new dates or room.
    void queryClient.invalidateQueries({ queryKey: ["followups"] });
    void queryClient.invalidateQueries({ queryKey: ["reservations"] });
    void queryClient.invalidateQueries({ queryKey: ["guests"] });
  };
}
