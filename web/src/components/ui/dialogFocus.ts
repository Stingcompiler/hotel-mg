import { type RefObject, useEffect, useRef, useState } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(panel: HTMLElement): HTMLElement[] {
  // `[hidden]` subtrees are skipped; visually hidden (`sr-only`) controls stay, as the browser's own Tab order keeps them.
  return [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.closest("[hidden]"));
}

/**
 * Keyboard contract shared by Modal and Drawer: focus starts on the first field (an `autoFocus` control, else the
 * first control that is not the close button), Tab cycles inside the panel, Esc closes, and the element that opened
 * the dialog gets focus back when it closes. The opener is captured once, on mount, so a parent re-render (a new
 * `onClose` identity) neither moves focus nor forgets where it came from.
 */
export function useDialogFocus(panel: RefObject<HTMLElement | null>, onClose: () => void): void {
  const close = useRef(onClose);
  close.current = onClose;
  // Read during the first render: by the time effects run, React has already moved focus to an `autoFocus` field.
  const [opener] = useState(() => document.activeElement as HTMLElement | null);

  useEffect(() => {
    const el = panel.current;
    if (el) {
      const all = focusables(el);
      const first = el.querySelector<HTMLElement>("[autofocus]") ?? all.find((x) => !x.hasAttribute("data-dialog-close")) ?? all[0];
      first?.focus();
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close.current();
        return;
      }
      if (e.key !== "Tab" || !panel.current) return;
      const all = focusables(panel.current);
      if (!all.length) return;
      const first = all[0];
      const last = all[all.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || !panel.current.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !panel.current.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener && document.contains(opener)) opener.focus();
    };
    // Mount/unmount only: the opener and the first field are decided when the dialog appears.
  }, []);
}
