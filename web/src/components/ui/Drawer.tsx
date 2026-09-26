import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";

import { t } from "@/i18n/t";

/** 480 px side panel from the end (left) edge over a 24 % scrim (design rule for drawers). Esc closes. */
export function Drawer({ title, onClose, footer, children }: { title: ReactNode; onClose: () => void; footer?: ReactNode; children: ReactNode }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40">
      <div className="scrim-24 absolute inset-0" onClick={onClose} aria-hidden />
      <aside role="dialog" aria-modal="true" className="absolute inset-y-0 end-0 flex w-drawer flex-col rounded-s-modal bg-bg-surface shadow-elevated">
        <div className="flex items-center justify-between border-b border-border px-6 py-5">
          <h2 className="m-0 text-page-title">{title}</h2>
          <button
            ref={closeRef}
            type="button"
            aria-label={t("common.close")}
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2"
          >
            <X className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
        <div className="flex flex-1 flex-col gap-4 overflow-auto px-6 py-5">{children}</div>
        {footer && <div className="flex items-center gap-2 border-t border-border px-6 py-4">{footer}</div>}
      </aside>
    </div>
  );
}
