import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, DoorOpen, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError, data } from "@/api/client";
import { keys } from "@/api/queries";
import { stateColor, stateSolid } from "@/design/state";
import { days } from "@/i18n/counts";
import { formatDayMonth, formatRange, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import type { BoardRoom } from "./roomText";

type Props = { room: BoardRoom; boardDate: string; now: Date; offline: boolean; onClose: () => void };

const primary =
  "flex h-11 items-center justify-center gap-2 rounded-control border-0 bg-primary font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:bg-bg-surface-2 disabled:text-text-disabled";
const secondary =
  "flex h-11 items-center justify-center gap-2 rounded-control border border-border-strong bg-bg-surface font-sans text-body font-semibold text-text-primary hover:bg-bg-surface-2 disabled:text-text-disabled";

/** 6.2 B: 480 px drawer sliding from the end (left) side over a 24 % scrim. */
export function RoomDrawer({ room, boardDate, offline, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const color = stateColor(room.display_status);
  const stay = room.stay;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40">
      <div className="scrim-24 absolute inset-0" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={digits(room.number)}
        className="absolute inset-y-0 end-0 flex w-drawer flex-col rounded-s-modal bg-bg-surface shadow-elevated"
      >
        <div className="flex flex-col gap-3 border-b border-border px-6 py-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-headline-number">{digits(room.number)}</span>
              <span className="text-body text-text-secondary">
                {t("roomDrawer.typeFloor", { type: room.room_type_name, floor: digits(String(room.floor)) })}
              </span>
              <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${color.soft} ${color.text}`}>
                {t(`roomState.${room.display_status}`)}
              </span>
            </div>
            <button
              ref={closeRef}
              type="button"
              aria-label={t("roomDrawer.close")}
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2"
            >
              <X className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            </button>
          </div>
          {stay ? <StayBlock stay={stay} /> : <RoomBlock room={room} boardDate={boardDate} />}
        </div>

        {stay ? (
          <div className="flex flex-col gap-2 border-b border-border px-6 py-4">
            <Link to={`/stays/${stay.id}`} className={`${primary} hover:text-primary-text-on`}>
              <DoorOpen className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
              {t("roomDrawer.openStay")}
            </Link>
            <div className="grid grid-cols-2 gap-2">
              <Link to={`/stays/${stay.id}?action=extend`} className={`${secondary} hover:text-text-primary`}>
                {t("roomDrawer.extend")}
              </Link>
              <Link to={`/stays/${stay.id}?action=checkout`} className={`${secondary} hover:text-text-primary`}>
                {t("roomDrawer.checkout")}
              </Link>
            </div>
            {(stay.balance ?? 0) > 0 && <div className="text-label font-normal text-text-secondary">{t("roomDrawer.debtNote")}</div>}
          </div>
        ) : (
          <StatusActions room={room} offline={offline} />
        )}

        <History roomId={room.id} />

        {stay && (
          <div className="flex justify-start border-t border-border px-6 py-3">
            <Link to={`/stays/${stay.id}`} className="text-body font-medium">
              {t("roomDrawer.fullDetails")}
            </Link>
          </div>
        )}
      </aside>
    </div>
  );
}

function StayBlock({ stay }: { stay: NonNullable<BoardRoom["stay"]> }) {
  const d = stay.days_left;
  const statusLine =
    d < 0
      ? t("roomDrawer.endedOverdue", { date: formatDayMonth(stay.last_night), days: days(-d) })
      : d === 0
        ? t("roomDrawer.endsTodayLine")
        : t("roomDrawer.endsOn", { date: formatDayMonth(stay.last_night) });
  const balance = stay.balance ?? 0;
  return (
    <div className="flex items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="text-section-title">{stay.guest_name}</div>
        <div className="text-body text-text-secondary">
          {stay.guest_phone && (
            <>
              <span dir="ltr">{stay.guest_phone}</span>
              {" · "}
            </>
          )}
          {stay.duration_label} · {formatRange(stay.check_in_date, stay.last_night)}
        </div>
        <div className={`text-body font-medium ${d < 0 ? "text-danger" : d === 0 ? "text-warning-text" : "text-text-secondary"}`}>
          {statusLine}
        </div>
      </div>
      <div className="flex-none text-end">
        <div className="text-label text-text-secondary">{t("roomDrawer.remaining")}</div>
        <div className={`whitespace-nowrap text-headline-number ${balance > 0 ? "text-danger" : ""}`}>
          {formatMoney(balance)} <span className="text-[16px] font-semibold">{t("money.currency")}</span>
        </div>
      </div>
    </div>
  );
}

function RoomBlock({ room, boardDate }: { room: BoardRoom; boardDate: string }) {
  const next = room.next_reservation;
  return (
    <div className="flex flex-col gap-1 text-body">
      {room.status === "maintenance" && room.maintenance_reason && (
        <div>
          <span className="text-text-secondary">{t("roomDrawer.maintenanceReason")}: </span>
          {room.maintenance_reason}
        </div>
      )}
      {next && (
        <div>
          <span className="text-text-secondary">{t("roomDrawer.nextBooking")}: </span>
          {t("roomDrawer.nextBookingLine", {
            name: next.guest_name,
            kind: next.duration_label,
            date: next.check_in_date === boardDate ? t("dates.today") : formatDayMonth(next.check_in_date),
          })}
        </div>
      )}
    </div>
  );
}

function actionLabel(from: string, to: string): string {
  return to === "maintenance" ? t("roomDrawer.to_maintenance") : t(`roomDrawer.to_${to}_from_${from}`);
}

/** Buttons for the moves staff may make from the board (server-provided `manual_targets`, spec §6.3). */
function StatusActions({ room, offline }: { room: BoardRoom; offline: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const setStatus = useMutation({
    mutationFn: (body: { status: "ready" | "cleaning" | "maintenance"; reason: string }) =>
      data(
        api.POST("/api/v1/rooms/{id}/set-status", {
          params: { path: { id: room.id } },
          body: { ...body, version: room.version },
        }),
      ),
    onSuccess: () => {
      setAsking(false);
      setReason("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: keys.roomBoard });
      void queryClient.invalidateQueries({ queryKey: ["rooms", room.id, "history"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });

  const targets = room.manual_targets.filter((s) => s !== "occupied") as ("ready" | "cleaning" | "maintenance")[];
  const busy = setStatus.isPending || offline;

  return (
    <div className="flex flex-col gap-2 border-b border-border px-6 py-4">
      {room.status === "ready" && (
        <button type="button" disabled={offline} onClick={() => navigate(`/reservations/new?room=${room.id}`)} className={primary}>
          {t("roomDrawer.newReservationHere")}
        </button>
      )}
      {asking ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1.5 text-label text-text-secondary">
            {t("roomDrawer.maintenanceReason")}
            <input
              autoFocus
              value={reason}
              maxLength={200}
              placeholder={t("roomDrawer.maintenanceReasonHint")}
              onChange={(e) => setReason(e.target.value)}
              className="h-11 rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body text-text-primary"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={busy || !reason.trim()}
              onClick={() => setStatus.mutate({ status: "maintenance", reason })}
              className={primary}
            >
              {t("roomDrawer.confirm")}
            </button>
            <button type="button" onClick={() => setAsking(false)} className={secondary}>
              {t("roomDrawer.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <div className={`grid gap-2 ${targets.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
          {targets.map((to) => (
            <button
              key={to}
              type="button"
              disabled={busy}
              onClick={() => (to === "maintenance" ? setAsking(true) : setStatus.mutate({ status: to, reason: "" }))}
              className={room.status !== "ready" && to !== "maintenance" ? primary : secondary}
            >
              {actionLabel(room.status, to)}
            </button>
          ))}
        </div>
      )}
      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-control bg-danger-soft px-3 py-2.5 text-body font-medium text-danger-text">
          <CircleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          {error}
        </div>
      )}
    </div>
  );
}

