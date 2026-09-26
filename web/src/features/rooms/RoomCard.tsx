import { reservedSoon as reservedSoonStyle, stateColor } from "@/design/state";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { type BoardRoom, cardLines, reservedSoon, TONE_CLASS } from "./roomText";

type Props = { room: BoardRoom; boardDate: string; now: Date; selected: boolean; onOpen: () => void };

/** Room card (Design System «بطاقة الغرفة», 6.2): 132 px high, width = grid column (min 190, RTL exception 1). */
export function RoomCard({ room, boardDate, now, selected, onOpen }: Props) {
  const color = stateColor(room.display_status);
  const lines = cardLines(room, boardDate, now);
  const outline = selected
    ? "border-primary outline outline-2 -outline-offset-2 outline-primary"
    : reservedSoon(room, boardDate)
      ? `border-border ${reservedSoonStyle.outline}`
      : "border-border hover:border-border-strong";
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`relative flex h-room-card-h flex-col overflow-hidden rounded-card border bg-bg-surface py-3 pe-3 ps-4 text-start font-sans text-text-primary ${outline}`}
    >
      {/* State stripe on the start (right) edge. */}
      <span className={`absolute inset-y-0 start-0 w-1 ${color.solid}`} />
      <span className="flex w-full items-start justify-between gap-2">
        <span className="text-room-number">{digits(room.number)}</span>
        <span className={`inline-flex h-6 items-center whitespace-nowrap rounded-control px-2 text-label ${color.soft} ${color.text}`}>
          {t(`roomState.${room.display_status}`)}
        </span>
      </span>
      <span className="-mt-0.5 text-label font-normal text-text-secondary">{room.room_type_name}</span>
      <span className="mt-auto flex w-full flex-col">
        <span className="truncate text-body font-medium leading-5">{lines.main || " "}</span>
        <span className={`text-label ${TONE_CLASS[lines.tone]}`}>{lines.sub}</span>
      </span>
    </button>
  );
}

/** 6.2 D: loading skeleton card. */
export function RoomCardSkeleton() {
  return (
    <div className="flex h-room-card-h flex-col gap-2.5 rounded-card border border-border bg-bg-surface py-3 pe-3 ps-4">
      <div className="flex justify-between">
        <div className="skeleton h-6 w-12 rounded" />
        <div className="h-6 w-14 rounded-control bg-bg-surface-2" />
      </div>
      <div className="h-3 w-10 rounded bg-bg-surface-2" />
      <div className="skeleton mt-auto h-3.5 w-[70%] rounded" />
      <div className="h-3 w-[45%] rounded bg-bg-surface-2" />
    </div>
  );
}
