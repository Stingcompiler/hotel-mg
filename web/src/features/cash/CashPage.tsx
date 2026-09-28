import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, LockOpen, Printer, Receipt, TriangleAlert } from "lucide-react";
import { useState } from "react";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { keys, useCurrentShift, useSystemStatus } from "@/api/queries";
import { ErrorBanner, groupThousands, Segmented, Select } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { stateColor } from "@/design/state";
import { openPrint } from "@/features/print/PrintPage";
import { elapsed } from "@/i18n/counts";
import { formatDayDate, formatDayMonth, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { notice } from "@/lib/notices";

type Current = components["schemas"]["CurrentShift"];
const money = (v: number) => formatMoney(v);
const signed = (v: number) => (v < 0 ? `− ${formatMoney(-v)}` : v > 0 ? `+ ${formatMoney(v)}` : "0");

/** 6.7 Cash & shift: the open shift with expected cash and closing, opening a shift, and the shift history. */
export function CashPage() {
  const [tab, setTab] = useState<"current" | "history">("current");
  const current = useCurrentShift().data;
  // «طباعة كشف الوردية»: the open shift, or the last closed one when none is open.
  const printable = current?.shift?.id ?? current?.last_closed?.id;
  return (
    <div className="flex h-full min-h-[620px] flex-col gap-4 p-6 max-[1599px]:gap-3">
      <div className="flex h-9 items-center gap-4">
        <h1 className="m-0 text-page-title">{t("cash.title")}</h1>
        <Segmented
          label={t("cash.title")}
          value={tab}
          onChange={setTab}
          options={[
            { value: "current", label: t("cash.tabCurrent") },
            { value: "history", label: t("cash.tabHistory") },
          ]}
        />
        <div className="flex-1" />
        <button type="button" disabled={!printable} onClick={() => openPrint("shift", printable!)} className={`${buttons.secondary} h-9 px-4`}>
          <Printer className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("print.printStatement")}
        </button>
      </div>
      {tab === "current" ? <CurrentTab /> : <HistoryTab />}
    </div>
  );
}

function CurrentTab() {
  const current = useCurrentShift().data;
  if (!current) return <div className="skeleton h-64 rounded-card" />;
  return current.shift ? <OpenShift current={current} /> : <NoShift current={current} />;
}

function useRefreshCash() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: keys.currentShift });
    void queryClient.invalidateQueries({ queryKey: ["shifts", "history"] });
  };
}

