import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Download, FileText, Printer } from "lucide-react";
import { useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";

import type { components } from "@api/schema";

import { api, ApiError, data, download } from "@/api/client";
import { ErrorBanner, Segmented, Select, TextInput } from "@/components/ui/form";
import { buttons } from "@/components/ui/Modal";
import { openPrint } from "@/features/print/PrintPage";
import { useRoomTypes } from "@/features/reservations/StaySection";
import { formatDayMonth, formatRange, formatTime, formatWhen } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Report = components["schemas"]["Report"];
type Column = Report["columns"][number];
type Tile = { label: string; value: number | string; type?: string; hint?: string; tone?: "danger" };

/** Report-specific controls (the framework accepts them as query parameters). */
const CONTROLS: Record<string, "debts" | "when" | "days" | "none" | "period"> = {
  debts: "debts",
  arrivals_departures: "when",
  ending_soon: "days",
  current_guests: "none",
};

/** Filters a report accepts (server: room_type / method / expense_category, contract 1.1). */
const FILTERS: Record<string, ("room_type" | "method" | "expense_category")[]> = {
  revenue: ["room_type", "method"],
  debts: ["room_type"],
  current_guests: ["room_type"],
  arrivals_departures: ["room_type"],
  expenses: ["method", "expense_category"],
};
const METHODS = ["cash", "bankak", "transfer"] as const;
const CATEGORIES = ["supplies", "purchases", "maintenance", "bills", "salaries", "other"] as const;

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function periodParams(period: string, custom: { from: string; to: string }): Record<string, string> {
  const now = new Date();
  if (period === "today") return { date_from: iso(now), date_to: iso(now) };
  if (period === "week") {
    // The week starts on Saturday (Sudan's working week).
    const back = (now.getDay() + 1) % 7;
    return { date_from: iso(new Date(now.getTime() - back * 86_400_000)), date_to: iso(now) };
  }
  if (period === "lastMonth") return { date_from: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)), date_to: iso(new Date(now.getFullYear(), now.getMonth(), 0)) };
  if (period === "7") return { date_from: iso(new Date(now.getTime() - 6 * 86_400_000)), date_to: iso(now) };
  if (period === "30") return { date_from: iso(new Date(now.getTime() - 29 * 86_400_000)), date_to: iso(now) };
  if (period === "custom" && custom.from && custom.to) return { date_from: custom.from, date_to: custom.to };
  return {}; // server default: this month (or the report's own default)
}

export function formatCell(value: unknown, type: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "money" && typeof value === "number") return formatMoney(value);
  if (type === "percent" && typeof value === "number") return `${digits(String(value))}٪`;
  if (type === "int" && typeof value === "number") return digits(String(value));
  if (type === "date" && typeof value === "string") return formatDayMonth(value);
  if (type === "datetime" && typeof value === "string") return `${formatDayMonth(value)} · ${formatTime(value)}`;
  return digits(String(value));
}

const numeric = (c: Column) => c.type === "money" || c.type === "int" || c.type === "percent";

