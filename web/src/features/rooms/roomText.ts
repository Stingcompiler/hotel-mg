import type { components } from "@api/schema";

import { reservedSoon as reservedSoonStyle, stateColor } from "@/design/state";
import { days, elapsed } from "@/i18n/counts";
import { formatDayMonth } from "@/i18n/dates";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

export type BoardRoom = components["schemas"]["RoomBoardRoom"];
export type Board = components["schemas"]["RoomBoard"];
export type DisplayStatus = BoardRoom["display_status"];

export type Tone = "muted" | "ready" | "reserved" | "warning" | "danger";

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
  // The status label already says «جاهزة»: no second «متاحة» line (owner request 2026-10-18, decision 228).
  return { main: "", sub: "", tone: "muted" };
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

/** One fact in the card's info row: the value, its fixed caption under it, and its tone. */
export type InfoCell = { icon: "end" | "money" | "clock" | "booking"; value: string; caption: string; tone: Tone };

/**
 * The detailed card (owner request 2026-10-22, decision 235): one main line (the guest, the maintenance reason or the
 * coming booking), then an info row in fixed places — end of stay and balance for an occupied room, how long the
 * room has waited otherwise. Presentation of API fields only; a value the API does not give is «—».
 */
export function cardInfo(room: BoardRoom, boardDate: string, now: Date): { main: string; cells: InfoCell[] } {
  const stay = room.stay;
  if (stay) {
    const d = stay.days_left;
    // The caption says «نهاية الإقامة», so the value is only the when: «اليوم», «غدًا», «بعد 5 أيام».
    const end =
      d < 0
        ? { value: t("board.overdueSince", { days: days(-d) }), tone: "danger" as const }
        : d === 0
          ? { value: t("dates.today"), tone: "warning" as const }
          : d === 1
            ? { value: t("dates.tomorrow"), tone: "muted" as const }
            : { value: t("board.inDays", { days: days(d) }), tone: "muted" as const };
    const balance = stay.balance;
    return {
      main: stay.guest_name,
      cells: [
        { icon: "end", caption: t("board.capEnd"), ...end },
        {
          icon: "money",
          caption: t("board.capBalance"),
          value: balance === null || balance === undefined ? "—" : balance > 0 ? `${formatMoney(balance)} ${t("money.currency")}` : t("board.paid"),
          tone: balance && balance > 0 ? "danger" : "muted",
        },
      ],
    };
  }
  const since = room.status_changed_at ? elapsed(room.status_changed_at, now) : "—";
  if (room.status === "cleaning") {
    return { main: "", cells: [{ icon: "clock", value: since, caption: t("board.capWaitingCleaning"), tone: "muted" }] };
  }
  if (room.status === "maintenance") {
    return {
      main: room.maintenance_reason,
      cells: [{ icon: "clock", value: since, caption: t("board.capInMaintenance"), tone: "muted" }],
    };
  }
  const next = room.next_reservation;
  if (next) {
    const inDays = Math.round((Date.parse(next.check_in_date) - Date.parse(boardDate)) / 86_400_000);
    const when = inDays === 0 ? t("dates.today") : inDays === 1 ? t("dates.tomorrow") : formatDayMonth(next.check_in_date);
    return {
      main: t("board.booking", { name: next.guest_name }),
      cells: [{ icon: "booking", value: when, caption: t("board.capArrival"), tone: inDays <= 1 ? "reserved" : "muted" }],
    };
  }
  return { main: "", cells: [{ icon: "booking", value: t("board.noBooking"), caption: t("board.capNextBooking"), tone: "muted" }] };
}

export type CardAction = "openStay" | "extend" | "checkout" | "checkIn" | "checkInBooking" | "cleaned" | "openRoom" | "startMaintenance";

/**
 * The card's one visible action and its «…» menu, by room state (decision 235). Status moves only where the server
 * allows them (`manual_targets`); check-out and extension open the stay page, where their own checks and prices are.
 */
export function cardActions(room: BoardRoom, boardDate: string): { primary: CardAction; more: CardAction[] } {
  if (room.stay) return { primary: "openStay", more: ["extend", "checkout"] };
  const canMaintain = room.manual_targets.includes("maintenance") ? (["startMaintenance"] as CardAction[]) : [];
  if (room.status === "cleaning") {
    return room.manual_targets.includes("ready") ? { primary: "cleaned", more: canMaintain } : { primary: "openRoom", more: [] };
  }
  if (room.status === "maintenance") return { primary: "openRoom", more: [] };
  return { primary: reservedSoon(room, boardDate) === "today" ? "checkInBooking" : "checkIn", more: canMaintain };
}