function OpenShift({ current }: { current: Current }) {
  const shift = current.shift!;
  const totals = current.totals!;
  const offline = useSystemStatus().isError;
  const refresh = useRefreshCash();
  const [counted, setCounted] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const countedMinor = counted.trim() ? parseMoney(counted) : null;
  const diff = countedMinor === null ? null : countedMinor - totals.expected;

  const close = useMutation({
    mutationFn: () =>
      data(api.POST("/api/v1/shifts/close", { body: { counted: countedMinor!, difference_reason: reason.trim(), version: shift.version } })),
    onSuccess: () => {
      setConfirming(false);
      notice(t("cash.closedNotice", { counted: money(countedMinor!), diff: signed(diff ?? 0) }));
      setCounted("");
      setReason("");
      refresh();
    },
    onError: (e) => {
      setConfirming(false);
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    },
  });
  // Closing is irreversible: a confirmation step repeats expected, counted and the difference first.
  const [confirming, setConfirming] = useState(false);
  const submit = () => {
    if (countedMinor === null) return setError(t("cash.errCounted"));
    if (diff !== 0 && !reason.trim()) return setError(t("cash.errReason"));
    setError(null);
    setConfirming(true);
  };

  const line = "flex justify-between border-b border-border py-2.5";
  const sub = "flex justify-between py-1.5 ps-5 text-text-secondary";
  return (
    <>
      <section className="grid grid-cols-[1fr_1px_1fr] rounded-card border border-border bg-bg-surface">
        <div className="flex flex-col gap-3 px-6 py-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="m-0 text-section-title">{t("cash.current")}</h2>
            <span className="inline-flex h-6 items-center gap-1.5 rounded-control bg-success-soft px-2 text-label text-success-text">
              <span className="h-2 w-2 rounded-full bg-success" />
              {t("cash.open")}
            </span>
            <span className="text-body text-text-secondary">
              {t("cash.openedBy", { name: shift.opened_by, date: formatDayDate(shift.opened_at) })} <span dir="ltr">{formatTime(shift.opened_at)}</span> ·{" "}
              {t("cash.since", { time: elapsed(shift.opened_at) })}
            </span>
          </div>
          <div className="text-body">
            <div className={line}>
              <span>{t("cash.opening")}</span>
              <span className="font-semibold">{money(totals.opening)}</span>
            </div>
            <div className={`${line} font-semibold`}>
              <span>{t("cash.receipts")}</span>
              <span>{money(totals.receipts.total)}</span>
            </div>
            {(["cash", "bankak", "transfer"] as const).map((m, i) => (
              <div key={m} className={`${sub} ${i === 2 ? "border-b border-border pb-2.5" : ""}`}>
                <span>{t(`payMethod.${m}`)}</span>
                <span>{money(totals.receipts[m])}</span>
              </div>
            ))}
            {totals.foreign.map((f) => (
              <div key={f.currency} className={line}>
                <span>{t("cash.foreignCash", { currency: f.symbol })}</span>
                <span className="font-semibold">
                  {formatMoney(f.cash)} {f.symbol}
                  <span className="ms-2 text-label font-normal text-text-secondary">{t("cash.foreignWorth", { amount: money(f.base) })}</span>
                </span>
              </div>
            ))}
            <div className={line}>
              <span>{t("cash.cashExpenses")}</span>
              <span className="font-semibold text-danger"><span dir="ltr">{signed(-totals.expenses.cash)}</span></span>
            </div>
            <div className="flex items-end justify-between pt-3">
              <span className="text-section-title">{t("cash.expected")}</span>
              <span className="text-headline-number">
                {money(totals.expected)} <span className="text-[16px] font-semibold">{t("money.currency")}</span>
              </span>
            </div>
          </div>
          <div className="text-label font-normal text-text-secondary">{t("cash.formula")}</div>
        </div>
        <div className="bg-border" />
        <div className="flex flex-col gap-3 px-6 py-4">
          <h2 className="m-0 text-section-title">{t("cash.close")}</h2>
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-text-secondary">{t("cash.counted")}</span>
            <span className="flex h-11 items-center justify-between rounded-control border border-border-strong bg-bg-surface px-3 focus-within:border-primary">
              <input
                inputMode="decimal"
                value={counted}
                onChange={(e) => {
                  groupThousands(e.target);
                  setCounted(e.target.value);
                }}
                className="w-full border-0 bg-transparent p-0 font-sans text-page-title text-text-primary outline-none"
              />
              <span className="text-body font-medium text-text-secondary">{t("money.currency")}</span>
            </span>
          </label>
          {diff !== null && (
            <div className={`flex items-center justify-between rounded-card px-4 py-3 ${diff === 0 ? "bg-success-soft text-success-text" : "bg-danger-soft text-danger-text"}`}>
              <div>
                <div className="text-label">{t("cash.difference")}</div>
                <div className="text-label font-normal">{diff === 0 ? t("cash.equal") : diff < 0 ? t("cash.less") : t("cash.more")}</div>
              </div>
              <div className={`text-headline-number ${diff === 0 ? "text-success" : "text-danger"}`}>
                <span dir="ltr">{signed(diff)}</span> <span className="text-[16px] font-semibold">{t("money.currency")}</span>
              </div>
            </div>
          )}
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-text-secondary">
              {t("cash.reason")} {diff !== null && diff !== 0 && <span className="text-danger">*</span>} <span className="text-text-disabled">{t("cash.reasonHint")}</span>
            </span>
            <textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="rounded-control border border-border-strong bg-bg-surface px-3 py-2 font-sans text-body text-text-primary"
            />
          </label>
          {error && <ErrorBanner>{error}</ErrorBanner>}
          <div className="mt-auto flex flex-wrap items-center gap-2">
            <button type="button" disabled={offline || close.isPending} onClick={submit} className={buttons.primary}>
              <Lock className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
              {t("cash.close")}
            </button>
            <span className="text-label font-normal text-text-secondary">{t("cash.closeNote", { name: shift.opened_by })}</span>
          </div>
        </div>
      </section>
      {confirming && (
        <Modal
          title={t("cash.confirmTitle")}
          width={480}
          onClose={() => setConfirming(false)}
          footer={
            <>
              <button type="button" disabled={close.isPending} onClick={() => close.mutate()} className={buttons.primary}>
                <Lock className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
                {t("cash.confirmClose")}
              </button>
              <div className="flex-1" />
              <button type="button" onClick={() => setConfirming(false)} className={buttons.ghost}>
                {t("common.cancel")}
              </button>
            </>
          }
        >
          <div className="flex flex-col divide-y divide-border">
            <div className="flex justify-between py-2.5 text-body">
              <span className="text-text-secondary">{t("cash.expected")}</span>
              <span className="font-semibold">{money(totals.expected)} {t("money.currency")}</span>
            </div>
            <div className="flex justify-between py-2.5 text-body">
              <span className="text-text-secondary">{t("cash.counted")}</span>
              <span className="font-semibold">{money(countedMinor ?? 0)} {t("money.currency")}</span>
            </div>
            <div className={`flex justify-between py-2.5 text-body ${diff ? "text-danger" : "text-success-text"}`}>
              <span>{t("cash.difference")}</span>
              <span className="font-bold" dir="ltr">
                {signed(diff ?? 0)}
              </span>
            </div>
          </div>
          {reason.trim() && (
            <div className="text-body text-text-secondary">
              {t("cash.reason")}: {reason.trim()}
            </div>
          )}
          <div className="text-label font-normal text-text-secondary">{t("cash.confirmText")}</div>
        </Modal>
      )}
      <Movements current={current} />
    </>
  );
}

