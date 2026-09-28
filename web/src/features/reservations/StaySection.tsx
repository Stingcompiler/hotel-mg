import { useQuery } from "@tanstack/react-query";
import { CalendarCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { api, data } from "@/api/client";
import { Field, Section, Segmented, Select, TextInput } from "@/components/ui/form";
import { type RoomState, stateColor } from "@/design/state";
import { nights, roomsAvailable } from "@/i18n/counts";
import { formatDayDate } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import type { Errors, Form, Kind, Quote } from "./model";

type Props = {
  form: Form;
  errors: Errors;
  update: (patch: Partial<Form>) => void;
  quote: Quote | undefined;
  quoteLoading: boolean;
  today: string;
  roomStatus: Record<string, string>;
};

export function useRoomTypes() {
  return useQuery({ queryKey: ["room-types"], queryFn: () => data(api.GET("/api/v1/room-types/")), staleTime: 5 * 60_000 });
}

/** Step 2 «الإقامة»: room type, free rooms for the whole period, arrival, duration; mixed stays pick a pricing. */
export function StaySection({ form, errors, update, quote, quoteLoading, today, roomStatus }: Props) {
  // The count is typed freely (clearing it to type «15» must not jump to «1»); only whole 1–366 values are applied.
  const [countText, setCountText] = useState(String(form.count));
  useEffect(() => setCountText((text) => (Number(text) === form.count ? text : String(form.count))), [form.count]);
  const types = useRoomTypes().data?.filter((rt) => rt.is_active) ?? [];
  const rooms = useQuery({
    queryKey: ["availability", form.room_type, form.check_in_date, quote?.check_out_date],
    queryFn: () =>
      data(
        api.GET("/api/v1/reservations/availability", {
          params: { query: { room_type: form.room_type, date_from: form.check_in_date, date_to: quote!.check_out_date } },
        }),
      ),
    enabled: !!form.room_type && !!quote,
  });
  const free = rooms.data ?? [];
  const checking = !!form.room_type && (quoteLoading || rooms.isFetching);
  const ready = stateColor("ready");

  return (
    <Section step={2} title={t("newRes.stay")}>
      <div className="grid grid-cols-[1fr_3fr] items-start gap-3">
        <Field label={t("newRes.roomType")} required error={errors.room_type}>
          <Select
            value={form.room_type}
            invalid={!!errors.room_type}
            onChange={(e) => update({ room_type: e.target.value, room: null, option_key: null, price: null })}
          >
            <option value="">{t("newRes.choose")}</option>
            {types.map((rt) => (
              <option key={rt.id} value={rt.id}>
                {rt.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className={`flex items-center gap-1.5 text-label ${errors.room ? "text-danger" : "text-text-secondary"}`}>
            {checking ? (
              <>
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-border border-t-primary" />
                {t("newRes.checkingRooms")}
              </>
            ) : (
              <>
                {t("newRes.room")}
                {form.room_type && rooms.isSuccess && (
                  <>
                    {" — "}
                    <span className={free.length ? ready.text : "text-danger"}>
                      {free.length ? roomsAvailable(free.length) : t("newRes.noRooms")}
                    </span>
                  </>
                )}
              </>
            )}
          </span>
          <div className="flex flex-wrap gap-2">
            {checking
              ? [1, 2, 3].map((i) => <div key={i} className="skeleton h-9 w-[110px] rounded-control" />)
              : free.map((r) => {
                  const selected = form.room === r.id;
                  // Arriving today: a room still being cleaned can be booked but not checked into yet.
                  const status = roomStatus[r.id];
                  const notReady = form.check_in_date === today && status && status !== "ready" ? status : null;
                  return (
                    <button
                      key={r.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => update({ room: selected ? null : r.id })}
                      className={`inline-flex h-9 items-center gap-2 rounded-control border px-3.5 font-sans text-body font-semibold ${
                        selected ? "border-primary bg-primary-soft text-primary" : "border-border-strong bg-bg-surface text-text-primary hover:bg-bg-surface-2"
                      }`}
                    >
                      <span>{digits(r.number)}</span>
                      <span className={`text-label font-normal ${selected ? "text-primary" : "text-text-secondary"}`}>
                        {t("newRes.floor", { n: digits(String(r.floor)) })}
                      </span>
                      {notReady && <span className={`text-label font-normal ${stateColor(notReady as RoomState).text}`}>{t(`roomState.${notReady}`)}</span>}
                    </button>
                  );
                })}
          </div>
          {errors.room && <span className="text-label font-normal text-danger">{errors.room}</span>}
        </div>
      </div>

      <div className="grid grid-cols-4 items-end gap-3">
        <Field label={t("newRes.arrival")}>
          <TextInput type="date" min={today} value={form.check_in_date} onChange={(e) => e.target.value && update({ check_in_date: e.target.value, room: null })} />
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("newRes.durationKind")}</span>
          <Segmented<Kind>
            label={t("newRes.durationKind")}
            value={form.duration_kind}
            onChange={(v) => update({ duration_kind: v, option_key: null, price: null, room: null })}
            options={(["daily", "weekly", "monthly"] as const).map((k) => ({ value: k, label: t(`duration.${k}`) }))}
          />
        </div>
        <Field label={t("newRes.count")} className="max-w-[140px]">
          <TextInput
            inputMode="numeric"
            value={countText}
            invalid={!/^\d+$/.test(countText) || Number(countText) < 1 || Number(countText) > 366}
            onChange={(e) => {
              const text = toWestern(e.target.value).replace(/\D/g, "").slice(0, 3);
              setCountText(text);
              const n = Number(text);
              if (n >= 1 && n <= 366 && n !== form.count) update({ count: n, option_key: null, price: null, room: null });
            }}
            onBlur={() => setCountText(String(form.count))}
          />
        </Field>
      </div>

      {quote && (
        <div className="flex items-center gap-2 rounded-control bg-bg-surface-2 px-3 py-2.5 text-section-title">
          <CalendarCheck className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          {t("newRes.endsLine", { date: formatDayDate(quote.last_night), nights: nights(quote.nights) })}
        </div>
      )}

      {quote && quote.options.length > 1 && (
        <div className="flex flex-col gap-2">
          <span className="text-label text-text-secondary">
            {t("newRes.choosePricing", {
              nights: nights(quote.nights),
              ways: quote.options.length === 2 ? t("count.ways2") : t("count.waysMany", { n: digits(String(quote.options.length)) }),
            })}
          </span>
          <div role="radiogroup" className="grid max-w-[760px] grid-cols-2 gap-3">
            {quote.options.map((o) => {
              const selected = (form.option_key ?? quote.options[0].key) === o.key;
              return (
                <button
                  key={o.key}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => update({ option_key: o.key, price: null })}
                  className={`flex h-14 items-center gap-3 rounded-control border px-4 text-start font-sans ${
                    selected ? "border-primary bg-primary-soft" : "border-border-strong bg-bg-surface hover:bg-bg-surface-2"
                  }`}
                >
                  <span
                    className={`h-[18px] w-[18px] flex-none rounded-full bg-bg-surface ${selected ? "border-[5px] border-primary" : "border-2 border-border-strong"}`}
                  />
                  <span className="flex-1">
                    <span className="block text-body font-semibold leading-5 text-text-primary">{o.label}</span>
                    <span className="block text-label font-normal text-text-secondary">{digits(o.formula)}</span>
                  </span>
                  <span className="text-section-title text-text-primary">
                    {formatMoney(o.total)} <span className="text-label text-text-secondary">{t("money.currency")}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </Section>
  );
}
