import type { ReactNode } from "react";

import type { components } from "@api/schema";

import { formatDayDate, formatDayMonth, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { formatCell } from "@/features/reports/ReportsPage";

type Invoice = components["schemas"]["InvoiceDocument"];
type Statement = components["schemas"]["ShiftStatementDocument"];
type Report = components["schemas"]["Report"];
type Hotel = Pick<components["schemas"]["HotelSettings"], "name_ar" | "name_latin" | "address" | "phone">;

const money = (v: number) => formatMoney(v);
const when = (iso: string) => (
  <>
    {formatDayDate(iso)} · <span dir="ltr">{digits(formatTime(iso))}</span>
  </>
);

/** Hotel header shared by the A4 sheets: monogram, Arabic name, address and phone, Latin name. */
function HotelHeader({ hotel, title, lines }: { hotel: Hotel; title: string; lines: ReactNode[] }) {
  return (
    <header className="flex items-start gap-4 border-b-2 border-text-primary pb-3">
      <div className="flex h-12 w-12 flex-none items-center justify-center rounded-control border-2 border-text-primary text-[12pt] font-bold" dir="ltr">
        {t("print.monogram")}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[16pt] font-bold">{hotel.name_ar}</div>
        <div className="text-[11pt] text-text-secondary">
          {[hotel.address, hotel.phone && <span dir="ltr">{hotel.phone}</span>].filter(Boolean).map((part, i) => (
            <span key={i}>
              {i > 0 && " · "}
              {part}
            </span>
          ))}
        </div>
        {hotel.name_latin && (
          <div dir="ltr" className="text-end text-[11pt] text-text-secondary">
            {hotel.name_latin}
          </div>
        )}
      </div>
      <div className="flex flex-col items-end gap-0.5 text-end">
        <div className="text-[16pt] font-bold">{title}</div>
        {lines.map((line, i) => (
          <div key={i} className="text-[11pt] text-text-secondary">
            {line}
          </div>
        ))}
      </div>
    </header>
  );
}

function Signatures({ left, right }: { left: string; right: string }) {
  return (
    <div className="mt-10 grid grid-cols-2 gap-16">
      {[right, left].map((label) => (
        <div key={label} className="border-t border-text-primary pt-2 text-[11pt] text-text-secondary">
          {label}
        </div>
      ))}
    </div>
  );
}

function Footer({ version, reference }: { version: string; reference: ReactNode }) {
  return (
    <footer className="mt-6 flex justify-between border-t border-border pt-2 text-[10pt] text-text-secondary">
      <span dir="ltr">
        {t("print.product")} v{version}
      </span>
      <span>{reference}</span>
    </footer>
  );
}

/** 7.1 Stay invoice, A4 portrait. */
export function InvoiceA4({ doc, version }: { doc: Invoice; version: string }) {
  const g = doc.guest;
  const s = doc.stay;
  return (
    <article className="sheet-a4">
      <HotelHeader
        hotel={doc.hotel}
        title={t("print.invoiceTitle")}
        lines={[
          <span key="n" dir="ltr" className="text-[12pt] font-semibold text-text-primary">
            {doc.invoice}
          </span>,
          <span key="p">
            {t("print.printedAt")} {when(doc.printed_at)}
          </span>,
        ]}
      />
      <section className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3">
        <Info label={t("print.guest")}>
          <div className="font-semibold">{g.name}</div>
          <div className="text-[11pt] text-text-secondary">
            {g.phone && <span dir="ltr">{digits(g.phone)}</span>}
            {g.id_number && ` · ${g.id_type} ${digits(g.id_number)}`}
          </div>
        </Info>
        <Info label={t("print.roomStay")}>
          <div className="font-semibold">
            {s.room ? t("print.roomN", { room: digits(s.room) }) : t("print.noRoom")} — {s.room_type} · {s.duration_kind}
          </div>
          <div className="text-[11pt] text-text-secondary">
            {t("print.fromTo", { from: formatDayDate(s.check_in_date), to: formatDayDate(s.last_night) })} · {t("print.nights", { n: digits(String(s.nights)) })}
          </div>
        </Info>
        <Info label={t("print.companions")}>{g.companions.length ? g.companions.join("، ") : t("print.none")}</Info>
        <Info label={t("print.stayState")}>{digits(s.state)}</Info>
      </section>

      {/* Artboard 7.1: line items (البيان · الكمية · السعر · الإجمالي), then the payment list; the ledger stays on screen. */}
      <table className="print-table mt-5 text-[12pt]">
        <thead>
          <tr className="border-y-2 border-text-primary text-[11pt]">
            <th className="w-[26mm]">{t("print.colDate")}</th>
            <th>{t("print.colText")}</th>
            <th className="num w-[18mm]">{t("print.colQty")}</th>
            <th className="num w-[28mm]">{t("print.colUnit")}</th>
            <th className="num w-[28mm]">{t("print.colLineTotal")}</th>
          </tr>
        </thead>
        <tbody>
          {doc.items.map((it, i) => (
            <tr key={i} className="border-b border-border">
              <td className="whitespace-nowrap text-[11pt]">{formatDayMonth(it.at)}</td>
              <td>{digits(it.text)}</td>
              <td className="num">{digits(String(it.quantity))}</td>
              <td className="num">{money(it.unit_price)}</td>
              <td className="num font-semibold">{money(it.total)}</td>
            </tr>
          ))}
          {/* Totals as the last body row: a <tfoot> makes Chromium repeat it and push it to a new page. */}
          <tr className="border-t-2 border-text-primary font-semibold">
            <td colSpan={4}>{t("print.total")}</td>
            <td className="num">{money(doc.totals.charges)}</td>
          </tr>
        </tbody>
      </table>

      {doc.payments.length > 0 && (
        <table className="print-table mt-4 text-[11pt]">
          <thead>
            <tr className="border-y border-text-primary">
              <th className="w-[26mm]">{t("print.colDate")}</th>
              <th className="w-[30mm]">{t("print.receiptNo")}</th>
              <th>{t("print.colType")}</th>
              <th>{t("print.colMethod")}</th>
              <th>{t("print.reference")}</th>
              <th className="num w-[28mm]">{t("print.colAmount")}</th>
            </tr>
          </thead>
          <tbody>
            {doc.payments.map((p) => (
              <tr key={p.receipt} className="border-b border-border">
                <td className="whitespace-nowrap">{formatDayMonth(p.at)}</td>
                <td dir="ltr" className="text-end">
                  {p.receipt}
                </td>
                <td>{p.kind}</td>
                <td>{p.method}</td>
                <td dir="ltr" className="text-end text-text-secondary">
                  {p.reference}
                </td>
                <td className="num font-semibold">{money(p.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <section className="mt-5 flex items-start gap-6">
        <ul className="m-0 flex-1 list-none p-0 text-[10pt] text-text-secondary">
          {doc.notes.map((n) => (
            <li key={n}>• {digits(n)}</li>
          ))}
        </ul>
        <div className="w-[70mm] flex-none">
          <Row label={t("print.total")} value={money(doc.totals.charges)} />
          {doc.totals.discount > 0 && <Row label={t("print.discount")} value={`− ${money(doc.totals.discount)}`} />}
          <Row label={t("print.stayTotal")} value={money(doc.totals.total)} />
          <Row label={t("print.paid")} value={money(doc.totals.paid)} />
          <div className="mt-2 flex items-baseline justify-between rounded-control border-2 border-text-primary px-3 py-2">
            <span className="text-[13pt] font-semibold">{doc.totals.balance < 0 ? t("print.refundDue") : t("print.balance")}</span>
            <span className="text-[19pt] font-bold">
              {money(Math.abs(doc.totals.balance))} <span className="text-[11pt] font-normal">{t("money.currency")}</span>
            </span>
          </div>
        </div>
      </section>

      <Signatures right={t("print.signStaff", { name: doc.printed_by })} left={t("print.signGuest")} />
      <Footer version={version} reference={<span dir="ltr">{doc.invoice}</span>} />
    </article>
  );
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-[10pt] text-text-secondary">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-text-secondary">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

/** 7.3 Shift statement, A4: the reference layout for printed reports (header, tiles, table, result box, signatures). */
export function ShiftStatementA4({ doc, version }: { doc: Statement; version: string }) {
  const sh = doc.shift;
  const receipts = doc.tiles.receipts;
  const ref = (
    <>
      {t("print.shiftRef")} <span dir="ltr">{sh.id.slice(0, 8)}</span>
    </>
  );
  return (
    <article className="sheet-a4">
      <HotelHeader
        hotel={doc.hotel}
        title={t("print.statementTitle")}
        lines={[
          <span key="w">
            {formatDayDate(sh.opened_at)} · <span dir="ltr">{digits(formatTime(sh.opened_at))}</span>
            {sh.closed_at && (
              <>
                {" – "}
                <span dir="ltr">{digits(formatTime(sh.closed_at))}</span>
              </>
            )}
          </span>,
          <span key="b">{t("print.employee", { name: sh.opened_by })}</span>,
          <span key="p">
            {t("print.printedBy", { name: doc.printed_by })} · <span dir="ltr">{digits(formatTime(doc.printed_at))}</span>
          </span>,
        ]}
      />
      <section className="mt-4 grid grid-cols-4 gap-3">
        <Tile label={t("print.opening")} value={money(doc.tiles.opening)} />
        <Tile label={t("print.receipts")} value={money(receipts.total)} />
        <Tile label={t("print.cashExpenses")} value={`− ${money(doc.tiles.cash_expenses)}`} />
        <Tile label={t("print.expected")} value={money(doc.tiles.expected)} shaded />
      </section>
      <div className="mt-2 text-[11pt] text-text-secondary">
        {t("payMethod.cash")} {money(receipts.cash)} · {t("payMethod.bankak")} {money(receipts.bankak)} · {t("payMethod.transfer")} {money(receipts.transfer)}
      </div>
      {doc.opening_reason && (
        <div className="mt-1 text-[11pt]">
          {t("print.openingDiffers", { amount: doc.opening_expected === null ? "—" : money(doc.opening_expected), reason: doc.opening_reason })}
        </div>
      )}

      <table className="print-table mt-4 text-[12pt]">
        <thead>
          <tr className="border-y-2 border-text-primary text-[11pt]">
            <th className="w-[18mm]">{t("print.colTime")}</th>
            <th className="w-[20mm]">{t("print.colType")}</th>
            <th>{t("print.colText")}</th>
            <th className="num w-[28mm]">{t("print.colAmount")}</th>
            <th className="w-[20mm]">{t("print.colMethod")}</th>
          </tr>
        </thead>
        <tbody>
          {doc.movements.map((m, i) => (
            <tr key={`${m.ref_id}-${i}`} className="border-b border-border">
              <td dir="ltr" className="text-end text-[11pt]">
                {digits(formatTime(m.at))}
              </td>
              <td>{t(`print.move_${m.kind}`)}</td>
              <td>{digits(m.text)}</td>
              <td className="num" dir="ltr">
                {m.amount < 0 ? "− " : ""}
                {money(Math.abs(m.amount))}
              </td>
              <td>{m.method ? t(`payMethod.${m.method}`) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Dollars and other currencies of the drawer, each in its own units (review 2026-09-29, A-9, D-1). */}
      {doc.currencies.length > 0 && (
        <table className="print-table mt-4 text-[12pt]">
          <thead>
            <tr className="border-y-2 border-text-primary text-[11pt]">
              <th>{t("print.colCurrency")}</th>
              <th className="num">{t("print.opening")}</th>
              <th className="num">{t("print.colReceived")}</th>
              <th className="num">{t("print.expected")}</th>
              <th className="num">{t("print.counted")}</th>
              <th className="num">{t("print.difference")}</th>
              <th className="num">{t("print.handedOver")}</th>
            </tr>
          </thead>
          <tbody>
            {doc.currencies.map((c) => {
              const cur = (v: number | null) => (v === null ? "—" : `${v < 0 ? "− " : ""}${money(Math.abs(v))} ${c.symbol}`);
              return (
                <tr key={c.currency} className="border-b border-border">
                  <td>{c.currency}</td>
                  <td className="num" dir="ltr">{cur(c.opening)}</td>
                  <td className="num" dir="ltr">{cur(c.received)}</td>
                  <td className="num" dir="ltr">{cur(c.expected)}</td>
                  <td className="num" dir="ltr">{cur(c.counted)}</td>
                  <td className="num font-semibold" dir="ltr">{cur(c.difference)}</td>
                  <td className="num" dir="ltr">{cur(c.handed_over)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <section className="mt-5 flex items-start gap-6">
        <div className="flex-1 whitespace-pre-line text-[10pt] text-text-secondary">{doc.formula}</div>
        <div className="w-[80mm] flex-none rounded-control border-2 border-text-primary p-3">
          <Row label={t("print.expected")} value={money(doc.tiles.expected)} />
          <Row label={t("print.counted")} value={doc.counted === null ? "—" : money(doc.counted)} />
          <div className="mt-1 flex items-baseline justify-between border-t border-text-primary pt-1">
            <span className="font-semibold">{t("print.difference")}</span>
            <span className="text-[18pt] font-bold" dir="ltr">
              {doc.difference === null ? "—" : `${doc.difference < 0 ? "− " : ""}${money(Math.abs(doc.difference))}`}
            </span>
          </div>
          {doc.difference_reason && <div className="mt-1 text-[11pt]">{t("print.reason", { reason: doc.difference_reason })}</div>}
          {doc.handed_over > 0 && (
            <div className="mt-1 border-t border-border pt-1">
              <Row label={t("print.handedOver")} value={money(doc.handed_over)} />
              <Row label={t("print.leftInDrawer")} value={doc.left_in_drawer === null ? "—" : money(doc.left_in_drawer)} />
            </div>
          )}
        </div>
      </section>

      <Signatures right={t("print.signHandover", { name: sh.closed_by || sh.opened_by })} left={t("print.signReceiver")} />
      <Footer version={version} reference={ref} />
    </article>
  );
}

function Tile({ label, value, shaded = false }: { label: string; value: string; shaded?: boolean }) {
  return (
    <div className={`rounded-control border border-text-primary p-2 ${shaded ? "bg-bg-surface-2" : ""}`}>
      <div className="text-[10pt] text-text-secondary">{label}</div>
      <div className="text-[15pt] font-bold" dir="ltr">
        <span className="block text-end">{value}</span>
      </div>
    </div>
  );
}

type Meta = {
  title?: string;
  as_of?: string;
  date_from?: string | null;
  date_to?: string | null;
  formula?: string;
  note?: string;
  totals?: Record<string, number>;
  filters?: { key: string; label: string; value: string }[];
};

/** Any report as A4 landscape (Gap Fill 7.3): title, hotel, period, as-of, table with totals, formula, page numbers. */
export function ReportA4({ report, hotel, printedBy, version }: { report: Report; hotel: Hotel; printedBy: string; version: string }) {
  const meta = report.meta as Meta;
  const numeric = (type: string) => type === "money" || type === "int" || type === "percent";
  const period =
    meta.date_from && meta.date_to ? t("print.period", { from: formatDayDate(meta.date_from), to: formatDayDate(meta.date_to) }) : null;
  return (
    <article className="sheet-a4-landscape">
      <HotelHeader
        hotel={hotel}
        title={meta.title ?? report.name}
        lines={[
          period,
          // The filters the report applied (brief §7: «filter summary line»), from the server's meta.
          meta.filters?.length ? <span key="f">{t("print.filters", { list: meta.filters.map((f) => `${f.label}: ${f.value}`).join(" · ") })}</span> : null,
          meta.as_of && (
            <span key="a">
              {t("print.asOf")} {when(meta.as_of)}
            </span>
          ),
          <span key="p">
            {t("print.printedBy", { name: printedBy })} · <span dir="ltr">{digits(formatTime(new Date()))}</span>
          </span>,
        ].filter(Boolean)}
      />
      <table className="print-table mt-4 text-[12pt]">
        <thead>
          <tr className="border-y-2 border-text-primary text-[11pt]">
            {report.columns.map((c) => (
              <th key={c.key} className={numeric(c.type) ? "num" : ""}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {report.rows.map((row, i) => (
            <tr key={i} className="border-b border-border">
              {report.columns.map((c) => (
                <td key={c.key} className={numeric(c.type) ? "num" : ""}>
                  {formatCell((row as Record<string, unknown>)[c.key], c.type)}
                </td>
              ))}
            </tr>
          ))}
          {meta.totals && (
            <tr className="border-t-2 border-text-primary font-semibold">
              {report.columns.map((c, i) => (
                <td key={c.key} className={numeric(c.type) ? "num" : ""}>
                  {i === 0 ? t("print.totalRows", { n: digits(String(report.rows.length)) }) : c.key in meta.totals! ? formatCell(meta.totals![c.key], c.type) : ""}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
      {(meta.formula || meta.note) && <div className="mt-4 text-[10pt] text-text-secondary">{digits(meta.formula ?? meta.note ?? "")}</div>}
      <Footer version={version} reference={meta.title ?? report.name} />
    </article>
  );
}
