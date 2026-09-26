import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, CircleAlert, Info } from "lucide-react";
import { useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { stateColor } from "@/design/state";
import { nights } from "@/i18n/counts";
import { formatDayDate } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Kind = "daily" | "weekly" | "monthly";
type Props = {
  stayId: string;
  version: number;
  room: string;
  roomType: string;
  kind: Kind;
  currentLastNight: string;
  total: number;
  balance: number;
  onClose: () => void;
  onDone: (thenPay: boolean) => void;
};

const money = (v: number) => `${formatMoney(v)} ${t("money.currency")}`;

/** 6.5 D: extend — old end (struck) → new end, price difference, room availability, alert recalculation note. */
export function ExtendModal({ stayId, version, room, roomType, kind: initialKind, currentLastNight, total, balance, onClose, onDone }: Props) {
  const [kind, setKind] = useState<Kind>(initialKind);
  const [count, setCount] = useState(1);
  const [optionKey, setOptionKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const quote = useQuery({
    queryKey: ["extend-quote", stayId, kind, count],
    queryFn: () => data(api.POST("/api/v1/stays/{id}/extend/quote", { params: { path: { id: stayId } }, body: { duration_kind: kind, count } })),
    retry: false,
  });
  const q = quote.data;
  const option = q?.quote.options.find((o) => o.key === optionKey) ?? q?.quote.options[0];
  const diff = option?.total ?? 0;

  const submit = async (thenPay: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await data(
        api.POST("/api/v1/stays/{id}/extend", {
          params: { path: { id: stayId } },
          body: { duration_kind: kind, count, option_key: option?.key ?? null, version },
        }),
      );
      onDone(thenPay);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  const ok = !!q && q.room_available && !!option && !busy;
  const ready = stateColor("ready");
  return (
    <Modal
      title={t("extendDlg.title", { room: digits(room) })}
      onClose={onClose}
      footer={
        <>
          <button type="button" disabled={!ok} onClick={() => void submit(false)} className={buttons.primary}>
            {t("extendDlg.confirm")}
          </button>
          <button type="button" disabled={!ok} onClick={() => void submit(true)} className={buttons.secondary}>
            {t("extendDlg.confirmAndPay")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-[2fr_1fr] items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("extendDlg.kind")}</span>
          <Segmented<Kind>
            label={t("extendDlg.kind")}
            value={kind}
            onChange={(v) => {
              setKind(v);
              setOptionKey(null);
            }}
            options={(["daily", "weekly", "monthly"] as const).map((k) => ({ value: k, label: t(`duration.${k}`) }))}
          />
        </div>
        <Field label={t("extendDlg.count")}>
          <TextInput
            type="number"
            min={1}
            max={366}
            value={count}
            onChange={(e) => {
              setCount(Math.max(1, Math.min(366, Number(e.target.value) || 1)));
              setOptionKey(null);
            }}
          />
        </Field>
      </div>

      {q && (
        <>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-card bg-bg-surface-2 px-4 py-3">
            <div>
              <div className="text-label text-text-secondary">{t("extendDlg.currentEnd")}</div>
              <div className="text-section-title text-text-secondary line-through">{formatDayDate(currentLastNight)}</div>
            </div>
            {/* The arrow points left: forward in time in RTL (6.5 notes). */}
            <ArrowLeft className="h-icon w-icon text-text-secondary" strokeWidth={1.75} aria-hidden />
            <div>
              <div className="text-label text-text-secondary">{t("extendDlg.newEnd")}</div>
              <div className="text-section-title">{formatDayDate(q.quote.last_night)}</div>
              <div className="text-label font-normal text-text-secondary">
                {t("extendDlg.moreNights", { nights: nights(q.quote.nights), total: nights(q.total_nights) })}
              </div>
            </div>
          </div>

          <div className={`flex items-center gap-2 text-body font-medium ${q.room_available ? ready.text : "text-danger"}`}>
            {q.room_available ? (
              <CircleCheck className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
            ) : (
              <CircleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
            )}
            {t(q.room_available ? "extendDlg.roomFree" : "extendDlg.roomBusy", { room: digits(room) })}
          </div>

          {q.quote.options.length > 1 && (
            <div role="radiogroup" className="flex flex-col gap-2">
              <span className="text-label text-text-secondary">{t("extendDlg.choosePricing")}</span>
              {q.quote.options.map((o) => {
                const selected = option?.key === o.key;
                return (
                  <button
                    key={o.key}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setOptionKey(o.key)}
                    className={`flex h-12 items-center gap-3 rounded-control border px-4 text-start font-sans ${selected ? "border-primary bg-primary-soft" : "border-border-strong bg-bg-surface"}`}
                  >
                    <span className={`h-[18px] w-[18px] flex-none rounded-full bg-bg-surface ${selected ? "border-[5px] border-primary" : "border-2 border-border-strong"}`} />
                    <span className="flex-1 text-body font-semibold text-text-primary">{o.label}</span>
                    <span className="text-label text-text-secondary">{digits(o.formula)}</span>
                    <span className="text-body font-semibold text-text-primary">{money(o.total)}</span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="grid grid-cols-3 gap-3 border-t border-border pt-4">
            <div>
              <div className="text-label text-text-secondary">{t("extendDlg.difference")}</div>
              <div className="text-section-title">
                <span dir="ltr">+{formatMoney(diff)}</span> {t("money.currency")}
              </div>
              <div className="text-label font-normal text-text-secondary">{t("extendDlg.priceFrom", { type: roomType, kind: option?.label ?? "" })}</div>
            </div>
            <div>
              <div className="text-label text-text-secondary">{t("extendDlg.newTotal")}</div>
              <div className="text-section-title">{money(total + diff)}</div>
            </div>
            <div>
              <div className="text-label text-text-secondary">{t("extendDlg.remainingAfter")}</div>
              <div className="text-section-title text-danger">{money(balance + diff)}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-label font-normal text-text-secondary">
            <Info className="h-icon-inline w-icon-inline flex-none" strokeWidth={1.75} aria-hidden />
            {t("extendDlg.recalc")}
          </div>
        </>
      )}
      {quote.isError && <ErrorBanner>{(quote.error as Error).message}</ErrorBanner>}
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}

