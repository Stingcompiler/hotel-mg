import { useInfiniteQuery } from "@tanstack/react-query";
import { format, startOfMonth, subDays } from "date-fns";
import { Download, Search } from "lucide-react";
import { useEffect, useState } from "react";

import type { components } from "@api/schema";

import { api, ApiError, data, download } from "@/api/client";
import { ErrorBanner, Segmented, Select } from "@/components/ui/form";
import { formatDayMonth, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { Card, HeadRow, smallButton } from "./shared";

type Category = components["schemas"]["AuditCategoryEnum"];
type Period = "today" | "week" | "month" | "all";
const CATEGORIES: Category[] = ["payment", "stay", "reversal", "override", "settings", "login", "sensitive", "other"];
const GRID = "grid grid-cols-[120px_110px_1fr_140px_130px] items-center gap-4 px-4";
// Category chips (V2 6.11 E): reversals in danger, overrides and sensitive views in warning, the rest neutral.
const CHIP: Partial<Record<Category, string>> = {
  reversal: "bg-danger-soft text-danger-text",
  override: "bg-warning-soft text-warning-text",
  sensitive: "bg-warning-soft text-warning-text",
};

function range(period: Period): { date_from?: string; date_to?: string } {
  const today = new Date();
  const iso = (d: Date) => format(d, "yyyy-MM-dd");
  if (period === "today") return { date_from: iso(today), date_to: iso(today) };
  if (period === "week") return { date_from: iso(subDays(today, 6)), date_to: iso(today) };
  if (period === "month") return { date_from: iso(startOfMonth(today)), date_to: iso(today) };
  return {};
}

/** V2 6.11 E «سجل التدقيق»: read only, searchable, by category and period; CSV export of the same filter. */
export function AuditTab() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<Category | "">("");
  const [period, setPeriod] = useState<Period>("today");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const id = window.setTimeout(() => setQ(text.trim()), 300);
    return () => window.clearTimeout(id);
  }, [text]);

  const filter = { ...range(period), ...(q ? { q } : {}), ...(category ? { category } : {}) };
  const log = useInfiniteQuery({
    queryKey: ["audit", filter],
    queryFn: ({ pageParam }) => data(api.GET("/api/v1/audit/", { params: { query: { ...filter, page: pageParam } } })),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  });
  const rows = log.data?.pages.flatMap((p) => p.results) ?? [];
  const count = log.data?.pages[0]?.count ?? 0;

  const exportCsv = async () => {
    setError(null);
    try {
      await download(`/api/v1/reports/audit_log/export?${new URLSearchParams({ ...filter, format: "csv" })}`, "audit_log.csv");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    }
  };

  return (
    <Card
      className="min-h-0 flex-1"
      title={t("settings.tabs.audit")}
      note={t("settings.audit.readOnly")}
      actions={
        <button type="button" onClick={exportCsv} className={smallButton()}>
          <Download className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("settings.audit.export")}
        </button>
      }
    >
      <div className="flex flex-none flex-wrap items-center gap-3 border-b border-border p-3">
        <label className="flex h-9 w-72 items-center gap-2 rounded-control border border-border-strong bg-bg-surface px-3">
          <Search className="h-icon-inline w-icon-inline flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("settings.audit.search")}
            aria-label={t("settings.audit.search")}
            className="h-full min-w-0 flex-1 border-0 bg-transparent p-0 font-sans text-body outline-none placeholder:text-text-disabled"
          />
        </label>
        <Segmented<Period>
          label={t("settings.audit.period")}
          value={period}
          onChange={setPeriod}
          options={(["today", "week", "month", "all"] as Period[]).map((p) => ({ value: p, label: t(`settings.audit.p_${p}`) }))}
        />
        <div className="w-44">
          <Select aria-label={t("settings.audit.allEvents")} value={category} onChange={(e) => setCategory(e.target.value as Category | "")}>
            <option value="">{t("settings.audit.allEvents")}</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`settings.audit.cat_${c}`)}
              </option>
            ))}
          </Select>
        </div>
      </div>
      {error && (
        <div className="p-3">
          <ErrorBanner>{error}</ErrorBanner>
        </div>
      )}
      <HeadRow grid={GRID} labels={["time", "event", "details", "user", "ref"].map((k) => t(`settings.audit.col_${k}`))} />
      <div className="min-h-0 flex-1 overflow-auto">
        {log.isSuccess && rows.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("settings.audit.empty")}</div>}
        {rows.map((row) => (
          <div key={row.id} className={`${GRID} min-h-11 border-b border-border py-1.5 text-table-cell`}>
            <div className="text-label font-normal text-text-secondary">
              {period === "today" ? "" : `${formatDayMonth(row.at)} · `}
              <span dir="ltr">{digits(formatTime(row.at))}</span>
            </div>
            <div>
              <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${CHIP[row.category] ?? "bg-bg-surface-2 text-text-primary"}`}>
                {row.category_label}
              </span>
            </div>
            <div className="min-w-0">
              <span className="font-medium">{row.action_label}</span>
              {row.summary && <span className="text-text-secondary"> — {row.summary}</span>}
            </div>
            <div className="text-text-secondary">{row.actor_name ?? t("settings.audit.system")}</div>
            <div dir="ltr" className="truncate text-end text-label text-text-secondary" title={`${row.entity} ${row.entity_id}`}>
              {row.entity}·{row.entity_id.slice(0, 8)}
            </div>
          </div>
        ))}
        {log.hasNextPage && (
          <div className="p-3 text-center">
            <button type="button" disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()} className={smallButton()}>
              {t("settings.audit.more")}
            </button>
          </div>
        )}
      </div>
      <div className="flex flex-none items-center justify-between border-t border-border px-4 py-3 text-label font-normal text-text-secondary">
        <span>{t("settings.audit.shown", { n: digits(String(rows.length)), total: digits(String(count)) })}</span>
        <span>{t("settings.audit.chainNote")}</span>
      </div>
    </Card>
  );
}
