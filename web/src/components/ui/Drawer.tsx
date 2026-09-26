import { X } from "lucide-react";
import { type ReactNode, useId, useRef } from "react";

import { t } from "@/i18n/t";

import { useDialogFocus } from "./dialogFocus";

/**
 * 480 px side panel from the end (left) edge over a 24 % scrim (design rule for drawers).
 * Same keyboard contract as Modal: first field focused, Tab stays inside, Esc closes, opener refocused.
 */
export function Drawer({ title, onClose, footer, children }: { title: ReactNode; onClose: () => void; footer?: ReactNode; children: ReactNode }) {
  const panel = useRef<HTMLElement>(null);
  const titleId = useId();
  useDialogFocus(panel, onClose);
  return (
    <div className="fixed inset-0 z-40">
      <div className="scrim-24 absolute inset-0" onClick={onClose} aria-hidden />
      <aside ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} className="absolute inset-y-0 end-0 flex w-drawer flex-col rounded-s-modal bg-bg-surface shadow-elevated">
        <div className="flex items-center justify-between border-b border-border px-6 py-5">
          <h2 id={titleId} className="m-0 text-page-title">
            {title}
          </h2>
          <button
            type="button"
            data-dialog-close
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
