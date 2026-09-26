import { Check, Info, X } from "lucide-react";
import { useEffect, useState } from "react";

import { t } from "@/i18n/t";
import { dismissNotice, useNotices } from "@/lib/notices";

const SHOW_MS = 4_000;

/** Save confirmations (`lib/notices`): bottom-start stack above the follow-up toasts; a hover pauses the timer. */
export function Notices() {
  const notices = useNotices();
  const [paused, setPaused] = useState(false);
  const oldest = notices[0];
  useEffect(() => {
    if (!oldest || paused) return;
    const id = window.setTimeout(() => dismissNotice(oldest.id), SHOW_MS);
    return () => window.clearTimeout(id);
  }, [oldest, paused]);

  if (!notices.length) return null;
  return (
    <div
      className="fixed bottom-6 start-6 z-40 flex w-[360px] flex-col gap-2"
      role="status"
      aria-live="polite"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {notices.map((n) => (
        <div
          key={n.id}
          className={`flex items-center gap-3 rounded-card border p-3 shadow-elevated ${
            n.tone === "success" ? "border-success bg-success-soft text-success-text" : "border-border bg-bg-surface text-text-primary"
          }`}
        >
          {n.tone === "success" ? (
            <Check className="h-icon w-icon flex-none" strokeWidth={2} aria-hidden />
          ) : (
            <Info className="h-icon w-icon flex-none text-primary" strokeWidth={1.75} aria-hidden />
          )}
          <div className="min-w-0 flex-1 text-body font-medium">{n.text}</div>
          <button
            type="button"
            aria-label={t("common.close")}
            onClick={() => dismissNotice(n.id)}
            className="-me-1 flex h-9 w-9 flex-none items-center justify-center rounded-control border-0 bg-transparent text-current hover:bg-bg-surface"
          >
            <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
