import type { ReactNode } from "react";

import { digits } from "@/i18n/digits";

export type TabItem<T extends string> = { key: T; label: string; count?: number };

/**
 * The one tab strip (stay detail, guest profile): 48 px row, 2 px underline on the active tab, optional count.
 * Arrow keys move between tabs (WAI-ARIA tabs pattern); the panel's contents are the caller's.
 */
export function Tabs<T extends string>({ items, value, onChange, end, size = "md" }: { items: TabItem<T>[]; value: T; onChange: (key: T) => void; end?: ReactNode; size?: "md" | "sm" }) {
  const h = size === "sm" ? "h-11" : "h-12";
  const move = (from: number, delta: number) => {
    const next = items[(from + delta + items.length) % items.length];
    onChange(next.key);
    document.getElementById(`tab-${String(next.key)}`)?.focus();
  };
  return (
    <div role="tablist" className={`flex ${h} flex-none items-center gap-1 border-b border-border px-4`}>
      {items.map((tb, i) => (
        <button
          key={tb.key}
          id={`tab-${String(tb.key)}`}
          type="button"
          role="tab"
          aria-selected={value === tb.key}
          tabIndex={value === tb.key ? 0 : -1}
          onClick={() => onChange(tb.key)}
          onKeyDown={(e) => {
            // RTL: the "next" tab sits to the left.
            if (e.key === "ArrowLeft") move(i, 1);
            else if (e.key === "ArrowRight") move(i, -1);
          }}
          className={`-mb-px inline-flex ${h} items-center gap-1.5 border-0 border-b-2 bg-transparent px-4 font-sans text-body ${
            value === tb.key ? "border-primary font-semibold text-primary" : "border-transparent font-medium text-text-secondary hover:text-text-primary"
          }`}
        >
          {tb.label}
          {tb.count ? <span className="text-label font-normal text-text-secondary">{digits(String(tb.count))}</span> : null}
        </button>
      ))}
      {end && (
        <>
          <div className="flex-1" />
          {end}
        </>
      )}
    </div>
  );
}
