import { useState } from "react";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, MoneyInput, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { notice } from "@/lib/notices";

type Entry = components["schemas"]["LedgerEntry"];
type Method = "cash" | "bankak" | "transfer";

/** «عكس» a folio line or a payment: a counter-entry with a reason; nothing is edited or deleted.
 *  A room charge, a discount or someone else's payment needs the manager's password (the server says so). */
export function ReverseModal({ folioId, entry, onClose, onDone }: { folioId: string; entry: Entry; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [needsManager, setNeedsManager] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const payment = entry.type === "payment";

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    const body = { reason: reason.trim(), manager_password: needsManager ? password : "" };
    try {
      if (payment) await data(api.POST("/api/v1/payments/{id}/reverse", { params: { path: { id: entry.id } }, body }));
      else await data(api.POST("/api/v1/folios/{id}/lines/{line_pk}/reverse", { params: { path: { id: folioId, line_pk: entry.id } }, body }));
      notice(t("folioAction.reverseDone"));
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.code === "override_required") setNeedsManager(true);
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };
  const ready = !!reason.trim() && (!needsManager || !!password) && !busy;

  return (
    <Modal
      title={t(payment ? "folioAction.reversePayment" : "folioAction.reverseLine")}
      onClose={onClose}
      width={480}
      footer={
        <>
          <button type="button" disabled={!ready} onClick={() => void submit()} className={buttons.danger}>
            {t("folioAction.reverse")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="text-body">
        {entry.text} · <span className="font-semibold">{formatMoney(entry.debit || entry.credit)} {t("money.currency")}</span>
      </div>
      <div className="text-body text-text-secondary">{t("folioAction.reverseText")}</div>
      <Field label={t("folioAction.reverseReason")} required>
        <TextInput autoFocus value={reason} onChange={(e) => setReason(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ready && void submit()} />
      </Field>
      {needsManager && (
        <Field label={t("folioAction.managerPassword")} required hint={t("folioAction.managerNeeded")}>
          <TextInput type="password" autoComplete="off" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
      )}
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}

/** «ردّ مبلغ»: pays the guest's credit back, from this device's open shift, with a reason. */
export function RefundModal({ folioId, room, credit, onClose, onDone }: { folioId: string; room: string; credit: number; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState(formatMoney(credit));
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const minor = parseMoney(amount);
  const invalidAmount = amount !== "" && (minor === null || minor <= 0);
  const tooMuch = minor !== null && minor > credit;
  const ready = minor !== null && minor > 0 && !tooMuch && !!reason.trim() && (method === "cash" || !!reference.trim()) && !busy;

  const save = async () => {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      await data(
        api.POST("/api/v1/folios/{id}/refunds", {
          params: { path: { id: folioId } },
          body: { amount: minor, method, reference: reference.trim(), reason: reason.trim() },
        }),
      );
      notice(t("folioAction.refundDone", { amount: `${formatMoney(minor)} ${t("money.currency")}` }));
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("folioAction.refundTitle", { room: digits(room) })}
      onClose={onClose}
      width={480}
      footer={
        <>
          <button type="button" disabled={!ready} onClick={() => void save()} className={buttons.primary}>
            {t("folioAction.refundSave")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="text-body text-text-secondary">{t("folioAction.refundCredit", { amount: `${formatMoney(credit)} ${t("money.currency")}` })}</div>
      <Field label={t("payment.amount")} error={invalidAmount ? t("payment.errAmount") : tooMuch ? t("folioAction.errRefundAmount") : null}>
        <MoneyInput autoFocus value={amount} invalid={invalidAmount || tooMuch} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <div className="flex flex-col gap-1.5">
        <span className="text-label text-text-secondary">{t("payment.method")}</span>
        <Segmented<Method>
          label={t("payment.method")}
          value={method}
          onChange={setMethod}
          options={(["cash", "bankak", "transfer"] as const).map((m) => ({ value: m, label: t(`payMethod.${m}`) }))}
        />
      </div>
      {method !== "cash" && (
        <Field label={t("payment.reference")} required>
          <TextInput dir="ltr" value={reference} placeholder={t("payment.referenceHint")} onChange={(e) => setReference(e.target.value)} />
        </Field>
      )}
      <Field label={t("folioAction.refundReason")} required>
        <TextInput value={reason} onChange={(e) => setReason(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void save()} />
      </Field>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}