/** 6.10 Reports: index with badges on the start side, the open report with its tiles, table, totals and exports. */
export function ReportsPage() {
  const { name } = useParams();
  const navigate = useNavigate();
  const index = useQuery({ queryKey: ["reports", "index"], queryFn: () => data(api.GET("/api/v1/reports/")) });
  const current = name ?? index.data?.[0]?.name;
  const [debts, setDebts] = useState<"due" | "late" | "all">("due");
  const [when, setWhen] = useState<"today" | "tomorrow" | "week">("today");
  const [days, setDays] = useState("3");
  const [period, setPeriod] = useState("month");
  const [custom, setCustom] = useState({ from: "", to: "" });
  const [filters, setFilters] = useState({ room_type: "", method: "", expense_category: "" });
  const [error, setError] = useState<string | null>(null);
  const roomTypes = useRoomTypes().data ?? [];

  const kind = current ? CONTROLS[current] ?? "period" : "none";
  const accepted = current ? FILTERS[current] ?? [] : [];
  const query: Record<string, string> = {
    ...(kind === "debts" ? { status: debts } : kind === "when" ? { when } : kind === "days" ? { days } : kind === "period" ? periodParams(period, custom) : {}),
    ...Object.fromEntries(accepted.filter((k) => filters[k]).map((k) => [k, filters[k]])),
  };
  const report = useQuery({
    queryKey: ["reports", current, query],
    queryFn: () => data(api.GET("/api/v1/reports/{name}", { params: { path: { name: current! }, query: query as never } })),
    enabled: !!current,
  });
  const r = report.data;
  const title = index.data?.find((x) => x.name === current)?.title ?? "";

  const [pdfBusy, setPdfBusy] = useState(false);
  const exportAs = async (format: "xlsx" | "pdf") => {
    if (format === "pdf") setPdfBusy(true);
    setError(null);
    const qs = new URLSearchParams({ ...query, format });
    try {
      await download(`/api/v1/reports/${current}/export?${qs}`, `${current}.${format}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setPdfBusy(false);
    }
  };

  const meta = r?.meta as
    | {
        title?: string;
        as_of?: string;
        date_from?: string | null;
        date_to?: string | null;
        formula?: string;
        note?: string;
        tiles?: Tile[];
        totals?: Record<string, number>;
        filters?: { key: string; label: string; value: string }[];
      }
    | undefined;

  return (
    <div className="grid h-full min-h-[620px] grid-cols-[280px_1fr] grid-rows-[auto_1fr] gap-4 p-6 max-[1599px]:grid-cols-[220px_1fr] max-[1599px]:gap-3 max-[1399px]:grid-cols-[210px_1fr]">
      <div className="col-span-2 flex flex-wrap items-center gap-3">
        <h1 className="m-0 whitespace-nowrap text-page-title">{t("reports.title")}</h1>
        {title && (
          <>
            <span className="text-text-disabled">/</span>
            <span className="whitespace-nowrap text-section-title">{title}</span>
          </>
        )}
        <div className="flex-1" />
        {kind === "debts" && (
          <Segmented
            label={title}
            value={debts}
            onChange={setDebts}
            options={[
              { value: "due", label: t("reports.debtsDue") },
              { value: "late", label: t("reports.debtsLate") },
              { value: "all", label: t("reports.all") },
            ]}
          />
        )}
        {kind === "when" && (
          <Segmented
            label={title}
            value={when}
            onChange={setWhen}
            options={[
              { value: "today", label: t("reports.whenToday") },
              { value: "tomorrow", label: t("reports.whenTomorrow") },
              { value: "week", label: t("reports.whenWeek") },
            ]}
          />
        )}
        {kind === "days" && (
          <Segmented
            label={title}
            value={days}
            onChange={setDays}
            options={[
              { value: "3", label: t("reports.days3") },
              { value: "7", label: t("reports.days7") },
              { value: "14", label: t("reports.days14") },
            ]}
          />
        )}
        {kind === "period" && (
          <>
            <div className="w-44 shrink-0">
              <Select aria-label={t("reports.periodMonth")} value={period} onChange={(e) => setPeriod(e.target.value)}>
                <option value="today">{t("reports.periodToday")}</option>
                <option value="week">{t("reports.periodWeek")}</option>
                <option value="month">{t("reports.periodMonth")}</option>
                <option value="lastMonth">{t("reports.periodLastMonth")}</option>
                <option value="7">{t("reports.period7")}</option>
                <option value="30">{t("reports.period30")}</option>
                <option value="custom">{t("reports.periodCustom")}</option>
              </Select>
            </div>
            {period === "custom" && (
              <>
                <TextInput type="date" aria-label={t("reports.from")} value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} className="w-40" />
                <TextInput type="date" aria-label={t("reports.to")} value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} className="w-40" />
              </>
            )}
          </>
        )}
        {accepted.includes("room_type") && (
          <div className="w-40 shrink-0">
            <Select aria-label={t("reports.allRoomTypes")} value={filters.room_type} onChange={(e) => setFilters({ ...filters, room_type: e.target.value })}>
              <option value="">{t("reports.allRoomTypes")}</option>
              {roomTypes.map((rt) => (
                <option key={rt.id} value={rt.id}>
                  {rt.name}
                </option>
              ))}
            </Select>
          </div>
        )}
        {accepted.includes("method") && (
          <div className="w-36 shrink-0">
            <Select aria-label={t("reports.allMethods")} value={filters.method} onChange={(e) => setFilters({ ...filters, method: e.target.value })}>
              <option value="">{t("reports.allMethods")}</option>
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {t(`payMethod.${m}`)}
                </option>
              ))}
            </Select>
          </div>
        )}
        {accepted.includes("expense_category") && (
          <div className="w-36 shrink-0">
            <Select aria-label={t("reports.allCategories")} value={filters.expense_category} onChange={(e) => setFilters({ ...filters, expense_category: e.target.value })}>
              <option value="">{t("reports.allCategories")}</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`expenseCategory.${c}`)}
                </option>
              ))}
            </Select>
          </div>
        )}
        <button type="button" disabled={!r} onClick={() => openPrint("report", current!, query)} className={`${buttons.secondary} h-9 px-4`}>
          <Printer className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
          {t("print.printA4")}
        </button>
        <button type="button" disabled={!r} onClick={() => void exportAs("xlsx")} className={`${buttons.secondary} h-9 px-4`}>
          <Download className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
          {t("reports.exportExcel")}
        </button>
        {/* PDF like the printed page; Excel for the accountant. CSV left the screen: Excel covers it (owner, 2026-10-02). */}
        <button type="button" disabled={!r || pdfBusy} onClick={() => void exportAs("pdf")} className={`${buttons.secondary} h-9 px-4`}>
          <FileText className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
          {pdfBusy ? t("reports.pdfBusy") : t("reports.exportPdf")}
        </button>
      </div>

      <nav className="flex flex-col gap-0.5 self-start rounded-card border border-border bg-bg-surface p-2">
        {index.data?.map((item) => (
          <NavLink
            key={item.name}
            to={`/reports/${item.name}`}
            className={() =>
              `flex h-10 items-center justify-between gap-2 rounded-control px-3 text-body ${
                item.name === current ? "bg-primary-soft font-semibold text-primary hover:text-primary" : "text-text-primary hover:bg-bg-surface-2 hover:text-text-primary"
              }`
            }
            onClick={(e) => {
              e.preventDefault();
              navigate(`/reports/${item.name}`);
            }}
          >
            <span className="min-w-0 truncate" title={item.title}>
              {item.title}
            </span>
            {item.badge ? <span className={`flex-none text-label font-semibold ${item.badge > 0 ? "text-danger" : "text-text-secondary"}`}>{digits(String(item.badge))}</span> : null}
          </NavLink>
        ))}
      </nav>

      <div className="flex min-h-0 min-w-0 flex-col gap-4 max-[1599px]:gap-3">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        {report.isError && <ErrorBanner>{(report.error as Error).message}</ErrorBanner>}
        {!r ? (
          <div className="skeleton h-64 rounded-card" />
        ) : (
          <>
            {!!meta?.tiles?.length && (
              <div className="grid gap-4 max-[1599px]:gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(meta.tiles.length, 4)}, 1fr)` }}>
                {meta.tiles.slice(0, 4).map((tile) => (
                  <div key={tile.label} className="rounded-card border border-border bg-bg-surface p-4 max-[1599px]:px-4 max-[1599px]:py-3">
                    <div className="text-label text-text-secondary">{tile.label}</div>
                    <div className={`mt-1 text-headline-number ${tile.tone === "danger" && typeof tile.value === "number" && tile.value !== 0 ? "text-danger" : ""}`}>
                      {formatCell(tile.value, tile.type ?? "text")}
                      {tile.type === "money" && <span className="text-[16px] font-semibold text-text-secondary"> {t("money.currency")}</span>}
                    </div>
                    {tile.hint && <div className="mt-1 text-label font-normal text-text-secondary">{digits(tile.hint)}</div>}
                  </div>
                ))}
              </div>
            )}
            <ReportTable report={r} totals={meta?.totals ?? {}} />
            <div className="flex flex-wrap items-center justify-between gap-2 text-label font-normal text-text-secondary">
              <span>
                {meta?.date_from && meta.date_to && t("reports.period", { range: formatRange(meta.date_from, meta.date_to) })}
                {!!meta?.filters?.length && ` · ${t("reports.filters", { list: meta.filters.map((f) => `${f.label}: ${f.value}`).join(" · ") })}`}
                {meta?.as_of && ` · ${t("reports.asOf", { time: formatWhen(meta.as_of) })}`}
              </span>
              <span>{meta?.formula || meta?.note}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined || a === "") return 1;
  if (b === null || b === undefined || b === "") return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "ar", { numeric: true });
}

