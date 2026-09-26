import type { components } from "@api/schema";

import { reservedSoon as reservedSoonStyle, stateColor } from "@/design/state";
import { days, elapsed } from "@/i18n/counts";
import { t } from "@/i18n/t";

export type BoardRoom = components["schemas"]["RoomBoardRoom"];
export type Board = components["schemas"]["RoomBoard"];
export type DisplayStatus = BoardRoom["display_status"];

type Tone = "muted" | "ready" | "reserved" | "warning" | "danger";

/** Card lines 2–3 (6.2): who or what is in the room, and when that changes. Presentation of API fields only. */
export function cardLines(room: BoardRoom, boardDate: string, now: Date): { main: string; sub: string; tone: Tone } {
  const stay = room.stay;
  if (stay) {
    const d = stay.days_left;
    if (d < 0) return { main: stay.guest_name, sub: t("board.overdueSince", { days: days(-d) }), tone: "danger" };
    if (d === 0) return { main: stay.guest_name, sub: t("board.endsToday"), tone: "warning" };
    if (d === 1) return { main: stay.guest_name, sub: t("board.endsTomorrow"), tone: "muted" };
    return { main: stay.guest_name, sub: t("board.endsIn", { days: days(d) }), tone: "muted" };
  }
  const since = room.status_changed_at ? t("board.since", { time: elapsed(room.status_changed_at, now) }) : "";
  if (room.status === "cleaning") return { main: "", sub: since, tone: "muted" };
  if (room.status === "maintenance") return { main: room.maintenance_reason, sub: since, tone: "muted" };
  const soon = reservedSoon(room, boardDate);
  if (soon) {
    return {
      main: t("board.booking", { name: room.next_reservation!.guest_name }),
      sub: t(soon === "today" ? "board.reservedToday" : "board.reservedTomorrow"),
      tone: "reserved",
    };
  }
  return { main: "", sub: t("board.available"), tone: "ready" };
}

/** A ready room booked for today or tomorrow gets the «محجوزة قريبًا» outline. */
export function reservedSoon(room: BoardRoom, boardDate: string): "today" | "tomorrow" | null {
  const next = room.next_reservation;
  if (room.status !== "ready" || !next) return null;
  const inDays = Math.round((Date.parse(next.check_in_date) - Date.parse(boardDate)) / 86_400_000);
  return inDays === 0 ? "today" : inDays === 1 ? "tomorrow" : null;
}

export const TONE_CLASS: Record<Tone, string> = {
  muted: "text-text-secondary",
  ready: stateColor("ready").text,
  reserved: reservedSoonStyle.text,
  warning: "text-warning-text",
  danger: "text-danger",
};
