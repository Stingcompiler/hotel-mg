import { useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { useHotelSettings } from "@/api/queries";
import { ErrorBanner, Field, MoneyInput, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { openPrint } from "@/features/print/PrintPage";
import { useCurrencies } from "@/features/settings/CurrenciesTab";
import { digits } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { notice } from "@/lib/notices";

type Method = "cash" | "bankak" | "transfer";
type Props = { folioId: string; room: string; balance: number; onClose: () => void; onDone: () => void };

/** «إضافة دفعة»: recorded in this device's open shift (the server refuses without one). */
export function PaymentModal({ folioId, room, balance, onClose, onDone }: Props) {
  const autoPrint = useHotelSettings().data?.auto_print_receipt ?? false;
  const [amount, setAmount] = useState(balance > 0 ? formatMoney(balance) : "");
  const [method, setMethod] = useState<Method>("cash");
  // Another currency the owner accepts (settings › العملات): typed in it; the server converts at its rate.
  const currencies = (useCurrencies().data ?? []).filter((c) => c.is_active);
  const [code, setCode] = useState("");
  const currency = currencies.find((c) => c.code === code);
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const minor = parseMoney(amount);
  const invalidAmount = amount !== "" && (minor === null || minor <= 0);
  const needsReference = method !== "cash" && !reference.trim();
  // The pounds it is worth, shown before saving (the server applies the same rate and has the final word).
  const base = minor !== null && currency ? Math.round((minor * currency.rate) / 100) : minor;
  // Paying more than the balance is allowed (a deposit for the next nights) but is usually a typo: say so before saving.
  const overpay = base !== null && balance > 0 && base > balance ? base - balance : 0;
  const sign = currency ? currency.symbol || currency.code : t("money.currency");

  const save = async () => {
    if (minor === null || minor <= 0) return setError(t("payment.errAmount"));
    if (needsReference) return setError(t("payment.errReference"));
    setBusy(true);
    setError(null);
    try {
      const payment = await data(
        api.POST("/api/v1/folios/{id}/payments", {
          params: { path: { id: folioId } },
          body: currency
            ? { method, reference: reference.trim(), currency: currency.code, foreign_amount: minor }
            : { amount: minor, method, reference: reference.trim() },
        }),
      );
      // «طباعة إيصال تلقائيًا بعد كل دفعة» (hotel settings, V2 6.11 D).
      if (autoPrint) openPrint("receipt", payment.id);
      notice(t("payment.saved", { amount: `${formatMoney(minor)} ${sign}`, room: digits(room) }));
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
      {currencies.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("payment.currency")}</span>
          <Segmented<string>
            label={t("payment.currency")}
            value={code}
            onChange={(next) => {
              setCode(next);
              setAmount("");
            }}
            options={[{ value: "", label: t("money.currency") }, ...currencies.map((c) => ({ value: c.code, label: c.symbol || c.code }))]}
          />
        </div>
      )}
      <Field label={t("payment.amount")} error={invalidAmount ? t("payment.errAmount") : null}>
        <MoneyInput autoFocus suffix={sign} value={amount} invalid={invalidAmount} onChange={(e) => setAmount(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void save()} />
      </Field>
      {currency && base !== null && base > 0 && (
        <div className="text-body text-text-secondary">
          {t("payment.equivalent", { amount: `${formatMoney(base)} ${t("money.currency")}`, rate: `1 ${sign} = ${formatMoney(currency.rate)}` })}
        </div>
      )}
      {overpay > 0 && (
        <div role="status" className="rounded-control bg-warning-soft px-3 py-2.5 text-body text-warning-text">
          {t("payment.overpay", { amount: `${formatMoney(overpay)} ${t("money.currency")}` })}
        </div>
      )}
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
