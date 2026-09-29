import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ChevronDown, CircleAlert, KeyRound, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { nights } from "@/i18n/counts";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Totals = { total: number; paid: number; balance: number };
type Props = { stayId: string; version: number; room: string; totals: Totals; onClose: () => void; onPay: () => void; onDone: () => void };

const money = (v: number) => `${formatMoney(v)} ${t("money.currency")}`;

type Method = "cash" | "bankak" | "transfer";

/** 6.5 B/C: check-out; a non-zero balance blocks it unless a manager overrides with password + reason.
 *  Leaving before the booked day: the nights used at the price paid, the rest refunded (owner decision 4). */
export function CheckoutModal({ stayId, version, room, totals: booked, onClose, onPay, onDone }: Props) {
  const quote = useQuery({
    queryKey: ["stays", stayId, "checkout-quote"],
    queryFn: () => data(api.GET("/api/v1/stays/{id}/checkout", { params: { path: { id: stayId } } })),
  });
  const early = quote.data?.early_departure ?? null;
  const totals: Totals = early
    ? { total: early.new_room_charges + early.services, paid: early.paid - early.refund, balance: early.balance_after }
    : booked;
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [after, setAfter] = useState<"cleaning" | "maintenance">("cleaning");
  const [maintenanceReason, setMaintenanceReason] = useState("");
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const owes = totals.balance !== 0;
  const overrideReady = open && !!password && !!reason.trim();
  const needsReference = !!early && early.refund > 0 && method !== "cash" && !reference.trim();
  const canSubmit =
    (!owes || overrideReady) && (after === "cleaning" || !!maintenanceReason.trim()) && !needsReference && !quote.isPending && !busy;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await data(
        api.POST("/api/v1/stays/{id}/checkout", {
          params: { path: { id: stayId } },
          body: {
            version,
            room_status: after,
            maintenance_reason: maintenanceReason.trim(),
            override_password: owes ? password : "",
            override_reason: owes ? reason.trim() : "",
            refund_method: method,
            refund_reference: reference.trim(),
          },
        }),
      );
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("checkout.title", { room: digits(room) })}
      onClose={onClose}
      footer={
        <>
          {owes && overrideReady ? (
            <button type="button" disabled={!canSubmit} onClick={() => void submit()} className={buttons.danger}>
              {t("checkout.submitDebt")}
            </button>
          ) : (
            <button type="button" disabled={!canSubmit} onClick={() => void submit()} className={owes ? buttons.primary : buttons.primary}>
              {t("checkout.submit")}
            </button>
          )}
          {totals.balance > 0 && !open && (
            <button type="button" onClick={onPay} className={buttons.primary}>
              {t("checkout.payRemaining", { amount: money(totals.balance) })}
            </button>
          )}
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      {early && !open && (
        <div className="flex flex-col gap-3 rounded-card bg-info-soft px-4 py-3 text-info-text">
          <div className="flex gap-3">
            <CalendarClock className="mt-0.5 h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
            <div className="flex-1">
              <div className="text-body font-semibold">
                {t("checkout.earlyTitle", { used: nights(early.nights_used), booked: nights(early.nights_booked) })}
              </div>
              <div className="text-body">{t("checkout.earlyText", { from: money(early.room_charges), to: money(early.new_room_charges) })}</div>
            </div>
            {early.refund > 0 && (
              <div className="text-end">
                <div className="text-label">{t("checkout.refund")}</div>
                <div className="text-section-title">{money(early.refund)}</div>
              </div>
            )}
          </div>
          {early.refund > 0 && (
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-label">{t("cancelStay.refundMethod")}</span>
                <Segmented
                  label={t("cancelStay.refundMethod")}
                  value={method}
                  onChange={setMethod}
                  options={(["cash", "bankak", "transfer"] as const).map((m) => ({ value: m, label: t(`payMethod.${m}`) }))}
                />
              </div>
              {method !== "cash" && (
                <Field label={t("payment.reference")} required className="w-48">
                  <TextInput dir="ltr" value={reference} placeholder={t("payment.referenceHint")} onChange={(e) => setReference(e.target.value)} />
                </Field>
              )}
            </div>
          )}
        </div>
      )}

      {!open && (
        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="text-label text-text-secondary">{t("checkout.total")}</div>
            <div className="text-section-title">{money(totals.total)}</div>
          </div>
          <div>
            <div className="text-label text-text-secondary">{t("checkout.paid")}</div>
            <div className="text-section-title">{money(totals.paid)}</div>
          </div>
          <div>
            <div className="text-label text-text-secondary">{t("checkout.remaining")}</div>
            <div className={`text-headline-number ${totals.balance > 0 ? "text-danger" : "text-success"}`}>{money(totals.balance)}</div>
          </div>
        </div>
      )}

      {owes && (
        <div className="flex gap-3 rounded-card bg-danger-soft px-4 py-3 text-danger-text">
          <CircleAlert className="mt-0.5 h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          <div className="flex-1">
            <div className="text-body font-semibold">{totals.balance > 0 ? t("checkout.debtTitle") : t("checkout.creditTitle")}</div>
            {!open && <div className="text-body">{totals.balance > 0 ? t("checkout.debtText") : t("checkout.creditText")}</div>}
          </div>
          {open && <div className="text-section-title">{money(Math.abs(totals.balance))}</div>}
        </div>
      )}

      {!open && (
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("checkout.roomAfter")}</span>
          <div className="w-fit">
            <Segmented
              label={t("checkout.roomAfter")}
              value={after}
              onChange={setAfter}
              options={[
                { value: "cleaning", label: t("roomState.cleaning") },
                { value: "maintenance", label: t("roomState.maintenance") },
              ]}
            />
          </div>
          {after === "maintenance" && (
            <TextInput aria-label={t("checkout.maintenanceReason")} placeholder={t("checkout.maintenanceReason")} value={maintenanceReason} onChange={(e) => setMaintenanceReason(e.target.value)} />
          )}
        </div>
      )}

      {owes &&
        (open ? (
          <div className="flex flex-col gap-3 rounded-card border border-border p-4">
            <div className="flex items-center gap-2 text-body font-semibold">
              <KeyRound className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
              {t("checkout.override")}
              <span className="ms-auto text-label font-normal text-text-secondary">{t("checkout.overrideAudit")}</span>
            </div>
            <Field label={t("checkout.managerPassword")}>
              <TextInput type="password" autoComplete="off" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Field label={t("checkout.overrideReason")} required>
              <TextInput value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
            {totals.balance > 0 && (
              <div className="flex items-center gap-2 text-label font-normal text-warning-text">
                <TriangleAlert className="h-icon-inline w-icon-inline flex-none" strokeWidth={1.75} aria-hidden />
                {t("checkout.debtStays", { amount: money(totals.balance) })}
              </div>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="flex h-10 items-center gap-2 rounded-control border border-border bg-bg-page px-3 text-start font-sans text-body font-medium text-text-primary"
          >
            <ChevronDown className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
            {t("checkout.override")}
            <span className="ms-auto text-label font-normal text-text-secondary">{t("checkout.overrideHint")}</span>
          </button>
        ))}

      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}
