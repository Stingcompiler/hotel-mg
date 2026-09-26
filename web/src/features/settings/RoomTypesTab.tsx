import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { ErrorBanner, MoneyInput, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { digits, toWestern } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { Cancelled, useConfirmGate } from "./confirm";
import { apiErrorText, Card, Footnote, HeadRow, linkButton, smallButton } from "./shared";

type RoomType = components["schemas"]["RoomType"];
type Draft = { name: string; capacity: string; nightly: string; weekly: string; monthly: string; is_active: boolean };
const GRID = "grid grid-cols-[1.3fr_80px_90px_1fr_1fr_1fr_90px_110px] items-center gap-4 px-4";
export const ROOM_TYPES = ["room-types"] as const;

const toDraft = (r?: RoomType): Draft => ({
  name: r?.name ?? "",
  capacity: String(r?.capacity ?? 2),
  nightly: r ? formatMoney(r.nightly_price) : "",
  weekly: r ? formatMoney(r.weekly_price) : "",
  monthly: r ? formatMoney(r.monthly_price) : "",
  is_active: r?.is_active ?? true,
});

/** 6.11 B «أنواع الغرف والأسعار»: one row per type, edited in place; prices are whole-period prices. */
export function RoomTypesTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const types = useQuery({ queryKey: ROOM_TYPES, queryFn: () => data(api.GET("/api/v1/room-types/")) });
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(toDraft());
  const [error, setError] = useState<string | null>(null);
  const { gate, modal } = useConfirmGate();

  const start = (r: RoomType | null) => {
    setError(null);
    setDraft(toDraft(r ?? undefined));
    setEditing(r ? r.id : "new");
  };

  const save = useMutation({
    mutationFn: async () => {
      const prices = { nightly_price: parseMoney(draft.nightly), weekly_price: parseMoney(draft.weekly), monthly_price: parseMoney(draft.monthly) };
      if (Object.values(prices).some((v) => v === null || v <= 0)) throw new Error(t("settings.types.pricesRequired"));
      const body = { name: draft.name.trim(), capacity: Number(draft.capacity) || 1, is_active: draft.is_active, ...(prices as Record<keyof typeof prices, number>) };
      if (editing === "new") {
        return gate(t("settings.types.actCreate", { name: body.name }), (headers) => data(api.POST("/api/v1/room-types/", { headers, body })));
      }
      const current = types.data!.find((r) => r.id === editing)!;
      // Only changed fields: a price in the body asks for the manager's password (spec §6.8).
      const changed = Object.fromEntries(Object.entries(body).filter(([k, v]) => current[k as keyof RoomType] !== v));
      return gate(t("settings.types.actPrices", { name: current.name }), (headers) =>
        data(api.PATCH("/api/v1/room-types/{id}", { params: { path: { id: current.id } }, headers, body: { ...changed, version: current.version } })),
      );
    },
    onSuccess: () => {
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ROOM_TYPES });
      void queryClient.invalidateQueries({ queryKey: ["rooms"] });
    },
    onError: (e) => !(e instanceof Cancelled) && setError(e instanceof Error && !("code" in e) ? e.message : apiErrorText(e)),
  });

  const rows: (RoomType | null)[] = [...(types.data ?? []), ...(editing === "new" ? [null] : [])];

  return (
    <Card
      title={t("settings.tabs.roomTypes")}
      actions={
        !readOnly && (
          <button type="button" disabled={editing !== null} onClick={() => start(null)} className={smallButton()}>
            <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("settings.types.new")}
          </button>
        )
      }
    >
      {error && (
        <div className="p-4 pb-0">
          <ErrorBanner>{error}</ErrorBanner>
        </div>
      )}
      <HeadRow grid={GRID} labels={["name", "capacity", "rooms", "nightly", "weekly", "monthly", "active", ""].map((k) => (k ? t(`settings.types.col_${k}`) : ""))} />
      {rows.map((r) => {
        const isEditing = r ? editing === r.id : true;
        if (isEditing) {
          return (
            <div key={r?.id ?? "new"} className={`${GRID} min-h-16 border-b border-border bg-primary-soft py-2 text-table-cell`}>
              <TextInput aria-label={t("settings.types.col_name")} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              <TextInput
                aria-label={t("settings.types.col_capacity")}
                inputMode="numeric"
                value={draft.capacity}
                onChange={(e) => setDraft({ ...draft, capacity: toWestern(e.target.value).replace(/\D/g, "") })}
              />
              <div className="text-text-secondary">{digits(String(r?.room_count ?? 0))}</div>
              <MoneyInput aria-label={t("settings.types.col_nightly")} value={draft.nightly} onChange={(e) => setDraft({ ...draft, nightly: e.target.value })} />
              <MoneyInput aria-label={t("settings.types.col_weekly")} value={draft.weekly} onChange={(e) => setDraft({ ...draft, weekly: e.target.value })} />
              <MoneyInput aria-label={t("settings.types.col_monthly")} value={draft.monthly} onChange={(e) => setDraft({ ...draft, monthly: e.target.value })} />
              <Toggle checked={draft.is_active} label={t("settings.types.col_active")} onChange={(is_active) => setDraft({ ...draft, is_active })} />
              <div className="flex gap-2">
                <button type="button" disabled={!draft.name.trim() || save.isPending} onClick={() => save.mutate()} className={smallButton("primary")}>
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
          <div key={r!.id} className={`${GRID} h-12 border-b border-border text-table-cell ${r!.is_active ? "" : "text-text-disabled"}`}>
            <div className="font-medium">{r!.name}</div>
            <div>{digits(String(r!.capacity))}</div>
            <div>{digits(String(r!.room_count))}</div>
            <div className="font-semibold">{formatMoney(r!.nightly_price)}</div>
            <div className="font-semibold">{formatMoney(r!.weekly_price)}</div>
            <div className="font-semibold">{formatMoney(r!.monthly_price)}</div>
            <div>{t(r!.is_active ? "settings.yes" : "settings.no")}</div>
            <div>
              {!readOnly && (
                <button type="button" disabled={editing !== null} onClick={() => start(r)} className={linkButton}>
                  {t("settings.edit")}
                </button>
              )}
            </div>
          </div>
        );
      })}
      <Footnote>
        <div>{t("settings.types.footnote")}</div>
        <div>{t("settings.types.footnote2")}</div>
      </Footnote>
      {modal}
    </Card>
  );
}
