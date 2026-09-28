import { CalendarPlus, ChevronRight, DoorOpen, HandCoins, LogOut, Plus, Printer, Undo2, Users, Wallet } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import type { components } from "@api/schema";

import { useSystemStatus } from "@/api/queries";
import { buttons } from "@/components/ui/Modal";
import { Tabs } from "@/components/ui/Tabs";
import { stateColor } from "@/design/state";
import { openPrint } from "@/features/print/PrintPage";
import { days, nights } from "@/i18n/counts";
import { formatDayDate, formatDayMonth, formatRange, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { CancelStayModal } from "./CancelStayModal";
import { ChangeRoomModal } from "./ChangeRoomModal";
import { CheckoutModal } from "./CheckoutModal";
import { ExtendModal } from "./ExtendModal";
import { RefundModal, ReverseModal } from "./FolioActionModals";
import { PaymentModal } from "./PaymentModal";
import { useFolio, useRefreshStay, useStay } from "./queries";

type Entry = components["schemas"]["LedgerEntry"];
type Ledger = Entry[];
type Tab = "invoice" | "payments" | "companions" | "notes" | "log";
type Dialog = null | "payment" | "checkout" | "extend" | "changeRoom" | "cancel" | "refund";

const money = (v: number) => formatMoney(v);
const when = (iso: string) => (
  <>
    {formatDayMonth(iso)} · <span dir="ltr">{formatTime(iso)}</span>
  </>
);

/** 6.5 Stay detail: header card with the balance, actions, and the invoice / payments / companions / notes / log tabs. */
export function StayDetailPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const stayQuery = useStay(id);
  const stay = stayQuery.data;
  const folioQuery = useFolio(stay?.reservation.folio);
  const folio = folioQuery.data;
  const offline = useSystemStatus().isError;
  const refresh = useRefreshStay(id, stay?.reservation.folio);
  const [tab, setTab] = useState<Tab>("invoice");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [reversing, setReversing] = useState<Entry | null>(null);

  // Opened from the room drawer with ?action=extend|checkout.
  useEffect(() => {
    const action = params.get("action");
    if (stay && folio && (action === "extend" || action === "checkout")) {
      setDialog(action);
      setParams({}, { replace: true });
    }
  }, [params, setParams, stay, folio]);

  if (stayQuery.isError) return <div className="p-6 text-text-secondary">{t("stay.notFound")}</div>;
  if (!stay || !folio) return <StaySkeleton />;

  const r = stay.reservation;
  const open = stay.checked_out_at === null;
  const room = stay.room;
  const color = stateColor(room?.display_status ?? "occupied");
  const totals = folio.totals;
  const writable = open && !offline;
  const ledger = folio.ledger;
  const payments = ledger.filter((e) => e.type === "payment");
  const done = () => {
    setDialog(null);
    setReversing(null);
    refresh();
  };
  // Entries that already have a counter-entry: «معكوس», no second reversal.
  const reversed = new Set(ledger.map((e) => e.reverses).filter(Boolean));
  const onReverse = writable ? setReversing : undefined;

  const d = stay.days_left;
  const endsText =
    d === null ? t("stay.closed") : d < 0 ? t("stay.overdueBy", { days: days(-d) }) : d === 0 ? t("stay.endsToday") : d === 1 ? t("stay.endsTomorrow") : t("stay.endsIn", { days: days(d) });

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "invoice", label: t("stay.tabInvoice") },
    { key: "payments", label: t("stay.tabPayments"), count: payments.length },
    { key: "companions", label: t("stay.tabCompanions"), count: stay.guest.companions.length || undefined },
    { key: "notes", label: t("stay.tabNotes") },
    { key: "log", label: t("stay.tabLog"), count: stay.log.length },
  ];

  return (
    <div className="flex h-full min-h-[620px] flex-col gap-4 p-6">
      <div className="flex h-9 items-center gap-3">
        <Link to="/" className="inline-flex items-center gap-1 text-body text-text-secondary">
          <ChevronRight className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
          {t("stay.back")}
        </Link>
        <h1 className="m-0 text-page-title">{t("stay.title")}</h1>
        <span dir="ltr" className="text-body text-text-secondary">
          {folio.invoice}
        </span>
      </div>

      <section className="flex items-center gap-6 rounded-card border border-border bg-bg-surface px-6 py-4">
        <div className="flex items-center gap-4 border-e border-border pe-6">
          <div className={`h-16 w-1.5 rounded-full ${color.solid}`} />
          <div>
            <div className="text-headline-number">{digits(room?.number ?? r.room_number)}</div>
            <div className="text-body text-text-secondary">
              {t("stay.typeFloor", { type: r.room_type_name, floor: digits(String(room?.floor ?? "")) })}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-center gap-3">
            <span className="text-section-title">{stay.guest.full_name}</span>
            <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${color.soft} ${color.text}`}>
              {t(`roomState.${room?.display_status ?? "occupied"}`)}
            </span>
            <span className="inline-flex h-6 items-center rounded-control bg-bg-surface-2 px-2 text-label text-text-primary">{t(`duration.${r.duration_kind}`)}</span>
          </div>
          <div className="text-body text-text-secondary">
            {[
              stay.guest.phone && <span key="p" dir="ltr">{stay.guest.phone}</span>,
              stay.guest.nationality,
              stay.guest.id_type_label && (
                <span key="i">
                  {stay.guest.id_type_label} <span dir="ltr">{stay.guest.id_number}</span>
                </span>
              ),
            ]
              .filter(Boolean)
              .flatMap((x, i) => (i ? [" · ", x] : [x]))}
          </div>
          <div className="text-body">
            {t("stay.range", { range: formatRange(r.check_in_date, stay.last_night), nights: nights(r.nights), kind: t(`duration.${r.duration_kind}`) })} ·{" "}
            <span className={`font-medium ${d !== null && d < 0 ? "text-danger" : ""}`}>{endsText}</span>{" "}
            {open && t("stay.endsOnDay", { date: formatDayDate(stay.last_night) })}
          </div>
        </div>
        <div className="border-s border-border ps-6 text-end">
          <div className="text-label text-text-secondary">{t("stay.remaining")}</div>
          <div className={`whitespace-nowrap text-headline-number ${totals.balance > 0 ? "text-danger" : totals.balance === 0 ? "text-success" : "text-info"}`}>
            {money(totals.balance)} <span className="text-[16px] font-semibold">{t("money.currency")}</span>
          </div>
          <div className="text-label font-normal text-text-secondary">
            {totals.balance === 0
              ? t("stay.paidInFull", { total: money(totals.total) })
              : t("stay.ofTotal", { total: money(totals.total), paid: money(totals.paid) })}
          </div>
        </div>
      </section>

      <div className="flex items-center gap-2">
        <button type="button" disabled={!writable} onClick={() => setDialog("payment")} className={buttons.primary}>
          <Wallet className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("stay.addPayment")}
        </button>
        <button type="button" disabled={!writable} onClick={() => setDialog("extend")} className={buttons.secondary}>
          <CalendarPlus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("stay.extend")}
        </button>
        <button type="button" disabled={!writable} onClick={() => setDialog("changeRoom")} className={buttons.secondary}>
          <DoorOpen className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("stay.changeRoom")}
        </button>
        <button type="button" disabled={!writable} onClick={() => setDialog("checkout")} className={buttons.secondary}>
          <LogOut className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("stay.checkout")}
        </button>
        {totals.balance < 0 && (
          <button type="button" disabled={offline} onClick={() => setDialog("refund")} className={buttons.secondary}>
            <HandCoins className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("folioAction.refund")}
          </button>
        )}
        <div className="flex-1" />
        {offline ? (
          <span className="text-body text-text-secondary">{t("stay.viewOnly")}</span>
        ) : (
          <button type="button" disabled={!writable} onClick={() => setDialog("cancel")} className={buttons.dangerGhost}>
            {t("stay.cancelStay")}
          </button>
        )}
      </div>

      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
        <Tabs
          items={tabs}
          value={tab}
          onChange={setTab}
          end={
            <button type="button" onClick={() => openPrint("invoice", folio.id)} className={`${buttons.secondary} h-9 px-3`}>
              <Printer className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
              {t("print.printInvoice")}
            </button>
          }
        />
        {tab === "invoice" && <InvoiceTab ledger={ledger} balance={totals.balance} reversed={reversed} onReverse={onReverse} />}
        {tab === "payments" && <PaymentsTab ledger={payments} reversed={reversed} onReverse={onReverse} />}
        {tab === "companions" && <CompanionsTab companions={stay.guest.companions} />}
        {tab === "notes" && (
          <NotesTab
            items={[
              r.notes && [t("stay.reservationNotes"), r.notes],
              stay.guest.warning_note && [t("stay.guestWarning"), stay.guest.warning_note],
              stay.override_reason && [t("stay.overrideNote", { by: stay.override_by_name ?? "", reason: stay.override_reason }), ""],
            ].filter(Boolean) as [string, string][]}
          />
        )}
        {tab === "log" && <LogTab log={stay.log} />}
      </section>

      {dialog === "payment" && (
        <PaymentModal folioId={folio.id} room={folio.room_number} balance={totals.balance} onClose={() => setDialog(null)} onDone={done} />
      )}
      {dialog === "refund" && (
        <RefundModal folioId={folio.id} room={folio.room_number} credit={-totals.balance} onClose={() => setDialog(null)} onDone={done} />
      )}
      {reversing && <ReverseModal folioId={folio.id} entry={reversing} onClose={() => setReversing(null)} onDone={done} />}
      {dialog === "checkout" && (
        <CheckoutModal
          stayId={stay.id}
          version={stay.version}
          room={folio.room_number}
          totals={totals}
          onClose={() => setDialog(null)}
          onPay={() => setDialog("payment")}
          onDone={done}
        />
      )}
      {dialog === "changeRoom" && (
        <ChangeRoomModal
          stayId={stay.id}
          version={stay.version}
          guest={stay.guest.full_name}
          room={{ number: folio.room_number, floor: room?.floor ?? 0, type: r.room_type_name }}
          lastNight={stay.last_night}
          onClose={() => setDialog(null)}
          onDone={done}
        />
      )}
      {dialog === "cancel" && (
        <CancelStayModal
          stayId={stay.id}
          version={stay.version}
          room={folio.room_number}
          guest={stay.guest.full_name}
          kind={t(`duration.${r.duration_kind}`)}
          checkIn={r.check_in_date}
          totalNights={r.nights}
          paid={totals.paid}
          total={totals.total}
          onClose={() => setDialog(null)}
          onDone={done}
        />
      )}
      {dialog === "extend" && (
        <ExtendModal
          stayId={stay.id}
          version={stay.version}
          room={folio.room_number}
          roomType={r.room_type_name}
          kind={r.duration_kind === "mixed" ? "daily" : r.duration_kind}
          currentLastNight={stay.last_night}
          total={totals.total}
          balance={totals.balance}
          onClose={() => setDialog(null)}
          onDone={(thenPay) => {
            refresh();
            setDialog(thenPay ? "payment" : null);
          }}
        />
      )}
    </div>
  );
}

// The text keeps at least 160 px on a 1100 px window; amount columns fit «100,000,000».
const GRID = "grid grid-cols-[150px_minmax(160px,1fr)_120px_120px_130px_130px_64px] items-center gap-3 px-4";

/** Ledger: reversal rows in danger with ↩ and a link to the original entry; nothing is edited or deleted. */
type ReverseProps = { reversed: Set<string | null>; onReverse?: (e: Entry) => void };

/** «عكس» on an entry that is neither a reversal nor already reversed; «معكوس» once it is. */
function ReverseCell({ entry, reversed, onReverse }: ReverseProps & { entry: Entry }) {
  if (entry.reverses) return <div />;
  if (reversed.has(entry.id)) return <div className="text-label text-text-disabled">{t("folioAction.reversed")}</div>;
  if (!onReverse) return <div />;
  return (
    <div>
      <button
        type="button"
        onClick={() => onReverse(entry)}
        className="h-9 rounded-control border-0 bg-transparent px-2 font-sans text-label font-medium text-danger hover:bg-danger-soft"
      >
        {t("folioAction.reverse")}
      </button>
    </div>
  );
}

function InvoiceTab({ ledger, balance, reversed, onReverse }: { ledger: Ledger; balance: number } & ReverseProps) {
  const index = new Map(ledger.map((e, i) => [e.id, i + 1]));
  const debit = ledger.reduce((s, e) => s + e.debit, 0);
  const credit = ledger.reduce((s, e) => s + e.credit, 0);
  return (
    <>
      <div className={`${GRID} h-10 flex-none border-b border-border bg-bg-surface-2 text-label text-text-secondary`}>
        <div>{t("stay.colDate")}</div>
        <div>{t("stay.colText")}</div>
        <div className="text-end">{t("stay.colDebit")}</div>
        <div className="text-end">{t("stay.colCredit")}</div>
        <div className="text-end">{t("stay.colBalance")}</div>
        <div>{t("stay.colBy")}</div>
        <div />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {ledger.map((e) => {
          const reversal = !!e.reverses;
          return (
            <div
              key={`${e.type}-${e.id}`}
              id={`entry-${e.id}`}
              className={`${GRID} h-10 scroll-mt-12 border-b border-border text-table-cell ${reversal ? "bg-danger-soft text-danger-text" : "hover:bg-bg-page"}`}
            >
              <div className="text-label font-normal text-text-secondary">{when(e.at)}</div>
              <div className="flex min-w-0 items-center gap-2">
                {reversal && <Undo2 className="h-icon-inline w-icon-inline flex-none text-danger" strokeWidth={1.75} aria-hidden />}
                <span className="truncate">{e.text}</span>
                {reversal && index.has(e.reverses!) && (
                  <button
                    type="button"
                    onClick={() => document.getElementById(`entry-${e.reverses}`)?.scrollIntoView({ block: "center" })}
                    className="whitespace-nowrap border-0 bg-transparent p-0 font-sans text-label font-medium text-primary underline-offset-2 hover:underline"
                  >
                    {t("stay.entryLink", { n: digits(String(index.get(e.reverses!))) })}
                  </button>
                )}
                {e.reference && (
                  <span dir="ltr" className="flex-none whitespace-nowrap text-label font-normal text-text-secondary">
                    {e.reference}
                  </span>
                )}
              </div>
              <div className={`text-end ${e.debit ? "font-semibold" : ""}`}>{e.debit ? money(e.debit) : "—"}</div>
              <div className={`text-end ${e.credit ? "font-semibold" : ""}`}>{e.credit ? money(e.credit) : "—"}</div>
              <div className="text-end font-semibold">{money(e.balance)}</div>
              <div className="text-text-secondary">{e.by}</div>
              <ReverseCell entry={e} reversed={reversed} onReverse={onReverse} />
            </div>
          );
        })}
      </div>
      <div className={`${GRID} h-11 flex-none border-t border-border bg-bg-surface text-body`}>
        <div />
        <div className="font-semibold">{t("stay.total")}</div>
        <div className="text-end font-semibold">{money(debit)}</div>
        <div className="text-end font-semibold">{money(credit)}</div>
        <div className={`text-end font-bold ${balance > 0 ? "text-danger" : ""}`}>
          {money(balance)} {t("money.currency")}
        </div>
        <div className="text-label font-normal text-text-secondary">
          {ledger.length === 1 ? t("count.entries1") : t("count.entries", { n: digits(String(ledger.length)) })}
        </div>
        <div />
      </div>
    </>
  );
}

const PAY_GRID = "grid grid-cols-[150px_minmax(160px,1fr)_130px_130px_130px_110px_64px] items-center gap-3 px-4";

function PaymentsTab({ ledger, reversed, onReverse }: { ledger: Ledger } & ReverseProps) {
  if (!ledger.length) return <Empty icon={<Wallet className="h-10 w-10 text-text-disabled" strokeWidth={1.75} aria-hidden />} text={t("stay.noPayments")} />;
  return (
    <>
      <div className={`${PAY_GRID} h-10 flex-none border-b border-border bg-bg-surface-2 text-label text-text-secondary`}>
        <div>{t("stay.colDate")}</div>
        <div>{t("stay.colText")}</div>
        <div className="text-end">{t("stay.colAmount")}</div>
        <div>{t("stay.colReference")}</div>
        <div>{t("stay.colBy")}</div>
        <div />
        <div />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {ledger.map((e, i) => (
          <div key={e.id} className={`${PAY_GRID} h-10 border-b border-border text-table-cell ${e.reverses ? "text-danger-text" : ""} ${i % 2 ? "bg-bg-surface-2" : ""}`}>
            <div className="text-label font-normal text-text-secondary">{when(e.at)}</div>
            <div className="truncate">{e.text}</div>
            <div className="text-end font-semibold">
              {money(e.credit || e.debit)} {t("money.currency")}
            </div>
            <div dir="ltr" className="text-end text-text-secondary">
              {e.reference}
            </div>
            <div className="text-text-secondary">{e.by}</div>
            <div>
              <button
                type="button"
                onClick={() => openPrint("receipt", e.id)}
                className="inline-flex h-9 items-center gap-1 rounded-control border-0 bg-transparent px-2 font-sans text-label font-medium text-primary hover:bg-bg-surface-2 hover:text-primary-hover"
              >
                <Printer className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
                {t("print.printReceipt")}
              </button>
            </div>
            <ReverseCell entry={e} reversed={reversed} onReverse={onReverse} />
          </div>
        ))}
      </div>
    </>
  );
}

function CompanionsTab({ companions }: { companions: { [k: string]: string }[] }) {
  if (!companions.length)
    return (
      <Empty
        icon={<Users className="h-10 w-10 text-text-disabled" strokeWidth={1.75} aria-hidden />}
        text={t("stay.noCompanions")}
        action={
          <Link to="/guests" className={`${buttons.secondary} h-9 hover:text-text-primary`}>
            <Plus className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
            {t("stay.addCompanion")}
          </Link>
        }
      />
    );
  return (
    <div className="flex flex-col">
      {companions.map((c, i) => (
        <div key={i} className="flex h-10 items-center gap-4 border-b border-border px-4 text-table-cell">
          <span className="font-medium">{c.name}</span>
          <span className="text-text-secondary">{c.relation}</span>
        </div>
      ))}
    </div>
  );
}

function NotesTab({ items }: { items: [string, string][] }) {
  if (!items.length) return <Empty text={t("stay.noNotes")} />;
  return (
    <div className="flex flex-col gap-4 p-4">
      {items.map(([title, text]) => (
        <div key={title}>
          <div className="text-label text-text-secondary">{title}</div>
          {text && <div className="text-body">{text}</div>}
        </div>
      ))}
    </div>
  );
}

function LogTab({ log }: { log: components["schemas"]["StayLogEntry"][] }) {
  if (!log.length) return <Empty text={t("stay.noLog")} />;
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      {log.map((e, i) => (
        <div key={i} className="grid h-10 grid-cols-[180px_1fr_160px] items-center gap-4 border-b border-border px-4 text-table-cell">
          <div className="text-label font-normal text-text-secondary">{when(e.at)}</div>
          <div>{e.label}</div>
          <div className="text-text-secondary">{e.by ?? ""}</div>
        </div>
      ))}
    </div>
  );
}

function Empty({ icon, text, action }: { icon?: ReactNode; text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      {icon}
      <div className="text-body text-text-secondary">{text}</div>
      {action}
    </div>
  );
}

/** 6.5 E: loading skeleton. */
function StaySkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="h-9 w-72 rounded bg-bg-surface-2" />
      <div className="flex h-24 items-center gap-6 rounded-card border border-border bg-bg-surface px-6">
        <div className="skeleton h-16 w-24 rounded" />
        <div className="flex flex-1 flex-col gap-2">
          <div className="skeleton h-4 w-64 rounded" />
          <div className="h-3 w-96 rounded bg-bg-surface-2" />
        </div>
        <div className="skeleton h-10 w-40 rounded" />
      </div>
      <div className="flex gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-11 w-36 rounded-control bg-bg-surface-2" />
        ))}
      </div>
      <div className="flex flex-1 flex-col gap-2 rounded-card border border-border bg-bg-surface p-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="skeleton h-6 w-full rounded" />
        ))}
      </div>
    </div>
  );
}
