import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Info, Plus, Undo2 } from "lucide-react";
import { useRef, useState } from "react";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { keys, useCurrentShift, useHotelSettings, useSystemStatus } from "@/api/queries";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorBanner, Field, Segmented, Select, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { useRoomBoard } from "@/features/rooms/RoomBoardPage";
import { formatDayMonth, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

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
  const list = useQuery({
    queryKey: ["expenses", scope, category],
    queryFn: () => data(api.GET("/api/v1/expenses/", { params: { query: { scope, ...(category ? { category } : {}) } } })),
  });
  const summary = useQuery({ queryKey: ["expenses", "summary"], queryFn: () => data(api.GET("/api/v1/expenses/summary")) }).data;
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["expenses"] });
    void queryClient.invalidateQueries({ queryKey: keys.currentShift });
  };
  const rows = list.data?.results ?? [];

  return (
    <div className="flex h-full flex-col gap-4 p-6 max-[1599px]:gap-3">
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
        <button type="button" disabled={offline} onClick={() => setCreating(true)} className={`${buttons.primary} h-9 px-4`}>
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

      <ExpenseTable rows={rows} total={list.data?.count ?? 0} offline={offline} onReverse={setReversing} onUploaded={refresh} />

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

function Tile({ label, value, hint, warn = false }: { label: string; value: string; hint?: string; warn?: boolean }) {
  return (
    <div className="rounded-card border border-border bg-bg-surface p-4">
      <div className="text-label text-text-secondary">{label}</div>
      <div className={`mt-1 text-headline-number ${warn ? "text-warning" : ""}`}>{value}</div>
      {hint && <div className="mt-1 text-label font-normal text-text-secondary">{hint}</div>}
    </div>
  );
}

const GRID = "grid grid-cols-[160px_140px_1fr_160px_120px_140px_140px_64px] items-center gap-4 px-4";

function ExpenseTable({
  rows,
  total,
  offline,
  onReverse,
  onUploaded,
}: {
  rows: Expense[];
  total: number;
  offline: boolean;
  onReverse: (e: Expense) => void;
  onUploaded: () => void;
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
      <div className={`${GRID} h-10 flex-none bg-bg-surface-2 text-label text-text-secondary`}>
        {["colDate", "colCategory", "colText", "colAmount", "colMethod", "colAttachment", "colBy"].map((k) => (
          <div key={k}>{t(`expenses.${k}`)}</div>
        ))}
        <div />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("expenses.empty")}</div>}
        {rows.map((e) => {
          const correction = !!e.reverses;
          const muted = e.reversed ? "text-text-disabled line-through" : "";
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
              <div className={`font-semibold ${muted}`}>
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
                  <button type="button" disabled={offline} onClick={() => onReverse(e)} className="border-0 bg-transparent p-0 font-sans text-label font-medium text-danger disabled:text-text-disabled">
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
      <button type="button" disabled={disabled} onClick={() => input.current?.click()} className="border-0 bg-transparent p-0 font-sans text-label font-medium text-warning-text underline">
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
    mutationFn: async () => {
      const created = await data(
        api.POST("/api/v1/expenses/", { body: { category, amount: minor!, note: note.trim(), method, reference: reference.trim(), room: room || null } }),
      );
      if (file) await upload(created.id, file);
    },
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  const submit = () => {
    if (minor === null || minor <= 0) return setError(t("expenses.errAmount"));
    if (!note.trim()) return setError(t("expenses.errNote"));
    if (method !== "cash" && !reference.trim()) return setError(t("expenses.errReference"));
    if (needsReceipt && !file) return setError(t("expenses.errReceipt"));
    setError(null);
    save.mutate();
  };

  return (
    <Drawer
      title={t("expenses.new")}
      onClose={onClose}
      footer={
        <>
          <button type="button" disabled={save.isPending} onClick={submit} className={buttons.primary}>
            {t("expenses.save")}
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
          {rooms.map((r) => (
            <option key={r.id} value={r.id}>
              {digits(r.number)} — {t(`roomState.${r.display_status}`)}
            </option>
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

