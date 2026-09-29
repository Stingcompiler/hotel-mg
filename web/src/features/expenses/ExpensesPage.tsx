import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Info, Plus, Printer, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { keys, useCurrentShift, useHotelSettings, useSystemStatus } from "@/api/queries";
import { Drawer } from "@/components/ui/Drawer";
import { session } from "@/api/session";
import { ErrorBanner, Field, MoneyInput, Segmented, Select, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { openPrint } from "@/features/print/PrintPage";
import { useRoomBoard } from "@/features/rooms/RoomBoardPage";
import { formatDayMonth, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { notice } from "@/lib/notices";

type Expense = components["schemas"]["Expense"];
type Category = components["schemas"]["ExpenseCategoryEnum"];
type Method = "cash" | "bankak" | "transfer";
type Scope = "shift" | "today" | "month";
const CATEGORIES: Category[] = ["supplies", "purchases", "maintenance", "bills", "salaries", "other"];
const money = (v: number) => `${formatMoney(v)} ${t("money.currency")}`;

/** 6.8 Expenses: scope tabs, KPI tiles, the list (reversals, missing receipts) and the «مصروف جديد» drawer. */
export function ExpensesPage() {
  const queryClient = useQueryClient();
  const offline = useSystemStatus().isError;
  const threshold = useHotelSettings().data?.expense_attachment_threshold ?? 0;
  const [scope, setScope] = useState<Scope>("shift");
  const [category, setCategory] = useState<Category | "">("");
  const [creating, setCreating] = useState(false);
  const [reversing, setReversing] = useState<Expense | null>(null);
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [scope, category]);
  const list = useQuery({
    queryKey: ["expenses", scope, category, page],
    queryFn: () => data(api.GET("/api/v1/expenses/", { params: { query: { scope, page, ...(category ? { category } : {}) } } })),
    placeholderData: keepPreviousData,
  });
  const summary = useQuery({ queryKey: ["expenses", "summary"], queryFn: () => data(api.GET("/api/v1/expenses/summary")) }).data;
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["expenses"] });
    void queryClient.invalidateQueries({ queryKey: keys.currentShift });
  };
  const rows = list.data?.results ?? [];

  return (
    <div className="flex h-full min-h-[620px] flex-col gap-4 p-6 max-[1599px]:gap-3">
      <div className="flex h-9 items-center gap-3">
        <h1 className="m-0 text-page-title">{t("expenses.title")}</h1>
        <Segmented<Scope>
          label={t("expenses.title")}
          value={scope}
          onChange={setScope}
          options={[
            { value: "shift", label: t("expenses.scopeShift") },
            { value: "today", label: t("expenses.scopeToday") },
            { value: "month", label: t("expenses.scopeMonth") },
          ]}
        />
        <div className="w-44">
          <Select aria-label={t("expenses.allCategories")} value={category} onChange={(e) => setCategory(e.target.value as Category | "")}>
            <option value="">{t("expenses.allCategories")}</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`expenseCategory.${c}`)}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex-1" />
        <button type="button" disabled={offline} title={offline ? t("common.offlineHint") : undefined} onClick={() => setCreating(true)} className={`${buttons.primary} h-9 px-4`}>
          <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("expenses.new")}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-4 gap-4 max-[1599px]:gap-3">
          <Tile label={t("expenses.kShift")} value={money(summary.shift_total)} hint={t("expenses.kShiftHint", { n: digits(String(summary.shift_count)) })} />
          <Tile label={t("expenses.kMonth")} value={money(summary.month_total)} />
          <Tile
            label={t("expenses.kTop")}
            value={summary.top_category ? t(`expenseCategory.${summary.top_category}`) : "—"}
            hint={
              summary.top_category
                ? t("expenses.kTopHint", {
                    amount: money(summary.top_category_total),
                    pct: digits(String(summary.month_total ? Math.round((100 * summary.top_category_total) / summary.month_total) : 0)),
                  })
                : undefined
            }
          />
          <Tile
            label={t("expenses.kAwaiting")}
            value={digits(String(summary.awaiting_attachment))}
            hint={t("expenses.kAwaitingHint", { amount: formatMoney(threshold) })}
            warn={summary.awaiting_attachment > 0}
          />
        </div>
      )}

      {!offline && session.role !== "owner" && <QuickExpense threshold={threshold} onSaved={refresh} onNeedsReceipt={() => setCreating(true)} />}

      <ExpenseTable
        rows={rows}
        total={list.data?.count ?? 0}
        loading={list.isPending}
        page={page}
        hasPrev={!!list.data?.previous}
        hasNext={!!list.data?.next}
        onPage={setPage}
        offline={offline}
        onReverse={setReversing}
        onUploaded={refresh}
      />

      {creating && (
        <NewExpenseDrawer
          threshold={threshold}
          onClose={() => setCreating(false)}
          onDone={() => {
            setCreating(false);
            refresh();
          }}
        />
      )}
      {reversing && (
        <ReverseModal
          expense={reversing}
          onClose={() => setReversing(null)}
          onDone={() => {
            setReversing(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

/**
 * Gap Fill «Quick Expense»: one row above the list for the everyday cash expense (amount, category, note) with no
 * drawer. Anything above the receipt threshold, or not cash, goes through «مصروف جديد».
 */
function QuickExpense({ threshold, onSaved, onNeedsReceipt }: { threshold: number; onSaved: () => void; onNeedsReceipt: () => void }) {
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState<Category>("supplies");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const minor = parseMoney(amount);
  const needsReceipt = minor !== null && minor > threshold;
  const save = useMutation({
    mutationFn: () => data(api.POST("/api/v1/expenses/", { body: { category, amount: minor!, note: note.trim(), method: "cash", reference: "", room: null } })),
    onSuccess: () => {
      notice(t("expenses.saved", { amount: money(minor!) }));
      setAmount("");
      setNote("");
      setError(null);
      onSaved();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  const submit = () => {
    if (minor === null || minor <= 0) return setError(t("expenses.errAmount"));
    if (!note.trim()) return setError(t("expenses.errNote"));
    if (needsReceipt) return onNeedsReceipt();
    setError(null);
    save.mutate();
  };
  return (
    <section className="flex flex-col gap-2 rounded-card border border-border bg-bg-surface px-4 py-3">
      <div className="flex flex-wrap items-end gap-3">
        <span className="text-label text-text-secondary">{t("expenses.quickTitle")}</span>
        <label className="flex w-48 shrink-0 flex-col gap-1">
          <span className="sr-only">{t("expenses.quickAmount")}</span>
          <MoneyInput
            value={amount}
            placeholder={t("expenses.quickAmount")}
            invalid={!!amount && (minor === null || minor <= 0)}
            onChange={(e) => setAmount(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
        </label>
        <div className="w-40 shrink-0">
          <Select aria-label={t("expenses.category")} value={category} onChange={(e) => setCategory(e.target.value as Category)}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`expenseCategory.${c}`)}
              </option>
            ))}
          </Select>
        </div>
        <TextInput
          aria-label={t("expenses.quickNote")}
          placeholder={t("expenses.quickNote")}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          className="min-w-56 max-w-md flex-1"
        />
        <button type="button" disabled={save.isPending} onClick={submit} className={`${buttons.primary} h-9 px-4`}>
          {needsReceipt ? t("expenses.new") : t("expenses.quickSave")}
        </button>
        <span className="text-label font-normal text-text-secondary">{t("expenses.quickHint", { amount: money(threshold) })}</span>
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </section>
  );
}

function Tile({ label, value, hint, warn = false }: { label: string; value: string; hint?: string; warn?: boolean }) {
  return (
    <div className="rounded-card border border-border bg-bg-surface p-4">
      <div className="text-label text-text-secondary">{label}</div>
      <div className={`mt-1 text-headline-number ${warn ? "text-warning" : ""}`}>{value}</div>
      {hint && <div className="mt-1 text-label font-normal text-text-secondary">{hint}</div>}
    </div>
  );
}

// The description keeps at least 160 px; the fixed columns fit their content (an amount up to 100,000,000).
const GRID = "grid grid-cols-[130px_120px_minmax(160px,1fr)_130px_90px_110px_120px_64px] items-center gap-3 px-4";

function ExpenseTable({
  rows,
  total,
  loading,
  page,
  hasPrev,
  hasNext,
  onPage,
  offline,
  onReverse,
  onUploaded,
}: {
  rows: Expense[];
  total: number;
  loading: boolean;
  page: number;
  hasPrev: boolean;
  hasNext: boolean;
  onPage: (next: number) => void;
  offline: boolean;
  onReverse: (e: Expense) => void;
  onUploaded: () => void;
}) {
  const pager = "h-9 rounded-control border-0 bg-transparent px-2 font-sans text-label text-primary hover:bg-bg-surface-2 disabled:text-text-disabled disabled:hover:bg-transparent";
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
      <div className={`${GRID} h-10 flex-none bg-bg-surface-2 text-label text-text-secondary`}>
        {["colDate", "colCategory", "colText", "colAmount", "colMethod", "colAttachment", "colBy"].map((k) => (
          <div key={k} className={k === "colAmount" ? "text-end" : ""}>
            {t(`expenses.${k}`)}
          </div>
        ))}
        <div />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {loading &&
          Array.from({ length: 6 }, (_, i) => (
            <div key={i} className={`${GRID} h-10 border-b border-border`}>
              {Array.from({ length: 7 }, (_, j) => (
                <div key={j} className="skeleton h-4 rounded" />
              ))}
            </div>
          ))}
        {!loading && rows.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("expenses.empty")}</div>}
        {rows.map((e) => {
          const correction = !!e.reverses;
          const muted = e.reversed ? "text-text-secondary line-through" : "";
          return (
            <div key={e.id} className={`${GRID} h-10 border-b border-border text-table-cell ${correction ? "bg-danger-soft text-danger-text" : "hover:bg-bg-page"}`}>
              <div className="text-label font-normal text-text-secondary">
                {formatDayMonth(e.spent_at)} · <span dir="ltr">{formatTime(e.spent_at)}</span>
              </div>
              <div>
                <span className="inline-flex h-6 items-center rounded-control bg-bg-surface-2 px-2 text-label text-text-primary">{e.category_label}</span>
              </div>
              <div className={`flex min-w-0 items-center gap-2 ${muted}`}>
                {correction && <Undo2 className="h-icon-inline w-icon-inline flex-none text-danger" strokeWidth={1.75} aria-hidden />}
                <span className="truncate">
                  {correction ? t("expenses.correction", { reason: e.reason }) : e.note}
                  {e.room_number && ` · ${digits(e.room_number)}`}
                </span>
              </div>
              <div className={`text-end font-semibold ${muted}`}>
                <span dir="ltr">{correction ? "− " : ""}{formatMoney(Math.abs(e.amount))}</span> {t("money.currency")}
              </div>
              <div>{t(`payMethod.${e.method}`)}</div>
              <div>
                {e.attachments.length ? (
                  <span className="text-label text-success-text">{t("expenses.attached")}</span>
                ) : e.attachment_missing && !correction ? (
                  <AttachButton expense={e} disabled={offline} onDone={onUploaded} />
                ) : (
                  <span className="text-label text-text-disabled">{t("expenses.none")}</span>
                )}
              </div>
              <div className="text-text-secondary">{e.by}</div>
              <div>
                {!correction && !e.reversed && (
                  <button type="button" disabled={offline} onClick={() => onReverse(e)} className="h-9 rounded-control border-0 bg-transparent px-2 font-sans text-label font-medium text-danger hover:bg-danger-soft disabled:text-text-disabled disabled:hover:bg-transparent">
                    {t("expenses.reverse")}
                  </button>
                )}
                {e.reversed && <span className="text-label text-text-disabled">{t("expenses.reversed")}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex h-10 flex-none items-center justify-between border-t border-border px-4 text-label font-normal text-text-secondary">
        <span>{t("expenses.foot", { shown: digits(String(rows.length)), total: digits(String(total)) })}</span>
        <span className="flex items-center gap-2">
          <button type="button" disabled={!hasPrev} onClick={() => onPage(page - 1)} className={pager}>
            {t("guests.prev")}
          </button>
          {t("guests.page", { n: digits(String(page)) })}
          <button type="button" disabled={!hasNext} onClick={() => onPage(page + 1)} className={pager}>
            {t("guests.next")}
          </button>
        </span>
        <span>{t("expenses.footNote")}</span>
      </div>
    </section>
  );
}

async function upload(expenseId: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  await data(
    api.POST("/api/v1/expenses/{id}/attachments", { params: { path: { id: expenseId } }, body: body as never, bodySerializer: (b: unknown) => b as FormData }),
  );
}

function AttachButton({ expense, disabled, onDone }: { expense: Expense; disabled: boolean; onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" disabled={disabled} onClick={() => input.current?.click()} className="h-9 rounded-control border-0 bg-transparent px-2 font-sans text-label font-medium text-warning-text underline hover:bg-warning-soft">
        {t("expenses.missing")}
      </button>
      <input
        ref={input}
        type="file"
        accept="image/*,application/pdf"
        className="sr-only"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) {
            await upload(expense.id, file);
            onDone();
          }
        }}
      />
    </>
  );
}

type RoomChoice = { id: string; number: string; name: string; floor: number; room_type_name: string };

/** «مرتبط بغرفة»: rooms grouped by type («شقة», «جناح»…), each with its name and floor (owner request 2026-09-28). */
export function roomGroups(rooms: RoomChoice[]): { type: string; rooms: { id: string; label: string }[] }[] {
  return [...new Set(rooms.map((r) => r.room_type_name))].map((type) => ({
    type,
    rooms: rooms
      .filter((r) => r.room_type_name === type)
      .map((r) => ({ id: r.id, label: [digits(r.number), r.name, t("expenses.floorN", { n: digits(String(r.floor)) })].filter(Boolean).join(" · ") })),
  }));
}

function NewExpenseDrawer({ threshold, onClose, onDone }: { threshold: number; onClose: () => void; onDone: () => void }) {
  const shift = useCurrentShift().data?.shift;
  const rooms = useRoomBoard().data?.rooms ?? [];
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState<Category>("supplies");
  const [note, setNote] = useState("");
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [room, setRoom] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const minor = parseMoney(amount);
  const needsReceipt = minor !== null && minor > threshold;

  const save = useMutation({
    mutationFn: async (print: boolean) => {
      const created = await data(
        api.POST("/api/v1/expenses/", { body: { category, amount: minor!, note: note.trim(), method, reference: reference.trim(), room: room || null } }),
      );
      if (file) await upload(created.id, file);
      if (print) openPrint("expense", created.id);
      notice(t("expenses.saved", { amount: money(minor!) }));
    },
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  const submit = (print = false) => {
    if (minor === null || minor <= 0) return setError(t("expenses.errAmount"));
    if (!note.trim()) return setError(t("expenses.errNote"));
    if (method !== "cash" && !reference.trim()) return setError(t("expenses.errReference"));
    if (needsReceipt && !file) return setError(t("expenses.errReceipt"));
    setError(null);
    save.mutate(print);
  };

  return (
    <Drawer
      title={t("expenses.new")}
      onClose={onClose}
      footer={
        <>
          <button type="button" disabled={save.isPending} onClick={() => submit()} className={buttons.primary}>
            {t("expenses.save")}
          </button>
          <button type="button" disabled={save.isPending} onClick={() => submit(true)} className={buttons.secondary}>
            <Printer className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("print.saveAndPrint")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <label className="flex flex-col gap-1.5">
        <span className="text-label text-text-secondary">{t("expenses.amount")}</span>
        <span className="flex h-11 items-center justify-between rounded-control border border-border-strong bg-bg-surface px-3 focus-within:border-primary">
          <input autoFocus inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-full border-0 bg-transparent p-0 font-sans text-page-title text-text-primary outline-none" />
          <span className="text-body font-medium text-text-secondary">{t("money.currency")}</span>
        </span>
      </label>
      <div className="flex flex-col gap-1.5">
        <span className="text-label text-text-secondary">{t("expenses.category")}</span>
        <div role="radiogroup" className="flex flex-wrap gap-2">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={category === c}
              onClick={() => setCategory(c)}
              className={`inline-flex h-8 items-center rounded-control border px-3 font-sans text-body ${
                category === c ? "border-primary bg-primary-soft font-semibold text-primary" : "border-border-strong bg-bg-surface text-text-primary"
              }`}
            >
              {t(`expenseCategory.${c}`)}
            </button>
          ))}
        </div>
      </div>
      <Field label={t("expenses.note")} required>
        <TextInput value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("expenses.method")}</span>
          <Segmented<Method>
            label={t("expenses.method")}
            value={method}
            onChange={setMethod}
            options={(["cash", "bankak", "transfer"] as const).map((m) => ({ value: m, label: t(`payMethod.${m}`) }))}
          />
        </div>
        <Field label={t("expenses.date")}>
          <TextInput readOnly value={t("expenses.now", { time: formatTime(new Date()) })} />
        </Field>
      </div>
      {method !== "cash" && (
        <Field label={t("expenses.reference")} required>
          <TextInput dir="ltr" value={reference} onChange={(e) => setReference(e.target.value)} />
        </Field>
      )}
      <Field label={<>{t("expenses.room")} <span className="text-text-disabled">{t("expenses.optional")}</span></>}>
        <Select value={room} onChange={(e) => setRoom(e.target.value)}>
          <option value="">{t("expenses.noRoom")}</option>
          {roomGroups(rooms).map((group) => (
            <optgroup key={group.type} label={group.type}>
              {group.rooms.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
      </Field>
      <div className="flex flex-col gap-1.5">
        <span className={`text-label ${needsReceipt ? "text-warning" : "text-text-secondary"}`}>
          {t("expenses.receipt")}{" "}
          <span className="font-normal">{needsReceipt ? t("expenses.receiptRequired", { amount: money(threshold) }) : t("expenses.receiptOptional")}</span>
        </span>
        <label
          className={`flex h-16 cursor-pointer items-center justify-center gap-2 rounded-control border border-dashed text-body ${
            needsReceipt && !file ? "border-warning bg-warning-soft text-warning-text" : "border-border-strong bg-bg-page text-text-secondary"
          }`}
        >
          <ImageUp className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {file ? file.name : t("expenses.receiptPick")}
          <input type="file" accept="image/*,application/pdf" capture="environment" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      </div>
      {method === "cash" && shift && (
        <div className="flex items-center gap-2 rounded-control bg-bg-surface-2 px-3 py-2.5 text-label font-normal text-text-secondary">
          <Info className="h-icon-inline w-icon-inline flex-none" strokeWidth={1.75} aria-hidden />
          {t("expenses.cashNote", { name: shift.opened_by })}
        </div>
      )}
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Drawer>
  );
}

function ReverseModal({ expense, onClose, onDone }: { expense: Expense; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reverse = useMutation({
    mutationFn: () => data(api.POST("/api/v1/expenses/{id}/reverse", { params: { path: { id: expense.id } }, body: { reason: reason.trim() } })),
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  return (
    <Modal
      title={t("expenses.reverseTitle")}
      onClose={onClose}
      width={480}
      footer={
        <>
          <button type="button" disabled={!reason.trim() || reverse.isPending} onClick={() => reverse.mutate()} className={buttons.danger}>
            {t("expenses.reverseConfirm")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="text-body">
        {expense.note} · <span className="font-semibold">{money(expense.amount)}</span>
      </div>
      <div className="text-body text-text-secondary">{t("expenses.reverseText")}</div>
      <Field label={t("expenses.reverseReason")} required>
        <TextInput autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}

