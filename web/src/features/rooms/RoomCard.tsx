import { StatusPill } from "@/components/ui/StatusPill";
import { reservedSoon as reservedSoonStyle } from "@/design/state";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { type BoardRoom, cardLines, reservedSoon, TONE_CLASS } from "./roomText";

type Props = { room: BoardRoom; boardDate: string; now: Date; selected: boolean; onOpen: () => void };

/**
 * Room card (6.2, 132 px high, width = grid column, min 190): number and type, the state as a soft pill with a dot,
 * then who is in the room and when that changes. No coloured side stripe (owner request 2026-10-18, decision 231).
 */
export function RoomCard({ room, boardDate, now, selected, onOpen }: Props) {
  const lines = cardLines(room, boardDate, now);
  const outline = selected
    ? "border-primary outline outline-2 -outline-offset-2 outline-primary"
    : reservedSoon(room, boardDate)
      ? `border-border ${reservedSoonStyle.outline}`
      : "border-border hover:border-border-strong hover:bg-bg-page";
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex h-room-card-h flex-col rounded-card border bg-bg-surface p-3.5 text-start font-sans text-text-primary transition-colors duration-150 ${outline}`}
    >
      <span className="flex w-full items-start justify-between gap-2">
        <span className="flex min-w-0 flex-col">
          <span className="text-room-number">{digits(room.number)}</span>
          <span className="truncate text-label font-normal text-text-secondary" title={room.name || undefined}>
            {room.name ? `${room.room_type_name} · ${room.name}` : room.room_type_name}
          </span>
        </span>
        <StatusPill state={room.display_status} label={t(`roomState.${room.display_status}`)} pulse={room.display_status === "overdue"} />
      </span>
      <span className="mt-auto flex w-full flex-col">
        <span className="truncate text-body font-medium leading-5">{lines.main || " "}</span>
        <span className={`text-label font-normal ${TONE_CLASS[lines.tone]}`}>{lines.sub || " "}</span>
      </span>
    </button>
  );
}

/** 6.2 D: loading skeleton card. */
export function RoomCardSkeleton() {
  return (
    <div className="flex h-room-card-h flex-col gap-2.5 rounded-card border border-border bg-bg-surface p-3.5">
      <div className="flex justify-between">
        <div className="skeleton h-6 w-12 rounded" />
        <div className="h-6 w-16 rounded-full bg-bg-surface-2" />
      </div>
      <div className="h-3 w-10 rounded bg-bg-surface-2" />
      <div className="skeleton mt-auto h-3.5 w-[70%] rounded" />
      <div className="h-3 w-[45%] rounded bg-bg-surface-2" />
    </div>
  );
}
