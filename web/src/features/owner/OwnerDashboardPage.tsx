import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { NewPcCard } from "@/features/backup/AdoptModal";
import { Segmented } from "@/components/ui/form";
import { stateColor } from "@/design/state";
import { days, duration } from "@/i18n/counts";
import { formatDayMonth } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney, MINOR } from "@/i18n/money";
import { t } from "@/i18n/t";

type Dashboard = components["schemas"]["OwnerDashboard"];
type Period = "month" | "previous" | "90days";
type Attention = Dashboard["attention"][number];
// Imported data older than this is flagged «الأرقام أدناه قديمة» (artboard 6.12 B).
const STALE_HOURS = 72;

const pct = (n: number) => `${digits(String(n))}٪`;

/** 6.12 Owner dashboard: read only; KPIs, occupancy line, weekly revenue vs collected, attention list, staff response. */
export function OwnerDashboardPage() {
  const [period, setPeriod] = useState<Period>("month");
  const navigate = useNavigate();
  const dash = useQuery({
    queryKey: ["reports", "owner-dashboard", period],
    queryFn: () => data(api.GET("/api/v1/reports/owner-dashboard", { params: { query: { period } } })),
    // The owner PC changes only on an import: no reload each time the window gets focus (review 2026-09-29, F-12).
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const d = dash.data;

  return (
    <div className="flex flex-col gap-4 p-6 max-[1599px]:gap-3">
      <NewPcCard onSetup={() => navigate("/settings/roomTypes")} />
      <DeviceNotices />
      <div className="flex h-9 items-center gap-3">
        <h1 className="m-0 text-page-title">{t("ownerDash.title")}</h1>
        {d && (
          <span className="text-body text-text-secondary">
            {t("ownerDash.subtitle", { period: d.period.label, rooms: digits(String(d.rooms)) })}
          </span>
        )}
        <div className="flex-1" />
        <Segmented<Period>
          label={t("ownerDash.period")}
          value={period}
          onChange={setPeriod}
          options={(["month", "previous", "90days"] as Period[]).map((p) => ({ value: p, label: t(`ownerDash.p_${p}`) }))}
        />
      </div>

      {!d ? (
        <Skeleton />
      ) : (
        <>
          <Kpis d={d} />
          {/* minmax(0, …): a long week list (90 days = 13 weeks) must not widen its column and squeeze the other. */}
          <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-4 max-[1599px]:gap-3">
            <OccupancyChart d={d} />
            <WeeksChart weeks={d.weeks} />
          </div>
          <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] items-start gap-4 max-[1599px]:gap-3">
            <AttentionList rows={d.attention} />
            <StaffTable rows={d.staff} />
          </div>
        </>
      )}
    </div>
  );
}

/** Owner-PC notices under the banner: data not imported for days, or a newer backup waiting on Drive. */
function DeviceNotices() {
  const status = useQuery({ queryKey: ["owner", "status"], queryFn: () => data(api.GET("/api/v1/owner/status")), retry: false }).data;
  const candidates = useQuery({
    queryKey: ["owner", "import", "candidates"],
    queryFn: () => data(api.GET("/api/v1/owner/import/candidates")),
    retry: false,
    staleTime: 5 * 60_000,
  }).data;
  const newest = candidates?.filter((c) => c.state === "new").sort((a, b) => b.seq - a.seq)[0];
  const stale = status && status.hours_old !== null && status.hours_old >= STALE_HOURS;
  if (!newest && !stale) return null;
  return (
    <div className="flex flex-col gap-2">
      {newest && (
        <Notice tone="info">
          {t("ownerDash.newerOnDrive", { seq: digits(String(newest.seq)) })}
          <Link to="/backup" className="ms-2 font-semibold text-info-text underline">
            {t("ownerDash.goImport")}
          </Link>
        </Notice>
      )}
      {stale && (
        <Notice tone="warning">
          {t("ownerDash.stale", { age: days(Math.floor(status.hours_old! / 24)) })}
          <Link to="/backup" className="ms-2 font-semibold text-warning-text underline">
            {t("ownerDash.importNow")}
          </Link>
        </Notice>
      )}
    </div>
  );
}

function Notice({ tone, children }: { tone: "info" | "warning"; children: React.ReactNode }) {
  return (
    <div
      role="status"
      className={`flex min-h-11 items-center gap-3 rounded-card px-4 py-2 text-body font-medium ${
        tone === "info" ? "bg-info-soft text-info-text" : "bg-warning-soft text-warning-text"
      }`}
    >
      <TriangleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
      <span>{children}</span>
    </div>
  );
}

function Kpis({ d }: { d: Dashboard }) {
  const k = d.kpis;
  const money = (v: number) => formatMoney(v);
  const tiles: { label: string; value: string; unit?: string; hint: string; danger?: boolean }[] = [
    {
      label: t("ownerDash.kOccupancy"),
      value: digits(String(k.occupancy_today.value)),
      unit: "٪",
      hint: t("ownerDash.kOccupancyHint", {
        occ: digits(String(k.occupancy_today.occupied)),
        rooms: digits(String(k.occupancy_today.rooms)),
        avg: pct(k.occupancy_today.period_average),
      }),
    },
    {
      label: t("ownerDash.kRevenue"),
      value: money(k.revenue.value),
      unit: t("money.currency"),
      hint:
        k.revenue.change_percent === null
          ? t("ownerDash.kNoCompare")
          : t("ownerDash.kRevenueHint", { sign: k.revenue.change_percent >= 0 ? "+" : "−", p: pct(Math.abs(k.revenue.change_percent)) }),
    },
    {
      label: t("ownerDash.kCollected"),
      value: money(k.collected.value),
      unit: t("money.currency"),
      hint: t("ownerDash.kCollectedHint", { p: pct(k.collected.of_revenue_percent) }),
    },
    {
      label: t("ownerDash.kDebts"),
      value: money(k.debts.value),
      unit: t("money.currency"),
      hint: k.debts.largest
        ? t("ownerDash.kDebtsHint", {
            n: digits(String(k.debts.count)),
            amount: money(k.debts.largest.amount),
            room: digits(k.debts.largest.room),
          })
        : "",
    },
    {
      label: t("ownerDash.kNeglected"),
      value: digits(String(k.neglected_alerts.value)),
      hint:
        k.neglected_alerts.value && k.neglected_alerts.latest_at
          ? t("ownerDash.kNeglectedHint", { user: k.neglected_alerts.latest_shift_user ?? "—", date: formatDayMonth(k.neglected_alerts.latest_at) })
          : "",
      danger: k.neglected_alerts.value > 0,
    },
  ];
  return (
    <div className="grid grid-cols-5 gap-4 max-[1599px]:gap-3">
      {tiles.map((tile) => (
        <div key={tile.label} className="rounded-card border border-border bg-bg-surface p-4">
          <div className="text-label text-text-secondary">{tile.label}</div>
          <div className={`mt-1 flex items-baseline gap-1 ${tile.danger ? "text-danger" : ""}`}>
            <span className="text-headline-number">{tile.value}</span>
            {tile.unit && <span className={`text-body ${tile.danger ? "" : "text-text-secondary"}`}>{tile.unit}</span>}
          </div>
          <div className={`mt-1 min-h-4 text-label font-normal ${tile.danger ? "text-danger" : "text-text-secondary"}`}>{tile.hint}</div>
        </div>
      ))}
    </div>
  );
}

function Panel({ title, note, children, action }: { title: string; note?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex flex-col rounded-card border border-border bg-bg-surface">
      <div className="flex min-h-12 items-center gap-3 border-b border-border px-4 py-2">
        <h2 className="m-0 text-section-title">{title}</h2>
        {note && <span className="text-label font-normal text-text-secondary">{note}</span>}
        <div className="flex-1" />
        {action}
      </div>
      {children}
    </section>
  );
}

/**
 * Occupancy, last 30 nights: today on the right, earlier nights to the left (RTL exception 3, like the
 * reservations timeline). Drawn in an LTR box so x grows with time.
 */
function OccupancyChart({ d }: { d: Dashboard }) {
  const series = d.occupancy.series;
  const n = Math.max(1, series.length - 1);
  const points = series.map((p, i) => `${((i / n) * 600).toFixed(1)},${(200 - Math.min(100, p.percent) * 2).toFixed(1)}`).join(" ");
  const last = series[series.length - 1];
  const ticks = series.map((p, i) => ({ p, i })).filter(({ i }) => (series.length - 1 - i) % 7 === 0);
  return (
    <Panel
      title={t("ownerDash.occupancy")}
      note={t("ownerDash.occupancyNote", {
        avg: pct(d.occupancy.average),
        peak: pct(d.occupancy.peak.percent),
        date: formatDayMonth(d.occupancy.peak.date),
      })}
    >
      <div className="flex gap-2 p-4" dir="ltr">
        <div className="flex h-[200px] flex-col justify-between py-0 text-end text-label font-normal text-text-secondary">
          {[100, 75, 50, 25, 0].map((v) => (
            <span key={v} className="-my-2">
              {pct(v)}
            </span>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <svg viewBox="0 0 600 200" preserveAspectRatio="none" className="h-[200px] w-full" role="img" aria-label={t("ownerDash.occupancy")}>
            {[0, 50, 100, 150].map((y) => (
              <line key={y} x1="0" x2="600" y1={y} y2={y} className="stroke-border" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1="0" x2="600" y1="200" y2="200" className="stroke-border-strong" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            {series.length > 1 && (
              <>
                <polygon points={`0,200 ${points} 600,200`} className="fill-primary-soft" opacity="0.6" />
                <polyline points={points} fill="none" className="stroke-primary" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
              </>
            )}
          </svg>
          <div className="relative h-4 text-label font-normal text-text-secondary">
            {ticks.map(({ p, i }) => (
              <span key={p.date} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${(i / n) * 100}%` }}>
                {formatDayMonth(p.date)}
              </span>
            ))}
          </div>
        </div>
      </div>
      {last && (
        <div className="border-t border-border px-4 py-2 text-label font-normal text-text-secondary">
          {t("ownerDash.lastNight", {
            date: formatDayMonth(last.date),
            p: pct(last.percent),
            occ: digits(String(last.occupied)),
            rooms: digits(String(last.rooms)),
          })}
        </div>
      )}
    </Panel>
  );
}

function compact(minor: number): string {
  const units = minor / MINOR;
  if (units >= 1_000_000) return t("ownerDash.millions", { n: digits((units / 1_000_000).toFixed(2)) });
  if (units >= 1_000) return t("ownerDash.thousands", { n: digits(String(Math.round(units / 1_000))) });
  return digits(String(Math.round(units)));
}

// Above this many weeks (the 90-day period) the bars narrow and their values move to the tooltip.
const DENSE_WEEKS = 6;

/** Revenue (primary) against collected (chart-secondary) per week; the latest week on the right. */
function WeeksChart({ weeks }: { weeks: Dashboard["weeks"] }) {
  const max = Math.max(1, ...weeks.flatMap((w) => [w.revenue, w.collected]));
  const dense = weeks.length > DENSE_WEEKS;
  return (
    <Panel
      title={t("ownerDash.weeks")}
      action={
        <div className="flex items-center gap-3 text-label font-normal text-text-secondary">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-primary" />
            {t("ownerDash.revenue")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-chart-secondary" />
            {t("ownerDash.collected")}
          </span>
        </div>
      }
    >
      <div className={`flex h-[232px] items-end justify-around p-4 pb-2 ${dense ? "gap-1" : "gap-3"}`}>
        {[...weeks].reverse().map((w) => (
          <div
            key={w.label}
            className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-2"
            title={`${digits(w.label)} · ${t("ownerDash.revenue")} ${formatMoney(w.revenue)} · ${t("ownerDash.collected")} ${formatMoney(w.collected)}`}
          >
            <div className={`flex h-full w-full items-end justify-center ${dense ? "gap-0.5" : "gap-1.5"}`}>
              <Bar value={w.revenue} max={max} dense={dense} className="bg-primary" />
              <Bar value={w.collected} max={max} dense={dense} className="bg-chart-secondary" />
            </div>
            {/* Dense: the week's first day only (29/6); the full range is in the tooltip. */}
            <div className="max-w-full truncate whitespace-nowrap text-label font-normal text-text-secondary" dir={dense ? "ltr" : undefined}>
              {digits(dense ? w.label.split("–")[0] : w.label)}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Bar({ value, max, dense, className }: { value: number; max: number; dense: boolean; className: string }) {
  return (
    <div className={`flex h-full flex-col items-center justify-end gap-1 ${dense ? "w-full max-w-4" : "w-10"}`}>
      {!dense && <span className="text-label font-normal text-text-secondary">{compact(value)}</span>}
      <div className={`w-full rounded-t-sm ${className}`} style={{ height: `${Math.max(value ? 2 : 0, (value / max) * 80)}%` }} />
    </div>
  );
}

// Kind chips use the soft feedback colours; only «متجاوزة» uses a room-state colour (6.12 notes).
function chip(kind: Attention["kind"]): string {
  if (kind === "overdue") return `${stateColor("overdue").soft} ${stateColor("overdue").text}`;
  if (kind === "maint") return `${stateColor("maintenance").soft} ${stateColor("maintenance").text}`;
  if (kind === "neglected") return "bg-danger-soft text-danger-text";
  return "bg-warning-soft text-warning-text";
}

function AttentionList({ rows }: { rows: Attention[] }) {
  return (
    <Panel
      title={t("ownerDash.attention")}
      action={
        rows.length > 0 && (
          <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-danger px-2 text-label text-primary-text-on">{digits(String(rows.length))}</span>
        )
      }
    >
      {rows.length === 0 ? (
        <div className="flex flex-col items-center gap-1 p-6 text-center">
          <div className="text-body font-semibold">{t("ownerDash.allClear")}</div>
          <div className="text-label font-normal text-text-secondary">{t("ownerDash.allClearHint")}</div>
        </div>
      ) : (
        rows.map((row, i) => (
          <Link
            key={i}
            to={`/reports/${row.report}`}
            className="flex min-h-12 items-center gap-3 border-b border-border px-4 py-2 text-table-cell text-text-primary no-underline last:border-b-0 hover:bg-bg-page"
          >
            <span className={`inline-flex h-6 flex-none items-center rounded-control px-2 text-label ${chip(row.kind)}`}>{row.label}</span>
            <span className="min-w-0 flex-1">{digits(row.text)}</span>
            <ChevronLeft className="h-icon-inline w-icon-inline flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
          </Link>
        ))
      )}
    </Panel>
  );
}

const STAFF_GRID = "grid grid-cols-[1.4fr_1fr_1.2fr_1fr_1fr] items-center gap-3 px-4";

function StaffTable({ rows }: { rows: Dashboard["staff"] }) {
  return (
    <Panel
      title={t("ownerDash.staff")}
      note={t("ownerDash.staffNote")}
      action={
        <Link to="/reports/alert_response" className="text-body font-medium text-primary no-underline hover:text-primary-hover">
          {t("ownerDash.fullReport")}
        </Link>
      }
    >
      <div className={`${STAFF_GRID} h-10 bg-bg-surface-2 text-label text-text-secondary`}>
        {["name", "total", "handled", "neglected", "delay"].map((k) => (
          <div key={k}>{t(`ownerDash.s_${k}`)}</div>
        ))}
      </div>
      {rows.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("ownerDash.staffEmpty")}</div>}
      {rows.map((s) => (
        <div key={s.name} className={`${STAFF_GRID} h-11 border-b border-border text-table-cell last:border-b-0`}>
          <div className="font-medium">{s.name}</div>
          <div>{digits(String(s.total))}</div>
          <div>
            {digits(String(s.handled))} <span className="text-text-secondary">({pct(s.handled_percent)})</span>
          </div>
          <div className={s.neglected > 0 ? "font-semibold text-danger" : ""}>{digits(String(s.neglected))}</div>
          <div>{s.average_delay_minutes === null ? "—" : duration(s.average_delay_minutes)}</div>
        </div>
      ))}
      <div className="border-t border-border px-4 py-3 text-label font-normal text-text-secondary">{t("ownerDash.delayNote")}</div>
    </Panel>
  );
}

function Skeleton() {
  return (
    <>
      <div className="grid grid-cols-5 gap-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="skeleton h-[104px] rounded-card" />
        ))}
      </div>
      <div className="grid grid-cols-[3fr_2fr] gap-4">
        <div className="skeleton h-[300px] rounded-card" />
        <div className="skeleton h-[300px] rounded-card" />
      </div>
    </>
  );
}

