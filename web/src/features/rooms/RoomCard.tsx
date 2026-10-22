import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BedDouble,
  CalendarClock,
  CalendarPlus,
  Check,
  CircleCheck,
  Clock,
  type LucideIcon,
  LogOut,
  MoreHorizontal,
  NotebookText,
  Sparkles,
  UserPlus,
  Wallet,
  Wrench,
} from "lucide-react";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { api, ApiError, data } from "@/api/client";
import { keys } from "@/api/queries";
import { StatusPill } from "@/components/ui/StatusPill";
import { reservedSoon as reservedSoonStyle, stateTint } from "@/design/state";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";
import { notice } from "@/lib/notices";

import { type BoardRoom, type CardAction, cardActions, cardInfo, type InfoCell, reservedSoon, TONE_CLASS } from "./roomText";

type Props = {
  room: BoardRoom;
  boardDate: string;
  now: Date;
  selected: boolean;
  offline: boolean;
  /** Opens the room drawer; `maintenance` opens it on the maintenance-reason form. */
  onOpen: (start?: "maintenance") => void;
};

const CELL_ICON: Record<InfoCell["icon"], LucideIcon> = { end: CalendarClock, money: Wallet, clock: Clock, booking: CalendarClock };

const ACTION_ICON: Record<CardAction, LucideIcon> = {
  openStay: NotebookText,
  extend: CalendarPlus,
  checkout: LogOut,
  checkIn: UserPlus,
  checkInBooking: UserPlus,
  cleaned: Sparkles,
  openRoom: Wrench,
  startMaintenance: Wrench,
};

const footButton =
  "inline-flex h-9 items-center justify-center gap-1.5 rounded-control border border-border bg-bg-surface font-sans text-body font-medium text-text-primary hover:border-border-strong hover:bg-bg-surface-2 disabled:text-text-disabled";

/**
 * Room card (owner request 2026-10-22, decision 235; adapted from the owner's «Italica» brief): a surface tinted by the
 * state; the number, type and state; the guest (or the reason, or the coming booking); an info row in fixed places —
 * end of stay and balance — and a footer with one action for the state and a «…» menu for the rest. The card body and
 * the footer buttons are siblings, never a button inside a button. The open room has a teal frame and a check mark.
 */
export function RoomCard({ room, boardDate, now, selected, offline, onOpen }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const info = cardInfo(room, boardDate, now);
  const actions = cardActions(room, boardDate);
  const soon = reservedSoon(room, boardDate);

  const cleaned = useMutation({
    mutationFn: () =>
      data(api.POST("/api/v1/rooms/{id}/set-status", { params: { path: { id: room.id } }, body: { status: "ready", reason: "", version: room.version } })),
    onSuccess: () => notice(t("board.cleanedDone", { n: digits(room.number) })),
    onError: (e) => notice(e instanceof ApiError ? e.message : t("errors.error"), "info"),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: keys.roomBoard });
      void queryClient.invalidateQueries({ queryKey: ["rooms", room.id, "history"] });
    },
  });

  function run(action: CardAction) {
    const stay = room.stay;
    if (action === "openStay" && stay) navigate(`/stays/${stay.id}`);
    else if ((action === "extend" || action === "checkout") && stay) navigate(`/stays/${stay.id}?action=${action}`);
    else if (action === "checkIn") navigate(`/reservations/new?room=${room.id}`);
    else if (action === "checkInBooking" && room.next_reservation) navigate(`/reservations?focus=${room.next_reservation.id}`);
    else if (action === "cleaned") cleaned.mutate();
    else if (action === "startMaintenance") onOpen("maintenance");
    else onOpen();
  }

  const frame = selected
    ? "border-primary outline outline-2 -outline-offset-2 outline-primary"
    : soon
      ? `border-border ${reservedSoonStyle.outline}`
      : "border-border hover:border-border-strong";
  const label = (a: CardAction) => t(a === "openRoom" && room.status === "maintenance" ? "board.action.openRoomMaintenance" : `board.action.${a}`);
  const PrimaryIcon = ACTION_ICON[actions.primary];
  // Moves that change data wait for the server; opening a page or the drawer works offline too.
  const changes = (a: CardAction) => a === "cleaned" || a === "checkIn" || a === "checkInBooking";

  return (
    <div className={`surface-card relative flex h-room-card-h flex-col p-4 font-sans text-text-primary transition-colors duration-150 ${stateTint(room.display_status)} ${frame}`}>
      {selected && (
        <span className="absolute -top-2 -end-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-text-on">
          <Check className="h-4 w-4" strokeWidth={3} aria-hidden />
          <span className="sr-only">{t("board.selected")}</span>
        </span>
      )}
      <button
        type="button"
        onClick={() => onOpen()}
        aria-pressed={selected}
        className="flex min-h-0 flex-1 cursor-pointer flex-col rounded-control border-0 bg-transparent p-0 text-start font-sans text-text-primary"
      >
        <span className="flex w-full items-start justify-between gap-2">
          <span className="flex min-w-0 flex-col">
            <span className="text-room-number">{digits(room.number)}</span>
            <span className="truncate text-label font-normal text-text-secondary" title={room.name || undefined}>
              {room.name ? `${room.room_type_name} · ${room.name}` : room.room_type_name}
            </span>
          </span>
          <StatusPill bare state={room.display_status} label={t(`roomState.${room.display_status}`)} pulse={room.display_status === "overdue"} />
        </span>
        <span className="mt-1.5 truncate text-body font-semibold leading-6" title={info.main || undefined}>
          {info.main || " "}
        </span>
        <span className="mt-auto flex w-full items-stretch border-t border-border pt-2">
          {info.cells.map((cell, i) => {
            const Icon = cell.icon === "booking" && !room.next_reservation ? BedDouble : CELL_ICON[cell.icon];
            return (
              <span key={cell.icon} className={`flex min-w-0 flex-1 items-start gap-1.5 ${i > 0 ? "border-s border-border ps-2.5" : "pe-2"}`}>
                <Icon className="mt-0.5 h-icon-inline w-icon-inline flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
                <span className="flex min-w-0 flex-col">
                  <span className={`truncate text-body font-medium leading-5 ${cell.tone === "muted" ? "text-text-primary" : TONE_CLASS[cell.tone]}`}>
                    {cell.value}
                  </span>
                  <span className="truncate text-label font-normal text-text-secondary">{cell.caption}</span>
                </span>
              </span>
            );
          })}
        </span>
      </button>
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={(offline && changes(actions.primary)) || cleaned.isPending}
          onClick={() => run(actions.primary)}
          className={`${footButton} min-w-0 flex-1 px-3`}
        >
          {cleaned.isPending ? (
            <CircleCheck className="h-icon-inline w-icon-inline flex-none animate-pulse" strokeWidth={1.75} aria-hidden />
          ) : (
            <PrimaryIcon className="h-icon-inline w-icon-inline flex-none" strokeWidth={1.75} aria-hidden />
          )}
          <span className="truncate">{label(actions.primary)}</span>
        </button>
        {actions.more.length > 0 && (
          <MoreMenu
            title={t("board.more", { n: digits(room.number) })}
            items={actions.more.map((a) => ({ key: a, label: label(a), icon: ACTION_ICON[a], disabled: offline && a === "startMaintenance" }))}
            onPick={(a) => run(a as CardAction)}
          />
        )}
      </div>
    </div>
  );
}

