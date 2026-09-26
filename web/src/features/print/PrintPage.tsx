import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { api, data } from "@/api/client";
import { useMe, useSystemStatus } from "@/api/queries";
import { setDigits } from "@/i18n/digits";
import { setMoneyDecimals } from "@/i18n/money";
import { t } from "@/i18n/t";

import "./print.css";

import { ExpenseSlip, PaymentReceipt } from "./Receipts";
import { InvoiceA4, ReportA4, ShiftStatementA4 } from "./Sheets";

type Kind = "invoice" | "receipt" | "expense" | "shift" | "report";

/** Opens a print template in its own window (spec §8); it prints itself once the data is in. */
export function openPrint(kind: Kind, id: string, query?: Record<string, string>) {
  const qs = query && Object.keys(query).length ? `?${new URLSearchParams(query)}` : "";
  window.open(`/print/${kind}/${encodeURIComponent(id)}${qs}`, "_blank", "width=1000,height=1100");
}

/** `/print/:kind/:id` — no shell; black on white; `window.print()` when ready, closes after printing. */
export function PrintPage() {
  const { kind, id = "" } = useParams<{ kind: Kind; id: string }>();
  const [search] = useSearchParams();
  const me = useMe().data;
  const version = useSystemStatus().data?.version ?? "";

  const doc = useQuery({
    queryKey: ["print", kind, id, search.toString()],
    queryFn: async () => {
      const path = { params: { path: { id } } };
      switch (kind) {
        case "invoice":
          return { kind, doc: await data(api.GET("/api/v1/folios/{id}/invoice", path)) } as const;
        case "receipt":
          return { kind, doc: await data(api.GET("/api/v1/payments/{id}/receipt", path)) } as const;
        case "expense":
          return { kind, doc: await data(api.GET("/api/v1/expenses/{id}/receipt", path)) } as const;
        case "shift":
          return { kind, doc: await data(api.GET("/api/v1/shifts/{id}/statement", path)) } as const;
        default: {
          const [report, hotel] = await Promise.all([
            data(api.GET("/api/v1/reports/{name}", { params: { path: { name: id }, query: Object.fromEntries(search) as never } })),
            data(api.GET("/api/v1/system/settings")),
          ]);
          return { kind: "report", doc: report, hotel } as const;
        }
      }
    },
    retry: false,
  });

  const ready = doc.isSuccess && (doc.data.kind !== "report" || !!me);
  useEffect(() => {
    if (!doc.data) return;
    const hotel = doc.data.kind === "report" ? doc.data.hotel : doc.data.doc.hotel;
    setDigits(hotel.digits);
    setMoneyDecimals(hotel.money_decimals);
  }, [doc.data]);
  useEffect(() => {
    if (!ready) return;
    document.title = t("print.windowTitle");
    const close = () => window.opener && window.close();
    window.addEventListener("afterprint", close);
    // Let fonts and layout settle before the print dialog takes the page.
    const timer = window.setTimeout(() => void document.fonts.ready.then(() => window.print()), 300);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("afterprint", close);
    };
  }, [ready]);

  if (doc.isError) return <div className="p-8 text-body">{doc.error instanceof Error ? doc.error.message : t("errors.error")}</div>;
  if (!ready) return <div className="p-8 text-body text-text-secondary">{t("print.preparing")}</div>;
  const d = doc.data;
  return (
    <div className="print-root bg-bg-surface text-text-primary">
      {/* Screen-only toolbar: the page prints itself once, and this reprints it if the dialog was cancelled. */}
      <div className="no-print sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-bg-surface px-4 py-2">
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex h-9 items-center gap-2 rounded-control border-0 bg-primary px-4 font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover"
        >
          {t("print.print")}
        </button>
        <span className="text-label font-normal text-text-secondary">{t("print.previewHint")}</span>
        <div className="flex-1" />
        {window.opener && (
          <button
            type="button"
            onClick={() => window.close()}
            className="inline-flex h-9 items-center rounded-control border border-border-strong bg-bg-surface px-4 font-sans text-body font-medium text-text-primary hover:bg-bg-surface-2"
          >
            {t("common.close")}
          </button>
        )}
      </div>
      {d.kind === "invoice" && <InvoiceA4 doc={d.doc} version={version} />}
      {d.kind === "receipt" && <PaymentReceipt doc={d.doc} version={version} />}
      {d.kind === "expense" && <ExpenseSlip doc={d.doc} />}
      {d.kind === "shift" && <ShiftStatementA4 doc={d.doc} version={version} />}
      {d.kind === "report" && <ReportA4 report={d.doc} hotel={d.hotel} printedBy={me!.full_name} version={version} />}
    </div>
  );
}
