import { useSyncExternalStore } from "react";

/**
 * Light / dark / follow Windows, per PC (owner request 2026-10-22, decision 234). The choice lives in this PC's
 * browser storage; the resolved theme is set as <html data-theme>, and tokens.css re-colours from there.
 */
export type ThemePref = "light" | "dark" | "system";

const KEY = "skytowers.theme";
const listeners = new Set<() => void>();
let forcedLight = 0;

function stored(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

let pref: ThemePref = typeof window === "undefined" ? "system" : stored();

function systemDark(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

/** The theme on screen: the choice, or Windows' own when the choice is «حسب ويندوز». Printing is always light. */
export function resolvedTheme(): "light" | "dark" {
  if (forcedLight > 0) return "light";
  return pref === "system" ? (systemDark() ? "dark" : "light") : pref;
}

function apply(): void {
  document.documentElement.dataset.theme = resolvedTheme();
  listeners.forEach((l) => l());
}

export function setThemePref(next: ThemePref): void {
  pref = next;
  try {
    if (next === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, next);
  } catch {
    // storage unavailable: the choice holds for this session only
  }
  apply();
}

/** Called once before the first render (main.tsx), so the app never flashes the other theme. */
export function initTheme(): void {
  apply();
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => pref === "system" && apply());
}

/** Paper is white: print pages hold the light theme while they are open (receipts, invoices, statements). */
export function holdLightTheme(): () => void {
  forcedLight += 1;
  apply();
  return () => {
    forcedLight -= 1;
    apply();
  };
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The current choice, re-rendering when it changes. */
export function useThemePref(): ThemePref {
  return useSyncExternalStore(subscribe, () => pref, () => pref);
}
