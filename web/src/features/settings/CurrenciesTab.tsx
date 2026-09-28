import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { ErrorBanner, Field, MoneyInput, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { apiErrorText, Card, Footnote, HeadRow, linkButton, smallButton } from "./shared";

type Currency = components["schemas"]["Currency"];
type Draft = { code: string; name: string; symbol: string; rate: string; is_active: boolean };
const GRID = "grid grid-cols-[72px_minmax(120px,1fr)_72px_minmax(180px,1.2fr)_72px_80px] items-center gap-3 px-4";
export const CURRENCIES = ["currencies"] as const;

/** Everyone reads the accepted currencies (payment dialogs); only the owner adds one or changes its rate. */
export function useCurrencies() {
  return useQuery({ queryKey: CURRENCIES, queryFn: () => data(api.GET("/api/v1/currencies/")), staleTime: 60_000 });
}

const toDraft = (c?: Currency): Draft => ({
  code: c?.code ?? "",
  name: c?.name ?? "",
  symbol: c?.symbol ?? "",
  rate: c ? formatMoney(c.rate) : "",
  is_active: c?.is_active ?? true,
});

/** «العملات» (owner decision 2026-09-28): the hotel's own currency plus the ones the owner accepts, each with its rate. */
export function CurrenciesTab({ readOnly, owner }: { readOnly: boolean; owner: boolean }) {
  const queryClient = useQueryClient();
  const currencies = useCurrencies();
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(toDraft());
  const [error, setError] = useState<string | null>(null);
  const canEdit = owner && !readOnly;

  const start = (c: Currency | null) => {
    setError(null);
    setDraft(toDraft(c ?? undefined));
    setEditing(c ? c.id : "new");
  };

  const save = useMutation({
    mutationFn: async () => {
      const rate = parseMoney(draft.rate);
      if (rate === null || rate <= 0) throw new Error(t("settings.currencies.rateRequired"));
      if (editing === "new") {
        return data(
          api.POST("/api/v1/currencies/", {
            body: { code: draft.code.trim().toUpperCase(), name: draft.name.trim(), symbol: draft.symbol.trim(), rate },
          }),
        );
      }
      const current = currencies.data!.find((c) => c.id === editing)!;
      return data(
        api.PATCH("/api/v1/currencies/{id}", {
          params: { path: { id: current.id } },
          body: { version: current.version, name: draft.name.trim(), symbol: draft.symbol.trim(), rate, is_active: draft.is_active },
        }),
      );
    },
    onSuccess: () => {
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: CURRENCIES });
    },
    onError: (e) => setError(e instanceof Error && !("code" in e) ? e.message : apiErrorText(e)),
  });

  const rows: (Currency | null)[] = [...(currencies.data ?? []), ...(editing === "new" ? [null] : [])];

  return (
    <Card
      title={t("settings.tabs.currencies")}
      actions={
        canEdit && (
          <button type="button" disabled={editing !== null} onClick={() => start(null)} className={smallButton()}>
            <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("settings.currencies.new")}
          </button>
        )
      }
    >
      {error && (
        <div className="p-4 pb-0">
          <ErrorBanner>{error}</ErrorBanner>
        </div>
      )}
      <HeadRow grid={GRID} labels={["code", "name", "symbol", "rate", "active", ""].map((k) => (k ? t(`settings.currencies.col_${k}`) : ""))} />
      <div className={`${GRID} h-12 border-b border-border bg-bg-surface-2 text-table-cell`}>
        <div className="font-semibold">{t("settings.currencies.baseCode")}</div>
        <div>{t("settings.hotel.currencyName")}</div>
        <div>{t("money.currency")}</div>
        <div className="text-text-secondary">{t("settings.currencies.base")}</div>
        <div>{t("settings.yes")}</div>
        <div />
      </div>
      {rows.map((c) => {
        if (c ? editing === c.id : true) {
          return (
            <div key={c?.id ?? "new"} className="flex flex-wrap items-end gap-3 border-b border-border bg-primary-soft px-4 py-3 text-table-cell">
              <Field label={t("settings.currencies.col_code")} className="w-24" hint={c ? undefined : t("settings.currencies.codeHint")}>
                <TextInput dir="ltr" maxLength={3} readOnly={!!c} value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })} />
              </Field>
              <Field label={t("settings.currencies.col_name")} className="w-48">
                <TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </Field>
              <Field label={t("settings.currencies.col_symbol")} className="w-20">
                <TextInput dir="ltr" maxLength={6} value={draft.symbol} onChange={(e) => setDraft({ ...draft, symbol: e.target.value })} />
              </Field>
              <Field label={t("settings.currencies.rateLabel", { code: draft.symbol || draft.code || "1" })} className="w-52">
                <MoneyInput value={draft.rate} onChange={(e) => setDraft({ ...draft, rate: e.target.value })} />
              </Field>
              {c && (
                <div className="flex h-9 items-center gap-2">
                  <Toggle checked={draft.is_active} label={t("settings.currencies.col_active")} onChange={(is_active) => setDraft({ ...draft, is_active })} />
                  <span className="text-label text-text-secondary">{t("settings.currencies.col_active")}</span>
                </div>
              )}
              <div className="flex h-9 items-center gap-2">
                <button type="button" disabled={!draft.code.trim() || !draft.name.trim() || save.isPending} onClick={() => save.mutate()} className={smallButton("primary")}>
                  {t("settings.save")}
                </button>
                <button type="button" onClick={() => setEditing(null)} className={linkButton}>
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          );
        }
        return (
          <div key={c!.id} className={`${GRID} h-12 border-b border-border text-table-cell ${c!.is_active ? "" : "text-text-disabled"}`}>
            <div dir="ltr" className="text-end font-semibold">
              {c!.code}
            </div>
            <div className="truncate">{c!.name}</div>
            <div dir="ltr" className="text-end">
              {c!.symbol}
            </div>
            <div className="font-semibold">{t("settings.currencies.rateText", { unit: c!.symbol || c!.code, rate: formatMoney(c!.rate) })}</div>
            <div>{t(c!.is_active ? "settings.yes" : "settings.no")}</div>
            <div>
              {canEdit && (
                <button type="button" disabled={editing !== null} onClick={() => start(c)} className={linkButton}>
                  {t("settings.edit")}
                </button>
              )}
            </div>
          </div>
        );
      })}
      <Footnote>{owner ? t("settings.currencies.footnote") : t("settings.currencies.ownerOnly")}</Footnote>
    </Card>
  );
}
