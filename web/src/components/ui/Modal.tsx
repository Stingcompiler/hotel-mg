import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";

import { t } from "@/i18n/t";

type Props = { title: string; onClose: () => void; width?: number; footer: ReactNode; children: ReactNode };

/** Dialog (6.5 B–D): 32 % scrim, 12 px radius, header with close, body, footer row of actions. Esc closes. */
export function Modal({ title, onClose, width = 560, footer, children }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="scrim-32 fixed inset-0 z-50 flex items-center justify-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title} style={{ width }} className="flex max-h-[90vh] flex-col rounded-modal bg-bg-surface shadow-elevated">
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
        <div className="flex flex-col gap-4 overflow-auto px-6 py-5">{children}</div>
        <div className="flex items-center gap-2 border-t border-border px-6 py-4">{footer}</div>
      </div>
    </div>
  );
}

export const buttons = {
  primary:
    "inline-flex h-11 items-center justify-center gap-2 rounded-control border-0 bg-primary px-6 font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:bg-bg-surface-2 disabled:text-text-disabled",
  secondary:
    "inline-flex h-11 items-center justify-center gap-2 rounded-control border border-border-strong bg-bg-surface px-6 font-sans text-body font-semibold text-text-primary hover:bg-bg-surface-2 disabled:text-text-disabled",
  danger:
    "inline-flex h-11 items-center justify-center gap-2 rounded-control border-0 bg-danger px-6 font-sans text-body font-semibold text-primary-text-on disabled:bg-bg-surface-2 disabled:text-text-disabled",
  ghost:
    "inline-flex h-11 items-center justify-center rounded-control border-0 bg-transparent px-4 font-sans text-body font-medium text-text-secondary hover:bg-bg-surface-2",
  dangerGhost:
    "inline-flex h-11 items-center justify-center rounded-control border-0 bg-transparent px-4 font-sans text-body font-semibold text-danger hover:bg-danger-soft disabled:text-text-disabled",
};
