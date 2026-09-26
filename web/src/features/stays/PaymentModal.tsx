import { useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, MoneyInput, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Method = "cash" | "bankak" | "transfer";
type Props = { folioId: string; room: string; balance: number; onClose: () => void; onDone: () => void };

/** «إضافة دفعة»: recorded in this device's open shift (the server refuses without one). */
export function PaymentModal({ folioId, room, balance, onClose, onDone }: Props) {
  const [amount, setAmount] = useState(balance > 0 ? formatMoney(balance) : "");
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const minor = parseMoney(amount);
  const invalidAmount = amount !== "" && (minor === null || minor <= 0);
  const needsReference = method !== "cash" && !reference.trim();

  const save = async () => {
    if (minor === null || minor <= 0) return setError(t("payment.errAmount"));
    if (needsReference) return setError(t("payment.errReference"));
    setBusy(true);
    setError(null);
    try {
      await data(api.POST("/api/v1/folios/{id}/payments", { params: { path: { id: folioId } }, body: { amount: minor, method, reference: reference.trim() } }));
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("payment.title", { room: digits(room) })}
      onClose={onClose}
      width={480}
      footer={
        <>
          <button type="button" disabled={busy || minor === null || minor <= 0} onClick={() => void save()} className={buttons.primary}>
            {t("payment.save")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="text-body text-text-secondary">{t("payment.balance", { amount: `${formatMoney(balance)} ${t("money.currency")}` })}</div>
      <Field label={t("payment.amount")} error={invalidAmount ? t("payment.errAmount") : null}>
        <MoneyInput autoFocus value={amount} invalid={invalidAmount} onChange={(e) => setAmount(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void save()} />
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
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}