type MenuItem = { key: string; label: string; icon: LucideIcon; disabled?: boolean };

/**
 * The card's «…» menu: a button and a small list placed next to it (in a portal, so the board's scroll box does not
 * clip it).
 * Arrow keys move, Escape or a click outside closes and gives focus back to the button.
 */
function MoreMenu({ title, items, onPick }: { title: string; items: MenuItem[]; onPick: (key: string) => void }) {
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const close = (refocus = true) => {
    setAt(null);
    if (refocus) button.current?.focus();
  };

  useEffect(() => {
    if (!at) return;
    list.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus({ preventScroll: true });
    const outside = (e: MouseEvent) => {
      if (!list.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) close(false);
    };
    const gone = () => close(false);
    document.addEventListener("mousedown", outside);
    window.addEventListener("resize", gone);
    document.addEventListener("scroll", gone, true);
    return () => {
      document.removeEventListener("mousedown", outside);
      window.removeEventListener("resize", gone);
      document.removeEventListener("scroll", gone, true);
    };
  }, [at]);

  function open() {
    const r = button.current!.getBoundingClientRect();
    const height = items.length * 40 + 12;
    // Below the button when there is room, else above; aligned to the button's end (the left edge in RTL).
    const top = r.bottom + 4 + height > window.innerHeight ? r.top - 4 - height : r.bottom + 4;
    setAt({ top, left: r.left });
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const buttons = [...(list.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      buttons[(i + step + buttons.length) % buttons.length]?.focus({ preventScroll: true });
    } else if (e.key === "Tab") close(false);
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-label={title}
        title={title}
        aria-haspopup="menu"
        aria-expanded={at !== null}
        onClick={() => (at ? close() : open())}
        className={`${footButton} w-10 flex-none`}
      >
        <MoreHorizontal className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
      </button>
      {at &&
        createPortal(
          <div
            ref={list}
            role="menu"
            aria-label={title}
            onKeyDown={onKey}
            style={{ top: at.top, left: at.left }}
            className="fade-in fixed z-30 flex min-w-44 flex-col rounded-card border border-border bg-bg-surface p-1.5 shadow-elevated"
          >
            {items.map(({ key, label, icon: Icon, disabled }) => (
              <button
                key={key}
                type="button"
                role="menuitem"
                disabled={disabled}
                onClick={() => {
                  close();
                  onPick(key);
                }}
                className="flex h-10 items-center gap-2.5 rounded-control border-0 bg-transparent px-3 text-start font-sans text-body text-text-primary hover:bg-bg-surface-2 focus-visible:bg-bg-surface-2 disabled:text-text-disabled"
              >
                <Icon className="h-icon-inline w-icon-inline flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
                {label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

/** Loading skeleton in the card's own shape (6.2 D). */
export function RoomCardSkeleton() {
  return (
    <div className="surface-card flex h-room-card-h flex-col gap-2.5 p-4">
      <div className="flex justify-between">
        <div className="skeleton h-6 w-12 rounded" />
        <div className="h-5 w-16 rounded-full bg-bg-surface-2" />
      </div>
      <div className="h-3 w-10 rounded bg-bg-surface-2" />
      <div className="skeleton h-3.5 w-[70%] rounded" />
      <div className="mt-auto h-8 w-full rounded bg-bg-surface-2" />
      <div className="h-9 w-full rounded-control bg-bg-surface-2" />
    </div>
  );
}
