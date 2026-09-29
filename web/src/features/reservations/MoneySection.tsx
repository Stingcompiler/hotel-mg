import type { components } from "@api/schema";

import { Field, MoneyInput, Section, Segmented, Select, TextInput } from "@/components/ui/form";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { amount, type Errors, type Form, type Method } from "./model";

type Currency = components["schemas"]["Currency"];
type Props = {
  form: Form;
  errors: Errors;
  update: (patch: Partial<Form>) => void;
  planPrice: number;
  planLabel: string;
  total: number;
  currencies: Currency[];
  depositBase: number;
};

/** Step 3 «المال»: price (edit needs a reason), discount + reason, deposit + method (+ reference when not cash). */
export function MoneySection({ form, errors, update, planPrice, planLabel, total, currencies, depositBase }: Props) {
  const edited = form.price !== null;
  // A deposit above the total is allowed (it stays as the guest's credit) but is usually a typo: say so before saving.
  const over = total > 0 && depositBase > total ? depositBase - total : 0;
  const depositCurrency = currencies.find((c) => c.code === form.deposit_currency);
  const typed = amount(form.deposit) ?? 0;
  return (
    <Section step={3} title={t("newRes.money")}>
      <div className="grid grid-cols-[1fr_1fr_2fr] items-start gap-3">
        <Field
          label={
            <>
              {t("newRes.price")} {edited && <span className="text-warning-text">{t("newRes.priceEdited")}</span>}
            </>
          }
          action={
            <button
              type="button"
              onClick={() => update(edited ? { price: null, override_reason: "" } : { price: formatMoney(planPrice) })}
              className="border-0 bg-transparent p-0 font-sans text-label font-medium text-primary hover:text-primary-hover"
            >
              {edited ? t("newRes.undoEdit") : t("newRes.editPrice")}
            </button>
          }
          error={errors.price}
          hint={edited ? t("newRes.originalPrice", { price: formatMoney(planPrice) }) : planLabel}
        >
          <MoneyInput
            readOnly={!edited}
            invalid={!!errors.price}
            value={edited ? form.price! : formatMoney(planPrice)}
            onChange={(e) => update({ price: e.target.value, needManager: false })}
          />
        </Field>
        {edited ? (
          <Field label={t("newRes.overrideReason")} required error={errors.override_reason} className="col-span-2">
            <TextInput value={form.override_reason} invalid={!!errors.override_reason} onChange={(e) => update({ override_reason: e.target.value })} />
          </Field>
        ) : (
          <div className="col-span-2" />
        )}
      </div>

      <div className="grid grid-cols-[1fr_1fr_2fr] items-start gap-3">
        <Field label={t("newRes.discount")} error={errors.discount}>
          <MoneyInput value={form.discount} invalid={!!errors.discount} placeholder="0" onChange={(e) => update({ discount: e.target.value, needManager: false })} />
        </Field>
        <Field label={t("newRes.discountReason")} required={form.discount.trim() !== "" && form.discount.trim() !== "0"} error={errors.discount_reason} className="col-span-2">
          <TextInput
            value={form.discount_reason}
            invalid={!!errors.discount_reason}
            placeholder={t("newRes.discountReasonHint")}
            onChange={(e) => update({ discount_reason: e.target.value })}
          />
        </Field>
      </div>

      {form.needManager && (
        <div className="flex flex-col gap-2 rounded-control border border-warning bg-warning-soft p-3">
          <span className="text-body font-medium text-warning-text">{t("newRes.managerTitle")}</span>
          <div className="grid grid-cols-[1fr_2fr] gap-3">
            <Field label={t("newRes.managerPassword")} required error={errors.manager}>
              <TextInput type="password" autoComplete="off" value={form.manager_password} onChange={(e) => update({ manager_password: e.target.value })} />
            </Field>
            <Field label={t("newRes.managerReason")} required>
              <TextInput value={form.manager_reason} onChange={(e) => update({ manager_reason: e.target.value })} />
            </Field>
          </div>
        </div>
      )}

      <div className="grid grid-cols-[1fr_1fr_2fr] items-start gap-3">
        <Field
          label={t("newRes.deposit")}
          error={errors.deposit}
          hint={
            depositCurrency && typed > 0
              ? t("payment.equivalent", {
                  amount: `${formatMoney(depositBase)} ${t("money.currency")}`,
                  rate: `1 ${depositCurrency.symbol || depositCurrency.code} = ${formatMoney(depositCurrency.rate)}`,
                })
              : undefined
          }
          action={
            currencies.length > 0 ? (
              <span className="w-24">
                <Select aria-label={t("payment.currency")} value={form.deposit_currency} onChange={(e) => update({ deposit_currency: e.target.value, deposit: "" })}>
                  <option value="">{t("money.currency")}</option>
                  {currencies.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.symbol || c.code}
                    </option>
                  ))}
                </Select>
              </span>
            ) : undefined
          }
        >
          <MoneyInput
            value={form.deposit}
            suffix={depositCurrency ? depositCurrency.symbol || depositCurrency.code : undefined}
            invalid={!!errors.deposit}
            placeholder="0"
            onChange={(e) => update({ deposit: e.target.value })}
          />
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("newRes.method")}</span>
          <Segmented<Method>
            label={t("newRes.method")}
            value={form.deposit_method}
            onChange={(v) => update({ deposit_method: v })}
            options={(["cash", "bankak", "transfer"] as const).map((m) => ({ value: m, label: t(`payMethod.${m}`) }))}
          />
        </div>
        {form.deposit_method === "cash" ? (
          <span className="pt-8 text-label font-normal text-text-disabled">{t("newRes.referenceNote")}</span>
        ) : (
          <Field label={t("newRes.reference")} required error={errors.deposit_reference}>
            <TextInput
              dir="ltr"
              value={form.deposit_reference}
              invalid={!!errors.deposit_reference}
              placeholder={t("newRes.referenceHint")}
              onChange={(e) => update({ deposit_reference: e.target.value })}
            />
          </Field>
        )}
      </div>
      {over > 0 && (
        <div role="status" className="rounded-control bg-warning-soft px-3 py-2.5 text-body text-warning-text">
          {t("payment.overpay", { amount: `${formatMoney(over)} ${t("money.currency")}` })}
        </div>
      )}
    </Section>
  );
}