function ReportTable({ report, totals }: { report: Report; totals: Record<string, number> }) {
  const cols = report.columns;
  const template = cols.map((c) => (c.type === "text" ? "minmax(120px,1.4fr)" : "minmax(100px,1fr)")).join(" ");
  const hasTotals = Object.keys(totals).length > 0;
  // Click a header to sort (twice: descending; a third time: the server's order). Not carried to print or export.
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const cell = (row: unknown, key: string) => (row as Record<string, unknown>)[key];
  const rows = sort ? [...report.rows].sort((x, y) => sort.dir * compare(cell(x, sort.key), cell(y, sort.key))) : report.rows;
  const cycle = (key: string) => setSort((s) => (s?.key !== key ? { key, dir: 1 } : s.dir === 1 ? { key, dir: -1 } : null));
  return (
    // One scroll box for header, rows and totals: a report wider than the window scrolls sideways instead of losing
    // its last columns (review 2026-09-28, small screens).
    <section className="min-h-0 flex-1 overflow-auto rounded-card border border-border bg-bg-surface">
      <div className="w-max min-w-full">
        <div className="sticky top-0 z-10 grid h-10 items-center gap-3 bg-bg-surface-2 px-4 text-label text-text-secondary" style={{ gridTemplateColumns: template }}>
          {cols.map((c) => (
            <button
              key={c.key}
              type="button"
              aria-sort={sort?.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
              title={t("reports.sortBy", { col: c.label })}
              onClick={() => cycle(c.key)}
              className={`flex h-10 items-center gap-1 border-0 bg-transparent p-0 font-sans text-label ${numeric(c) ? "justify-end text-end" : "text-start"} ${
                sort?.key === c.key ? "text-primary" : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {c.label}
              {sort?.key === c.key && (sort.dir === 1 ? <ArrowUp className="h-3.5 w-3.5" strokeWidth={2} aria-hidden /> : <ArrowDown className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />)}
            </button>
          ))}
        </div>
        <div>
          {report.rows.length === 0 && <div className="p-8 text-center text-body text-text-secondary">{t("reports.empty")}</div>}
          {rows.map((row, i) => (
            <div key={i} className="grid h-10 items-center gap-3 border-b border-border px-4 text-table-cell hover:bg-bg-page" style={{ gridTemplateColumns: template }}>
              {cols.map((c) => (
                <div key={c.key} className={`truncate ${numeric(c) ? "text-end font-semibold" : ""}`}>
                  {formatCell((row as Record<string, unknown>)[c.key], c.type)}
                </div>
              ))}
            </div>
          ))}
        </div>
        {hasTotals && (
          <div className="sticky bottom-0 grid h-11 items-center gap-3 border-t border-border bg-bg-surface px-4 text-body font-semibold" style={{ gridTemplateColumns: template }}>
            {cols.map((c, i) => (
              <div key={c.key} className={`whitespace-nowrap ${numeric(c) ? "text-end" : ""}`}>
                {i === 0 ? `${t("reports.total")} · ${t("reports.rows", { n: digits(String(report.rows.length)) })}` : c.key in totals ? formatCell(totals[c.key], c.type) : ""}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
