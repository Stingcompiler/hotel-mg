import { useQuery } from "@tanstack/react-query";
import { TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, MoneyInput, Segmented, TextInput } from "@/components/ui/form";
import { buttons } from "@/components/ui/Modal";
import { nights } from "@/i18n/counts";
import { formatDayMonth } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Props = {
  stayId: string;
  version: number;
  room: string;
  guest: string;
  kind: string;
  checkIn: string;
  totalNights: number;
  paid: number;
  total: number;
  onClose: () => void;
  onDone: () => void;
};

const money = (v: number) => `${formatMoney(v)} ${t("money.currency")}`;

/**
 * V2 «نافذة إلغاء الإقامة»: nothing is deleted; the nights used are settled one of three ways, the excess
 * paid is refunded from the shift. A manager password is always required; the danger button names the refund.
 */
export function CancelStayModal(props: Props) {
  const { stayId, version, room, guest, kind, checkIn, totalNights, paid, total, onClose, onDone } = props;
  const closeRef = useRef<HTMLButtonElement>(null);
  const options = useQuery({
    queryKey: ["cancel-options", stayId],
    queryFn: () => data(api.GET("/api/v1/stays/{id}/cancel", { params: { path: { id: stayId } } })),
  });
  const [key, setKey] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [method, setMethod] = useState<"cash" | "bankak" | "transfer">("cash");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const o = options.data;
  const selected = key ?? o?.options[0]?.key ?? null;
  const manualMinor = key === "manual" ? parseMoney(manual) : null;
  const newTotal = key === "manual" ? manualMinor : o?.options.find((x) => x.key === selected)?.total ?? null;
  // Services stay charged on top of the new total; the server's own figures (review 2026-09-29, A-11).
  const paidSoFar = o?.paid ?? paid;
  const refund = newTotal === null ? 0 : paidSoFar - (newTotal + (o?.services_total ?? 0));
  const needsReference = refund > 0 && method !== "cash" && !reference.trim();
  const can = newTotal !== null && !!reason.trim() && !!password && !needsReference && !busy;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await data(
        api.POST("/api/v1/stays/{id}/cancel", {
          params: { path: { id: stayId } },
          body: {
            reason: reason.trim(),
            option_key: key === "manual" ? null : selected,
            manual_total: key === "manual" ? manualMinor : null,
            override_password: password,
            override_reason: reason.trim(),
            refund_method: method,
            refund_reference: reference.trim(),
            version,
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

  const radio = (active: boolean) =>
    `flex h-12 items-center gap-3 rounded-control border px-4 text-start font-sans ${active ? "border-primary bg-primary-soft" : "border-border-strong bg-bg-surface"}`;
  const dot = (active: boolean) =>
    `h-[18px] w-[18px] flex-none rounded-full bg-bg-surface ${active ? "border-[5px] border-primary" : "border-[1.5px] border-border-strong"}`;

  return (
    <div className="scrim-32 fixed inset-0 z-50 flex items-center justify-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={t("cancelStay.title", { room: digits(room) })} className="flex max-h-[90vh] w-[600px] flex-col rounded-modal bg-bg-surface shadow-elevated">
        <div className="flex items-center gap-3 border-b border-border px-6 py-5">
          <span className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-danger-soft text-danger">
            <TriangleAlert className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          </span>
          <div className="flex-1">
            <h2 className="m-0 text-page-title">{t("cancelStay.title", { room: digits(room) })}</h2>
            <div className="text-body text-text-secondary">
              {t("cancelStay.sub", { guest, kind, date: formatDayMonth(checkIn), nights: nights(o?.nights_used ?? 0) })}
            </div>
          </div>
          <button ref={closeRef} type="button" aria-label={t("common.close")} onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2">
            <X className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          </button>
        </div>

        <div className="flex flex-col gap-4 overflow-auto px-6 py-5">
          <div className="rounded-card bg-danger-soft px-4 py-3 text-body text-danger-text">{t("cancelStay.notice")}</div>

          <div role="radiogroup" className="flex flex-col gap-1.5">
            <span className="text-label text-text-secondary">
              {t("cancelStay.settle", { used: digits(String(o?.nights_used ?? 0)), total: digits(String(totalNights)) })}
            </span>
            {o?.options.map((x) => (
              <button key={x.key} type="button" role="radio" aria-checked={selected === x.key && key !== "manual"} onClick={() => setKey(x.key)} className={radio(selected === x.key && key !== "manual")}>
                <span className={dot(selected === x.key && key !== "manual")} />
                <span className="flex-1 text-body font-semibold text-text-primary">{t("cancelStay.optionLabel", { label: x.label })}</span>
                <span className="text-body font-semibold text-text-primary">{money(x.total)}</span>
              </button>
            ))}
            <button type="button" role="radio" aria-checked={key === "manual"} onClick={() => setKey("manual")} className={radio(key === "manual")}>
              <span className={dot(key === "manual")} />
              <span className="flex-1 text-body font-semibold text-text-primary">
                {t("cancelStay.manual")} <span className="text-label font-normal text-text-secondary">{t("cancelStay.manualHint")}</span>
              </span>
            </button>
            {key === "manual" && (
              <Field label={t("cancelStay.manualAmount")}>
                <MoneyInput autoFocus value={manual} onChange={(e) => setManual(e.target.value)} />
              </Field>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3 border-t border-border pt-3">
            <div>
              <div className="text-label text-text-secondary">{t("cancelStay.newTotal")}</div>
              <div className="text-section-title">{newTotal === null ? "—" : money(newTotal)}</div>
              <div className="text-label font-normal text-text-secondary">{t("cancelStay.instead", { amount: formatMoney(total) })}</div>
            </div>
            <div>
              <div className="text-label text-text-secondary">{t("cancelStay.paid")}</div>
              <div className="text-section-title">{money(paidSoFar)}</div>
              {!!o?.services_total && <div className="text-label font-normal text-text-secondary">{t("cancelStay.services", { amount: formatMoney(o.services_total) })}</div>}
            </div>
            <div>
              <div className="text-label text-text-secondary">{refund >= 0 ? t("cancelStay.refund") : t("cancelStay.owed")}</div>
              <div className={`text-headline-number ${refund >= 0 ? "text-success" : "text-danger"}`}>{money(Math.abs(refund))}</div>
              {refund > 0 && <div className="text-label font-normal text-text-secondary">{t("cancelStay.refundNote")}</div>}
            </div>
          </div>

          {refund > 0 && (
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-label text-text-secondary">{t("cancelStay.refundMethod")}</span>
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
          <Field label={t("cancelStay.reason")} required>
            <TextInput value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <Field label={t("cancelStay.managerPassword")} required>
            <TextInput type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {error && <ErrorBanner>{error}</ErrorBanner>}
        </div>

        <div className="flex items-center gap-2 border-t border-border px-6 py-4">
          <button type="button" disabled={!can} onClick={() => void submit()} className={buttons.danger}>
            {refund > 0 ? t("cancelStay.submitRefund", { amount: formatMoney(refund) }) : t("cancelStay.submit")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("cancelStay.back")}
          </button>
        </div>
      </div>
    </div>
  );
}
