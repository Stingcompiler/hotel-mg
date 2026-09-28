import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { keys, useHotelSettings, useSystemStatus } from "@/api/queries";
import { ErrorBanner, Field, MoneyInput, Segmented, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { formatWhen } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { apiErrorText, Card, smallButton } from "./shared";

type Settings = components["schemas"]["HotelSettings"];
type Draft = {
  name_ar: string;
  name_latin: string;
  address: string;
  phone: string;
  digits: "western" | "arabic";
  money_decimals: "0" | "2";
  stay_day_end: string;
  session_lock_minutes: string;
  expense_attachment_threshold: string;
  max_discount_percent: string;
  debt_attention_threshold: string;
  thermal_printer: string;
  auto_print_receipt: boolean;
};

const toDraft = (s: Settings): Draft => ({
  name_ar: s.name_ar,
  name_latin: s.name_latin,
  address: s.address,
  phone: s.phone,
  digits: s.digits,
  money_decimals: s.money_decimals === 2 ? "2" : "0",
  stay_day_end: s.stay_day_end.slice(0, 5),
  session_lock_minutes: String(s.session_lock_minutes),
  expense_attachment_threshold: formatMoney(s.expense_attachment_threshold),
  max_discount_percent: String(s.max_discount_percent),
  debt_attention_threshold: formatMoney(s.debt_attention_threshold),
  thermal_printer: s.thermal_printer,
  auto_print_receipt: s.auto_print_receipt,
});
const num = (text: string) => toWestern(text).replace(/\D/g, "");

/** V2 6.11 D «بيانات الفندق»: identity for print-outs and operating rules; one save with the row version. */
export function HotelTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const settings = useHotelSettings().data;
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (settings) setDraft(toDraft(settings));
  }, [settings]);

  const save = useMutation({
    mutationFn: () => {
      const d = draft!;
      return data(
        api.PATCH("/api/v1/system/settings", {
          body: {
            version: settings!.version,
            name_ar: d.name_ar.trim(),
            name_latin: d.name_latin.trim(),
            address: d.address.trim(),
            phone: d.phone.trim(),
            digits: d.digits,
            money_decimals: Number(d.money_decimals),
            stay_day_end: d.stay_day_end,
            session_lock_minutes: Number(d.session_lock_minutes || 0),
            expense_attachment_threshold: parseMoney(d.expense_attachment_threshold || "0") ?? 0,
            max_discount_percent: Number(d.max_discount_percent || 0),
            debt_attention_threshold: parseMoney(d.debt_attention_threshold || "0") ?? 0,
            thermal_printer: d.thermal_printer.trim(),
            auto_print_receipt: d.auto_print_receipt,
          },
        }),
      );
    },
    onSuccess: (value) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(keys.settings, value);
    },
    onError: (e) => setError(apiErrorText(e)),
  });

  if (!settings || !draft) return null;
  const set = (patch: Partial<Draft>) => {
    setSaved(false);
    setDraft({ ...draft, ...patch });
  };

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="grid grid-cols-2 gap-4">
        <Card title={t("settings.hotel.identity")}>
          <div className="grid grid-cols-2 gap-4 p-4">
            <Field label={t("settings.hotel.nameAr")} required>
              <TextInput readOnly={readOnly} value={draft.name_ar} onChange={(e) => set({ name_ar: e.target.value })} />
            </Field>
            <Field label={t("settings.hotel.nameLatin")}>
              <TextInput readOnly={readOnly} dir="ltr" value={draft.name_latin} onChange={(e) => set({ name_latin: e.target.value })} />
            </Field>
            <Field label={t("settings.hotel.address")} className="col-span-2">
              <TextInput readOnly={readOnly} value={draft.address} onChange={(e) => set({ address: e.target.value })} />
            </Field>
            <Field label={t("settings.hotel.phone")}>
              <TextInput readOnly={readOnly} dir="ltr" value={draft.phone} onChange={(e) => set({ phone: e.target.value })} />
            </Field>
            <Field label={t("settings.hotel.hotelId")} hint={t("settings.hotel.hotelIdHint")}>
              <div dir="ltr" className="min-h-9 rounded-control border border-border bg-bg-surface-2 px-3 py-1.5 text-body text-text-primary break-all text-end">
                {settings.hotel_id}
              </div>
            </Field>
          </div>
        </Card>
        <Card title={t("settings.hotel.rules")}>
          <div className="grid grid-cols-2 gap-4 p-4">
            <Field label={t("settings.hotel.currency")}>
              <div className="min-h-9 rounded-control border border-border bg-bg-surface-2 px-3 py-1.5 text-body text-text-primary">{`${t("money.currency")} — ${t("settings.hotel.currencyName")} (${settings.currency})`}</div>
            </Field>
            <Field label={t("settings.hotel.digits")}>
              <Segmented<Draft["digits"]>
                label={t("settings.hotel.digits")}
                value={draft.digits}
                onChange={(v) => !readOnly && set({ digits: v })}
                options={[
                  { value: "western", label: "123" },
                  { value: "arabic", label: digits("123", "arabic") },
                ]}
              />
            </Field>
            <Field label={t("settings.hotel.decimals")}>
              <Segmented<Draft["money_decimals"]>
                label={t("settings.hotel.decimals")}
                value={draft.money_decimals}
                onChange={(v) => !readOnly && set({ money_decimals: v })}
                options={[
                  { value: "0", label: t("settings.hotel.decimals0") },
                  { value: "2", label: t("settings.hotel.decimals2") },
                ]}
              />
            </Field>
            <Field label={t("settings.hotel.dayEnd")} hint={t("settings.hotel.dayEndHint")}>
              <TextInput readOnly={readOnly} type="time" dir="ltr" value={draft.stay_day_end} onChange={(e) => set({ stay_day_end: e.target.value })} />
            </Field>
            <Field label={t("settings.hotel.lock")} hint={t("settings.hotel.minutes")}>
              <TextInput readOnly={readOnly} inputMode="numeric" value={draft.session_lock_minutes} onChange={(e) => set({ session_lock_minutes: num(e.target.value) })} />
            </Field>
            <Field label={t("settings.hotel.maxDiscount")} hint="%">
              <TextInput readOnly={readOnly} inputMode="numeric" value={draft.max_discount_percent} onChange={(e) => set({ max_discount_percent: num(e.target.value) })} />
            </Field>
            <Field label={t("settings.hotel.attachAbove")}>
              <MoneyInput readOnly={readOnly} value={draft.expense_attachment_threshold} onChange={(e) => set({ expense_attachment_threshold: e.target.value })} />
            </Field>
            <Field label={t("settings.hotel.debtAbove")}>
              <MoneyInput readOnly={readOnly} value={draft.debt_attention_threshold} onChange={(e) => set({ debt_attention_threshold: e.target.value })} />
            </Field>
          </div>
        </Card>
      </div>
      <Card title={t("settings.hotel.printing")}>
        <div className="grid grid-cols-[1fr_1fr] items-end gap-4 p-4">
          <Field label={t("settings.hotel.printer")} hint={t("settings.hotel.printerHint")}>
            <TextInput readOnly={readOnly} dir="ltr" value={draft.thermal_printer} onChange={(e) => set({ thermal_printer: e.target.value })} />
          </Field>
          <div className="flex h-9 items-center gap-3">
            <Toggle checked={draft.auto_print_receipt} disabled={readOnly} label={t("settings.hotel.autoPrint")} onChange={(v) => set({ auto_print_receipt: v })} />
            <span className="text-body">{t("settings.hotel.autoPrint")}</span>
          </div>
        </div>
      </Card>
      <VersionLine />
      {!readOnly && (
        <div className="flex items-center gap-3">
          <button type="button" disabled={save.isPending || !draft.name_ar.trim()} onClick={() => save.mutate()} className={smallButton("primary")}>
            {t("settings.save")}
          </button>
          <span className={`text-label font-normal ${saved ? "text-success-text" : "text-text-secondary"}`}>
            {saved ? t("settings.savedNow") : t("settings.lastSaved", { when: formatWhen(settings.updated_at) })}
          </span>
        </div>
      )}
    </div>
  );
}

/** «الإصدار» line under the cards: program version and database schema, from `system/status`. */
function VersionLine() {
  const status = useSystemStatus().data;
  if (!status) return null;
  return (
    <div className="text-label font-normal text-text-secondary">
      {t("settings.hotel.version", { version: digits(status.version), schema: digits(String(status.schema_version)) })}
    </div>
  );
}
