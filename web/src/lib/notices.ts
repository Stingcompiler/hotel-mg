import { useSyncExternalStore } from "react";

export type Notice = { id: number; text: string; tone: "success" | "info" };

/**
 * Short confirmations after a save («تم تسجيل الدفعة»…), shown bottom-start like the follow-up toasts and gone
 * after a few seconds. A tiny store so any screen can post one without a provider.
 */
let notices: Notice[] = [];
let nextId = 1;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function notice(text: string, tone: Notice["tone"] = "success"): void {
  notices = [...notices, { id: nextId++, text, tone }].slice(-3);
  emit();
}

export function dismissNotice(id: number): void {
  notices = notices.filter((n) => n.id !== id);
  emit();
}

export function useNotices(): Notice[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => notices,
  );
}