function Movements({ current }: { current: Current }) {
  const [filter, setFilter] = useState<"all" | "in" | "out">("all");
  const rows = current.movements.filter((m) => filter === "all" || m.kind === filter);
  const GRID = "grid grid-cols-[100px_140px_1fr_160px_120px_160px] items-center gap-4 px-4";
  const chip = { in: "bg-success-soft text-success-text", out: "bg-danger-soft text-danger-text", open: "bg-bg-surface-2 text-text-secondary" };
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
      <div className="flex h-12 flex-none items-center gap-3 border-b border-border px-4">
        <h2 className="m-0 text-section-title">{t("cash.moves")}</h2>
        <span className="text-body text-text-secondary">{t("cash.movesCount", { n: digits(String(current.movements.length)) })}</span>
        <div className="flex-1" />
        <Segmented
          label={t("cash.moves")}
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: t("cash.all") },
            { value: "in", label: t("cash.in") },
            { value: "out", label: t("cash.out") },
          ]}
        />
      </div>
      <div className={`${GRID} h-10 flex-none bg-bg-surface-2 text-label text-text-secondary`}>
        <div>{t("cash.colTime")}</div>
        <div>{t("cash.colType")}</div>
        <div>{t("cash.colText")}</div>
        <div>{t("cash.colAmount")}</div>
        <div>{t("cash.colMethod")}</div>
        <div>{t("cash.colBy")}</div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("cash.noMovesYet")}</div>}
        {rows.map((m, i) => (
          <div key={`${m.ref_id}-${i}`} className={`${GRID} h-10 border-b border-border text-table-cell hover:bg-bg-page`}>
            <div dir="ltr" className="text-end text-text-secondary">
              {formatTime(m.at)}
            </div>
            <div>
              <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${chip[m.kind]}`}>
                {t(m.kind === "in" ? "cash.typeIn" : m.kind === "out" ? "cash.typeOut" : "cash.typeOpen")}
              </span>
            </div>
            <div className="truncate">
              {m.text}{" "}
              {m.reference && (
                <span dir="ltr" className="text-label font-normal text-text-secondary">
                  {m.reference}
                </span>
              )}
            </div>
            <div className={`font-semibold ${m.amount < 0 ? "text-danger" : ""}`}><span dir="ltr">{signed(m.amount)}</span></div>
            <div>{["cash", "bankak", "transfer"].includes(m.method) ? t(`payMethod.${m.method}`) : m.method}</div>
            <div className="text-text-secondary">{m.by}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NoShift({ current }: { current: Current }) {
  const offline = useSystemStatus().isError;
  const refresh = useRefreshCash();
  const [opening, setOpening] = useState(formatMoney(current.suggested_opening));
  const [error, setError] = useState<string | null>(null);
  const last = current.last_closed;
  const open = useMutation({
    mutationFn: () => data(api.POST("/api/v1/shifts/open", { body: { opening: parseMoney(opening) ?? 0 } })),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  return (
    <>
      <div className="flex h-11 items-center gap-3 rounded-card bg-warning-soft px-4 text-body font-medium text-warning-text">
        <TriangleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
        {t("cash.noShift")}
      </div>
      <section className="flex items-end gap-4 rounded-card border border-border bg-bg-surface p-6">
        <div className="flex flex-1 flex-col gap-1">
          <h2 className="m-0 text-section-title">{t("cash.openNew")}</h2>
          <div className="text-body text-text-secondary">
            {last
              ? t("cash.lastClosed", {
                  date: `${formatDayMonth(last.closed_at!)} ${formatTime(last.closed_at!)}`,
                  by: last.closed_by_name || last.opened_by,
                  counted: `${formatMoney(last.counted ?? 0)} ${t("money.currency")}`,
                  diff: signed(last.difference ?? 0),
                })
              : t("cash.noLast")}
          </div>
        </div>
        <label className="flex w-56 flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("cash.opening")}</span>
          <span className="flex h-11 items-center justify-between rounded-control border border-primary bg-bg-surface px-3">
            <input autoFocus inputMode="decimal" value={opening} onChange={(e) => setOpening(e.target.value)} className="w-full border-0 bg-transparent p-0 font-sans text-page-title text-text-primary outline-none" />
            <span className="text-body font-medium text-text-secondary">{t("money.currency")}</span>
          </span>
        </label>
        <button type="button" disabled={offline || open.isPending || parseMoney(opening) === null} onClick={() => open.mutate()} className={buttons.primary}>
          <LockOpen className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("cash.openButton")}
        </button>
      </section>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <section className="flex flex-1 flex-col items-center justify-center gap-3 rounded-card border border-border bg-bg-surface">
        <Receipt className="h-10 w-10 text-text-disabled" strokeWidth={1.75} aria-hidden />
        <div className="text-body text-text-secondary">{t("cash.noMoves")}</div>
      </section>
    </>
  );
}

function range(kind: "week" | "month" | "lastMonth") {
  const d = new Date();
  const iso = (x: Date) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  if (kind === "week") {
    const start = new Date(d);
    start.setDate(d.getDate() - ((d.getDay() + 1) % 7)); // weeks start on Saturday
    return { date_from: iso(start), date_to: iso(d) };
  }
  if (kind === "month") return { date_from: iso(new Date(d.getFullYear(), d.getMonth(), 1)), date_to: iso(d) };
  return { date_from: iso(new Date(d.getFullYear(), d.getMonth() - 1, 1)), date_to: iso(new Date(d.getFullYear(), d.getMonth(), 0)) };
}

function HistoryTab() {
  const [period, setPeriod] = useState<"week" | "month" | "lastMonth">("week");
  const [user, setUser] = useState("");
  const users = useQuery({ queryKey: ["auth", "users"], queryFn: () => data(api.GET("/api/v1/auth/users")) }).data ?? [];
  const history = useQuery({
    queryKey: ["shifts", "history", period, user],
    queryFn: () => data(api.GET("/api/v1/shifts/", { params: { query: { ...range(period), ...(user ? { user } : {}) } } })),
  }).data;
  const GRID = "grid grid-cols-[130px_110px_minmax(120px,1fr)_110px_110px_110px_110px_110px_minmax(140px,1.4fr)_40px] items-center gap-3 px-4";
  const zero = stateColor("ready");
  return (
    <>
      <div className="flex items-center gap-3">
        <div className="flex-1" />
        <div className="w-44">
          <Select aria-label={t("cash.rangeWeek")} value={period} onChange={(e) => setPeriod(e.target.value as typeof period)}>
            <option value="week">{t("cash.rangeWeek")}</option>
            <option value="month">{t("cash.rangeMonth")}</option>
            <option value="lastMonth">{t("cash.rangeLastMonth")}</option>
          </Select>
        </div>
        <div className="w-44">
          <Select aria-label={t("cash.allUsers")} value={user} onChange={(e) => setUser(e.target.value)}>
            <option value="">{t("cash.allUsers")}</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name}
              </option>
            ))}
          </Select>
        </div>
      </div>
      {history && (
        <div className="grid grid-cols-3 gap-3">
          <Kpi label={t("cash.kShifts")} value={digits(String(history.count))} />
          <Kpi label={t("cash.kWithDiff")} value={digits(String(history.with_difference))} danger={history.with_difference > 0} />
          <Kpi label={t("cash.kNet")} value={signed(history.net_difference)} danger={history.net_difference !== 0} currency />
        </div>
      )}
      {/* Ten columns: wider than a 1366 px window, so the table scrolls sideways instead of squeezing the names. */}
      <section className="min-h-0 flex-1 overflow-auto rounded-card border border-border bg-bg-surface">
        <div className="w-max min-w-full">
          <div className={`${GRID} sticky top-0 z-10 h-10 bg-bg-surface-2 text-label text-text-secondary`}>
            {["hDate", "hTime", "hUser", "hOpening", "hReceipts", "hExpenses", "hCounted", "hDiff", "hReason"].map((k) => (
              <div key={k}>{t(`cash.${k}`)}</div>
            ))}
            <div />
          </div>
          <div>
            {history?.shifts.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("cash.noHistory")}</div>}
            {history?.shifts.map((s) => (
              <div key={s.id} className={`${GRID} h-10 border-b border-border text-table-cell hover:bg-bg-page`}>
                <div>{formatDayMonth(s.opened_at)}</div>
                <div dir="ltr" className="text-end text-text-secondary">
                  {formatTime(s.opened_at)}–{s.closed_at ? formatTime(s.closed_at) : ""}
                </div>
                <div>{s.opened_by}</div>
                <div>{money(s.opening)}</div>
                <div>{money(s.receipts)}</div>
                <div>{money(s.cash_expenses)}</div>
                <div className="font-semibold">{s.counted === null ? "—" : money(s.counted)}</div>
                <div>
                  {s.difference === null ? (
                    <span className="text-label text-text-secondary">{t("cash.stillOpen")}</span>
                  ) : (
                    <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${s.difference === 0 ? `${zero.soft} ${zero.text}` : "bg-danger-soft text-danger-text"}`}>
                      <span dir="ltr">{signed(s.difference)}</span>
                    </span>
                  )}
                </div>
                <div className="truncate text-label font-normal text-text-secondary">{s.difference_reason}</div>
                <button
                  type="button"
                  aria-label={t("print.printStatement")}
                  title={t("print.printStatement")}
                  onClick={() => openPrint("shift", s.id)}
                  className="flex h-8 w-8 items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2"
                >
                  <Printer className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
                </button>
              </div>
            ))}
          </div>
          <div className="flex h-10 flex-none items-center justify-between border-t border-border px-4 text-label font-normal text-text-secondary">
            <span>{t("cash.historyCount", { n: digits(String(history?.shifts.length ?? 0)) })}</span>
            <span>{t("cash.historyFoot")}</span>
          </div>
        </div>
      </section>
    </>
  );
}

function Kpi({ label, value, danger = false, currency = false }: { label: string; value: string; danger?: boolean; currency?: boolean }) {
  // Signed values keep their sign in front: the number is laid out left to right.
  return (
    <div className="flex items-baseline justify-between rounded-card border border-border bg-bg-surface px-4 py-3">
      <div className="text-label text-text-secondary">{label}</div>
      <div className={`text-headline-number ${danger ? "text-danger" : ""}`}>
        <span dir="ltr">{value}</span> {currency && <span className="text-body font-semibold">{t("money.currency")}</span>}
      </div>
    </div>
  );
}
