import type { ReactNode } from "react";

import type { components } from "@api/schema";

import { formatDayMonth, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Payment = components["schemas"]["PaymentReceiptDocument"];
type Expense = components["schemas"]["ExpenseReceiptDocument"];
type Hotel = Payment["hotel"];

/** 7.2 thermal slips (80 mm): 12pt text, bold figures, dotted rules, amount in words, 24 px before the cut. */
function SlipHeader({ hotel, title, number, at }: { hotel: Hotel; title: string; number: string; at: string }) {
  return (
    <>
      <div className="text-center">
        <div className="text-[14pt] font-bold">{hotel.name_ar}</div>
        {hotel.address && <div className="text-[11pt]">{hotel.address}</div>}
        {hotel.phone && (
          <div dir="ltr" className="text-[11pt]">
            {hotel.phone}
          </div>
        )}
      </div>
      <div className="rule-dotted my-2" />
      <div className="text-center text-[14pt] font-bold">{title}</div>
      <Line label={t("print.number")} value={<span dir="ltr">{number}</span>} />
      <Line
        label={t("print.date")}
        value={
          <>
            {formatDayMonth(at)} · <span dir="ltr">{digits(formatTime(at))}</span>
          </>
        }
      />
    </>
  );
}

function Line({ label, value, strong = false }: { label: string; value: ReactNode; strong?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-2 ${strong ? "text-[16pt] font-bold" : "text-[12pt]"}`}>
      <span className={strong ? "" : "text-text-secondary"}>{label}</span>
      <span className="text-end font-semibold">{value}</span>
    </div>
  );
}

export function PaymentReceipt({ doc, version }: { doc: Payment; version: string }) {
  return (
    <article className="sheet-thermal">
      <SlipHeader hotel={doc.hotel} title={t("print.receiptTitle", { kind: doc.kind })} number={doc.receipt} at={doc.at} />
      {doc.room && <Line label={t("print.room")} value={digits(doc.room)} />}
      <Line label={t("print.guest")} value={doc.guest} />
      <Line label={t("print.invoice")} value={<span dir="ltr">{doc.invoice}</span>} />
      <Line label={t("print.periodLabel")} value={`${formatDayMonth(doc.check_in_date)} – ${formatDayMonth(doc.last_night)} · ${t("print.nights", { n: digits(String(doc.nights)) })}`} />
      <div className="rule-dotted my-2" />
      <Line label={t("print.amountPaid")} value={formatMoney(doc.amount)} strong />
      {doc.paid_in && <Line label={t("print.paidIn")} value={doc.paid_in} />}
      <Line label={t("print.method")} value={doc.method} />
      {doc.reference && <Line label={t("print.reference")} value={<span dir="ltr">{doc.reference}</span>} />}
      <div className="text-[11pt]">
        <span className="text-text-secondary">{t("print.inWords")} </span>
        {doc.amount_in_words}
      </div>
      <div className="rule-dotted my-2" />
      <Line label={t("print.stayTotal")} value={formatMoney(doc.stay_total)} />
      <Line label={t("print.paidToDate")} value={formatMoney(doc.paid_to_date)} />
      <Line label={t("print.balance")} value={formatMoney(doc.balance)} strong />
      <div className="rule-dotted my-2" />
      <Line label={t("print.staff")} value={doc.by} />
      <Line label={t("print.shift")} value={digits(doc.shift)} />
      <div className="mt-3 text-center text-[11pt]">{t("print.thanks")}</div>
      <div dir="ltr" className="text-center text-[10pt] text-text-secondary">
        {doc.receipt} · v{version}
      </div>
    </article>
  );
}

export function ExpenseSlip({ doc }: { doc: Expense }) {
  return (
    <article className="sheet-thermal">
      <SlipHeader hotel={doc.hotel} title={t("print.expenseTitle")} number={doc.number} at={doc.at} />
      <Line label={t("print.category")} value={doc.category} />
      <div className="text-[12pt]">
        {doc.note}
        {doc.room && ` — ${t("print.roomN", { room: digits(doc.room) })}`}
      </div>
      <div className="rule-dotted my-2" />
      <Line label={t("print.amount")} value={formatMoney(doc.amount)} strong />
      <Line label={t("print.method")} value={doc.method} />
      <div className="text-[11pt]">
        <span className="text-text-secondary">{t("print.inWords")} </span>
        {doc.amount_in_words}
      </div>
      <div className="rule-dotted my-2" />
      <Line label={t("print.recordedBy")} value={doc.by} />
      <div className="mt-8 border-t border-text-primary pt-1 text-center text-[11pt] text-text-secondary">{t("print.receiverSign")}</div>
    </article>
  );
}