function History({ roomId }: { roomId: string }) {
  const history = useQuery({
    queryKey: ["rooms", roomId, "history"],
    queryFn: () => data(api.GET("/api/v1/rooms/{id}/history", { params: { path: { id: roomId } } })),
  });
  const rows = history.data?.results ?? [];
  return (
    <div className="flex flex-1 flex-col gap-3 overflow-auto px-6 py-4">
      <div className="text-section-title">{t("roomDrawer.history")}</div>
      {history.isSuccess && rows.length === 0 && <div className="text-body text-text-secondary">{t("roomDrawer.historyEmpty")}</div>}
      {rows.map((h) => (
        <div key={h.id} className="flex items-start gap-3">
          <span className={`mt-1.5 h-2.5 w-2.5 flex-none rounded-full ${stateSolid(h.to_status)}`} />
          <div className="min-w-0 flex-1">
            <div className="text-body leading-5">
              {t("roomDrawer.historyTo", { state: t(`roomState.${h.to_status}`) })}
              {h.reason ? ` — ${h.reason}` : ""}
            </div>
            <div className="text-label font-normal text-text-secondary">
              {formatDayMonth(h.at)} · <span dir="ltr">{formatTime(h.at)}</span>
              {h.by_name ? ` · ${h.by_name}` : ""}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
