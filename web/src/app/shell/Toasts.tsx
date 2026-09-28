import { useQuery } from "@tanstack/react-query";
import { Bell, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { useHotelSettings } from "@/api/queries";
import { t } from "@/i18n/t";
import { playAlert } from "@/lib/alertSound";
import { notify } from "@/lib/desktop";

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
  // Hovering the stack pauses the countdown so a toast can be read or clicked in time.
  const [paused, setPaused] = useState(false);
  // The owner's sound, or the built-in tone when none is chosen (owner request 2026-09-28).
  const sound = useHotelSettings().data?.alert_sound?.updated_at ?? null;
  const poll = useQuery({
    queryKey: ["followups", "toasts"],
    queryFn: () => data(api.GET("/api/v1/followups/toasts", { params: { query: { after: cursor.current ?? 0 } } })),
    refetchInterval: 30_000,
    gcTime: 0,
  });

  useEffect(() => {
    const batch = poll.data;
    if (!batch) return;
    if (cursor.current !== null && batch.toasts.length) {
      setShown((s) => [...batch.toasts, ...s].slice(0, 3));
      // Desktop: also a Windows notification, so it reaches staff while the window sits in the tray.
      batch.toasts.forEach((toast) => void notify(toast.title, toast.body));
      void playAlert(sound); // once per batch, however many alerts arrived together
    }
    cursor.current = batch.cursor;
  }, [poll.data]);

  useEffect(() => {
    if (!shown.length || paused) return;
    const id = window.setTimeout(() => setShown((s) => s.slice(0, -1)), SHOW_MS);
    return () => window.clearTimeout(id);
  }, [shown, paused]);

  if (!shown.length) return null;
  return (
    <div
      className="fixed bottom-6 start-6 z-40 flex w-[360px] flex-col gap-2"
      aria-live="polite"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {shown.map((toast) => (
        <div key={toast.seq} className="flex items-start gap-3 rounded-card border border-border bg-bg-surface p-3 shadow-elevated">
          <Bell className="mt-0.5 h-icon w-icon flex-none text-primary" strokeWidth={1.75} aria-hidden />
          <button
            type="button"
            onClick={() => {
              setShown((s) => s.filter((x) => x.seq !== toast.seq));
              navigate(`/followups?task=${toast.task}`);
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
            className="-me-1 -mt-1 flex h-9 w-9 flex-none items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2"
          >
            <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
