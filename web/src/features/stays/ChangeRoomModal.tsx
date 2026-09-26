import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { stateColor } from "@/design/state";
import { formatDayMonth } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

type Props = {
  stayId: string;
  version: number;
  guest: string;
  room: { number: string; floor: number; type: string };
  lastNight: string;
  onClose: () => void;
  onDone: () => void;
};

/** V2 «نافذة تغيير الغرفة»: same type first; a price drop for the remaining nights needs the manager. */
export function ChangeRoomModal({ stayId, version, guest, room, lastNight, onClose, onDone }: Props) {
  const options = useQuery({
    queryKey: ["change-room", stayId],
    queryFn: () => data(api.GET("/api/v1/stays/{id}/change-room", { params: { path: { id: stayId } } })),
  });
  const list = [...(options.data ?? [])].sort(
    (a, b) => Number(a.room.room_type_name !== room.type) - Number(b.room.room_type_name !== room.type) || a.room.number.localeCompare(b.room.number),
  );
  const [picked, setPicked] = useState<string | null>(null);
  const [after, setAfter] = useState<"cleaning" | "maintenance">("cleaning");
  const [maintenanceReason, setMaintenanceReason] = useState("");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const choice = list.find((o) => o.room.id === picked) ?? null;
  const needsManager = !!choice && choice.difference < 0;
  const ready = stateColor("ready");
  const can =
    !!choice && !!reason.trim() && (!needsManager || !!password) && (after === "cleaning" || !!maintenanceReason.trim()) && !busy;

  const submit = async () => {
    if (!choice) return;
    setBusy(true);
    setError(null);
    try {
      await data(
        api.POST("/api/v1/stays/{id}/change-room", {
          params: { path: { id: stayId } },
          body: {
            room: choice.room.id,
            reason: reason.trim(),
            old_room_status: after,
            maintenance_reason: maintenanceReason.trim(),
            override_password: needsManager ? password : "",
            override_reason: needsManager ? reason.trim() : "",
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

  const diff = choice?.difference ?? 0;
  return (
    <Modal
      title={t("changeRoom.title", { guest })}
      onClose={onClose}
      footer={
        <>
          <button type="button" disabled={!can} onClick={() => void submit()} className={buttons.primary}>
            {choice ? t("changeRoom.confirm", { room: digits(choice.room.number) }) : t("changeRoom.confirmNoRoom")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-card bg-bg-surface-2 px-4 py-3">
        <div>
          <div className="text-label text-text-secondary">{t("changeRoom.from")}</div>
          <div className="text-room-number">{digits(room.number)}</div>
          <div className="text-label font-normal text-text-secondary">{t("changeRoom.typeFloor", { type: room.type, floor: digits(String(room.floor)) })}</div>
        </div>
        <ArrowLeft className="h-icon w-icon text-text-secondary" strokeWidth={1.75} aria-hidden />
        <div>
          <div className="text-label text-text-secondary">{t("changeRoom.to")}</div>
          <div className="text-room-number">{choice ? digits(choice.room.number) : "—"}</div>
          <div className="text-label font-normal text-text-secondary">
            {choice
              ? `${t("changeRoom.typeFloor", { type: choice.room.room_type_name, floor: digits(String(choice.room.floor)) })} · ${t("changeRoom.ready")}`
              : t("changeRoom.pick")}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-label text-text-secondary">{t("changeRoom.freeRooms", { date: formatDayMonth(lastNight) })}</span>
        {options.isSuccess && list.length === 0 && <span className="text-body text-danger">{t("changeRoom.noRooms")}</span>}
        <div className="flex flex-wrap gap-2">
          {options.isLoading && [1, 2, 3].map((i) => <div key={i} className="skeleton h-9 w-[110px] rounded-control" />)}
          {list.map((o) => {
            const selected = o.room.id === picked;
            return (
              <button
                key={o.room.id}
                type="button"
                aria-pressed={selected}
                onClick={() => setPicked(o.room.id)}
                className={`inline-flex h-9 items-center gap-2 rounded-control border px-3.5 font-sans text-body font-semibold ${
                  selected ? "border-primary bg-primary-soft text-primary" : "border-border-strong bg-bg-surface text-text-primary hover:bg-bg-surface-2"
                }`}
              >
                <span>{digits(o.room.number)}</span>
                <span className={`text-label font-normal ${selected ? "text-primary" : "text-text-secondary"}`}>
                  {o.room.room_type_name === room.type ? t("changeRoom.typeFloor", { type: o.room.room_type_name, floor: digits(String(o.room.floor)) }) : o.room.room_type_name}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 border-t border-border pt-3">
        <div>
          <div className="text-label text-text-secondary">{t("changeRoom.difference")}</div>
          <div className={`text-section-title ${diff === 0 ? ready.text : diff > 0 ? "text-text-primary" : "text-warning-text"}`}>
            <span dir="ltr">{diff > 0 ? "+" : ""}{formatMoney(diff)}</span> {t("money.currency")}
          </div>
          <div className="text-label font-normal text-text-secondary">
            {diff === 0 ? t("changeRoom.sameType") : diff > 0 ? t("changeRoom.moreNights") : t("changeRoom.lessNights")}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <div className="text-label text-text-secondary">{t("changeRoom.oldStatus", { room: digits(room.number) })}</div>
          <div className="w-fit">
            <Segmented
              label={t("changeRoom.oldStatus", { room: digits(room.number) })}
              value={after}
              onChange={setAfter}
              options={[
                { value: "cleaning", label: t("roomState.cleaning") },
                { value: "maintenance", label: t("roomState.maintenance") },
              ]}
            />
          </div>
          {after === "maintenance" && (
            <TextInput aria-label={t("changeRoom.maintenanceReason")} placeholder={t("changeRoom.maintenanceReason")} value={maintenanceReason} onChange={(e) => setMaintenanceReason(e.target.value)} />
          )}
        </div>
      </div>

      <Field label={t("changeRoom.reason")} required>
        <TextInput value={reason} placeholder={t("changeRoom.reasonHint")} onChange={(e) => setReason(e.target.value)} />
      </Field>
      {needsManager && (
        <Field label={t("changeRoom.managerPassword")} required>
          <TextInput type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
      )}
      <div className="text-label font-normal text-text-secondary">{t("changeRoom.note")}</div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}
