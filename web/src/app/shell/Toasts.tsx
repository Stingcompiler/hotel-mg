import { useQuery } from "@tanstack/react-query";
import { Bell, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { t } from "@/i18n/t";

type Toast = components["schemas"]["Toast"];
const SHOW_MS = 10_000;

/**
 * Follow-up toasts (spec §6.6 «إشعار»): polls `followups/toasts` every 30 s. The first answer only sets the cursor,
 * so opening the app does not replay old notifications. A toast opens the follow-ups screen.
 */
export function Toasts() {
  const navigate = useNavigate();
  const cursor = useRef<number | null>(null);
  const [shown, setShown] = useState<Toast[]>([]);
  const poll = useQuery({
    queryKey: ["followups", "toasts"],
    queryFn: () => data(api.GET("/api/v1/followups/toasts", { params: { query: { after: cursor.current ?? 0 } } })),
    refetchInterval: 30_000,
    gcTime: 0,
  });

  useEffect(() => {
    const batch = poll.data;
    if (!batch) return;
    if (cursor.current !== null && batch.toasts.length) setShown((s) => [...batch.toasts, ...s].slice(0, 3));
    cursor.current = batch.cursor;
  }, [poll.data]);

  useEffect(() => {
    if (!shown.length) return;
    const id = window.setTimeout(() => setShown((s) => s.slice(0, -1)), SHOW_MS);
    return () => window.clearTimeout(id);
  }, [shown]);

  if (!shown.length) return null;
  return (
    <div className="fixed bottom-6 start-6 z-40 flex w-[360px] flex-col gap-2" aria-live="polite">
      {shown.map((toast) => (
        <div key={toast.seq} className="flex items-start gap-3 rounded-card border border-border bg-bg-surface p-3 shadow-elevated">
          <Bell className="mt-0.5 h-icon w-icon flex-none text-primary" strokeWidth={1.75} aria-hidden />
          <button
            type="button"
            onClick={() => {
              setShown((s) => s.filter((x) => x.seq !== toast.seq));
              navigate("/followups");
            }}
            className="min-w-0 flex-1 border-0 bg-transparent p-0 text-start font-sans"
          >
            <div className="text-body font-semibold text-text-primary">{toast.title}</div>
            <div className="text-label font-normal text-text-secondary">{toast.body}</div>
          </button>
          <button
            type="button"
            aria-label={t("common.close")}
            onClick={() => setShown((s) => s.filter((x) => x.seq !== toast.seq))}
            className="flex h-6 w-6 flex-none items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2"
          >
            <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
