import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import { t } from "@/i18n/t";

/** Arabic text of a failed save: the field messages of a validation error, else the error's own message. */
export function apiErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return t("errors.error");
  const fields = error.extra.errors;
  if (fields && typeof fields === "object") {
    const messages = Object.values(fields as Record<string, unknown>).flatMap((v) => (Array.isArray(v) ? v : [v]));
    const text = messages.filter((m) => typeof m === "string").join(" · ");
    if (text) return text;
  }
  return error.message;
}

/** Settings card (6.11): 48 px header with title, optional note and actions, then the body. */
export function Card({ title, note, actions, children, className = "" }: { title: string; note?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`flex flex-col overflow-hidden rounded-card border border-border bg-bg-surface ${className}`}>
      <div className="flex min-h-12 flex-none items-center gap-3 border-b border-border px-4 py-2">
        <h2 className="m-0 text-section-title">{title}</h2>
        {note && <span className="text-body text-text-secondary">{note}</span>}
        <div className="flex-1" />
        {actions}
      </div>
      {children}
    </section>
  );
}

/** Table header row on surface-2, 12/500 secondary. */
export function HeadRow({ grid, labels }: { grid: string; labels: string[] }) {
  return (
    <div className={`${grid} h-10 flex-none border-b border-border bg-bg-surface-2 text-label text-text-secondary`}>
      {labels.map((label, i) => (
        <div key={i}>{label}</div>
      ))}
    </div>
  );
}

/** Footnote under a settings table. */
export function Footnote({ children }: { children: ReactNode }) {
  return <div className="border-t border-border px-4 py-3 text-label font-normal text-text-secondary">{children}</div>;
}

export const linkButton =
  "border-0 bg-transparent p-0 font-sans text-body font-medium text-primary hover:text-primary-hover disabled:text-text-disabled";
export const smallButton = (kind: "primary" | "secondary" = "secondary") =>
  kind === "primary"
    ? "inline-flex h-9 items-center justify-center gap-2 rounded-control border-0 bg-primary px-4 font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:bg-bg-surface-2 disabled:text-text-disabled"
    : "inline-flex h-9 items-center justify-center gap-2 rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body font-medium text-text-primary hover:bg-bg-surface-2 disabled:text-text-disabled";
