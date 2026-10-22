import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Sparkline } from "./Sparkline";

export type StatDelta = {
  /** Already formatted, e.g. «+٤٫٢٪». */
  text: string;
  trend: "up" | "down";
  /** Whether this direction is good news (revenue up) or bad (debts up). Defaults to up = good. */
  good?: boolean;
};

type Props = {
  icon: LucideIcon;
  value: ReactNode;
  unit?: ReactNode;
  label: string;
  /** One quiet line under the label: the context the old tiles carried («19 من 30 غرفة»). */
  hint?: ReactNode;
  /** Only from a comparison the API actually returns. */
  delta?: StatDelta;
  /** Only from a real series, oldest first. */
  series?: number[];
  /** «danger»: something needs action (red); «warning»: worth a look (amber). */
  tone?: "default" | "warning" | "danger";
  onClick?: () => void;
  active?: boolean;
};

/**
 * «Soft Minimal Card» for a statistic (owner brief 2026-10-18, decision 232): the icon in a tinted square at the start,
 * the change at the end, the number, its label, and a bare trend line when there is a series. Under 1600 px the card
 * tightens (smaller radius, padding, icon and number) so four fit a reception laptop. Clickable when it filters.
 */
const TONE = {
  default: { icon: "bg-primary-soft text-primary", value: "text-text-primary" },
  warning: { icon: "bg-warning-soft text-warning", value: "text-warning-text" },
  danger: { icon: "bg-danger-soft text-danger", value: "text-danger" },
};

export function StatCard({ icon: Icon, value, unit, label, hint, delta, series, tone = "default", onClick, active = false }: Props) {
  const box = `surface-card flex min-w-0 flex-col gap-[18px] p-6 text-start font-sans text-text-primary max-[1599px]:gap-3 max-[1599px]:p-4 ${
    active ? "border-primary" : ""
  }`;
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span
          className={`flex h-[60px] w-[60px] flex-none items-center justify-center rounded-icon max-[1599px]:h-11 max-[1599px]:w-11 max-[1599px]:rounded-[14px] ${
            TONE[tone].icon
          }`}
        >
          <Icon className="h-[26px] w-[26px] max-[1599px]:h-[22px] max-[1599px]:w-[22px]" strokeWidth={1.75} aria-hidden />
        </span>
        {delta && (
          <span
            dir="ltr"
            className={`inline-flex items-center gap-0.5 whitespace-nowrap rounded-full px-2 py-1 text-label font-bold ${
              (delta.good ?? delta.trend === "up") ? "bg-primary-soft text-primary-hover" : "bg-danger-soft text-danger"
            }`}
          >
            {delta.trend === "up" ? <ArrowUpRight className="h-3 w-3" strokeWidth={2.5} aria-hidden /> : <ArrowDownRight className="h-3 w-3" strokeWidth={2.5} aria-hidden />}
            {delta.text}
          </span>
        )}
      </div>
      <div className="min-w-0">
        <div className={`flex flex-wrap items-baseline gap-x-1.5 text-[34px] font-bold leading-[1.1] max-[1599px]:text-[26px] ${TONE[tone].value}`}>
          <span className="min-w-0">{value}</span>
          {unit && <span className="text-body font-semibold text-text-secondary max-[1599px]:text-label">{unit}</span>}
        </div>
        <div className="mt-1 truncate text-body font-normal text-text-secondary max-[1599px]:text-label">{label}</div>
        {hint && <div className="mt-0.5 text-label font-normal text-text-secondary">{hint}</div>}
      </div>
      {series && series.length > 1 && (
        <div className="-mx-1 mt-auto">
          <Sparkline values={series} />
        </div>
      )}
    </>
  );
  return onClick ? (
    <button type="button" onClick={onClick} aria-pressed={active} className={`${box} w-full transition-colors duration-150 hover:bg-bg-page`}>
      {body}
    </button>
  ) : (
    <div className={box}>{body}</div>
  );
}

/** Loading placeholder with the card's own surface, so the row does not jump. */
export function StatCardSkeleton() {
  return (
    <div className="surface-card flex h-[150px] flex-col gap-4 p-6 max-[1599px]:h-[104px] max-[1599px]:p-4" aria-hidden>
      <div className="skeleton h-11 w-11 rounded-icon" />
      <div className="skeleton h-5 w-24 rounded" />
    </div>
  );
}
