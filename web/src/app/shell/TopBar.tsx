import { useQuery } from "@tanstack/react-query";
import { Bell, ChevronDown, LogOut, Search, UserRound, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, data } from "@/api/client";
import { useRoomBoard } from "@/features/rooms/RoomBoardPage";
import { digits, toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";
import { setSoundMuted, soundMuted } from "@/lib/alertSound";

type Props = {
  userName: string;
  roleName: string;
  /** `null` when no shift is open on this device. */
  shift: { userName: string; since: string } | null;
  backup: { kind: "ok"; when: string } | { kind: "stale"; hours: number } | { kind: "never" };
  alerts: number;
  onLogout: () => void;
};

/** «Shell TopBar»: 56 px; search, shift chip, backup chip, alerts, user. */
export function TopBar({ userName, roleName, shift, backup, alerts, onLogout }: Props) {
  const backupChip =
    backup.kind === "stale"
      ? { text: t("topbar.backupStale", { hours: digits(String(backup.hours)) }), tone: "bg-danger-soft text-danger-text" }
      : backup.kind === "ok"
        ? { text: t("topbar.backupAt", { when: backup.when }), tone: "bg-success-soft text-success-text" }
        : { text: t("topbar.backupNever"), tone: "bg-danger-soft text-danger-text" };

  return (
    <header className="flex h-topbar flex-none items-center gap-3 border-b border-border bg-bg-surface px-6">
      <GlobalSearch />

      <span
        className={`inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-control px-2.5 text-label ${
          shift ? "bg-success-soft text-success-text" : "bg-bg-surface-2 text-text-secondary"
        }`}
      >
        <span className={`h-2 w-2 rounded-full ${shift ? "bg-success" : "bg-text-disabled"}`} />
        {shift
          ? t("topbar.shiftOpen", { name: shift.userName.split(" ")[0], time: shift.since })
          : t("topbar.shiftNone")}
      </span>

      <div className="flex-1" />

      <span className={`inline-flex h-7 items-center whitespace-nowrap rounded-control px-2.5 text-label ${backupChip.tone}`}>
        {backupChip.text}
      </span>

      <SoundToggle />
      <Link
        to="/followups"
        aria-label={t("topbar.alerts")}
        className="relative flex h-9 w-9 items-center justify-center rounded-control border border-transparent text-text-primary hover:bg-bg-surface-2 hover:text-text-primary"
      >
        <Bell className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
        {alerts > 0 && (
          <span className="absolute start-0 top-0 box-content inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full border-2 border-bg-surface bg-danger px-[5px] text-[11px] font-semibold text-primary-text-on">
            {digits(String(alerts))}
          </span>
        )}
      </Link>

      <UserMenu userName={userName} roleName={roleName} onLogout={onLogout} />
    </header>
  );
}

type Hit = { key: string; kind: "room" | "guest"; title: string; sub: string; to: string };

/**
 * The top-bar search (brief: «رقم الغرفة أو الاسم أو الهاتف»): rooms come from the board already in memory, guests
 * from `guests/?q=`. Enter opens the highlighted hit; `/` focuses the box from anywhere; Esc clears it.
 */
function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const term = q.trim();
  const western = toWestern(term);
  const board = useRoomBoard().data;
  const guests = useQuery({
    queryKey: ["guests", "search", term],
    queryFn: () => data(api.GET("/api/v1/guests/", { params: { query: { q: term, page_size: 6 } as never } })),
    enabled: term.length >= 2,
    staleTime: 30_000,
  }).data;

  useEffect(() => {
    // Keyboard shortcuts outside fields and dialogs: `/` search, `n` new reservation.
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
      if (typing || e.ctrlKey || e.metaKey || e.altKey || document.querySelector("[role=dialog]")) return;
      if (e.key === "/") {
        e.preventDefault();
        input.current?.focus();
      } else if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        navigate("/reservations/new");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  const rooms: Hit[] = /^\d+$/.test(western)
    ? (board?.rooms ?? [])
        .filter((r) => r.number.startsWith(western))
        .slice(0, 5)
        .map((r) => ({
          key: `room-${r.id}`,
          kind: "room",
          title: t("topbar.roomHit", { n: digits(r.number) }),
          sub: r.stay ? r.stay.guest_name : t(`roomState.${r.display_status}`),
          to: r.stay ? `/stays/${r.stay.id}` : `/?room=${r.id}`,
        }))
    : [];
  const people: Hit[] = (guests?.results ?? []).map((g) => ({
    key: `guest-${g.id}`,
    kind: "guest",
    title: g.full_name,
    sub: [g.phone, g.in_house && g.last_stay ? t("topbar.inRoom", { n: digits(g.last_stay.room) }) : ""].filter(Boolean).join(" · "),
    to: `/guests?select=${g.id}&q=${encodeURIComponent(term)}`,
  }));
  const hits = [...rooms, ...people];
  const showList = open && term.length > 0;

  const go = (hit: Hit) => {
    setQ("");
    setOpen(false);
    navigate(hit.to);
  };

  return (
    <div className="relative">
      <div className="flex h-9 w-[360px] items-center gap-2 rounded-control border border-border-strong bg-bg-surface px-3 text-body focus-within:border-primary max-[1599px]:w-72">
        <Search className="h-icon w-icon flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
        <input
          ref={input}
          role="combobox"
          aria-label={t("topbar.search")}
          aria-expanded={showList}
          aria-controls="topbar-search-list"
          aria-autocomplete="list"
          placeholder={t("topbar.search")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            setCursor(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setCursor((c) => Math.min(c + 1, hits.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            } else if (e.key === "Enter" && hits[cursor]) {
              go(hits[cursor]);
            } else if (e.key === "Escape") {
              setQ("");
              setOpen(false);
              input.current?.blur();
            }
          }}
          className="w-full border-0 bg-transparent p-0 font-sans text-body text-text-primary outline-none placeholder:text-text-disabled"
        />
        <kbd className="rounded border border-border px-1 text-[11px] font-normal text-text-disabled">/</kbd>
      </div>
      {showList && (
        <ul
          id="topbar-search-list"
          role="listbox"
          className="absolute start-0 top-10 z-30 m-0 w-[360px] list-none overflow-hidden rounded-card border border-border bg-bg-surface p-1 shadow-elevated"
        >
          {hits.length === 0 && (
            <li className="px-3 py-2 text-body text-text-secondary">{term.length < 2 && !rooms.length ? t("topbar.typeMore") : t("topbar.noHits")}</li>
          )}
          {hits.map((hit, i) => (
            <li
              key={hit.key}
              role="option"
              aria-selected={i === cursor}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => go(hit)}
              onMouseEnter={() => setCursor(i)}
              className={`flex h-10 cursor-pointer items-center gap-3 rounded-control px-3 ${i === cursor ? "bg-primary-soft" : ""}`}
            >
              <span className="text-body font-medium text-text-primary">{hit.title}</span>
              <span className="min-w-0 flex-1 truncate text-label font-normal text-text-secondary">{hit.sub}</span>
              <span className="text-label font-normal text-text-disabled">{t(hit.kind === "room" ? "topbar.kindRoom" : "topbar.kindGuest")}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The user button opens a small menu: who is signed in, and «تسجيل الخروج» (the sidebar keeps its own). */
function UserMenu({ userName, roleName, onLogout }: { userName: string; roleName: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 items-center gap-2 rounded-control border border-transparent bg-transparent pe-2 ps-3 text-body text-text-primary hover:bg-bg-surface-2"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-soft text-label font-semibold text-primary">
          {userName.trim().charAt(0)}
        </span>
        <span>{userName}</span>
        <ChevronDown className="h-icon-inline w-icon-inline text-text-secondary" strokeWidth={1.75} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute end-0 top-10 z-30 w-56 overflow-hidden rounded-card border border-border bg-bg-surface p-1 shadow-elevated">
          <div className="flex items-center gap-3 px-3 py-2">
            <UserRound className="h-icon w-icon flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
            <div className="min-w-0">
              <div className="truncate text-body font-medium">{userName}</div>
              <div className="text-label font-normal text-text-secondary">{roleName}</div>
            </div>
          </div>
          <div className="my-1 h-px bg-border" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="flex h-9 w-full items-center gap-3 rounded-control border-0 bg-transparent px-3 text-start font-sans text-body text-text-primary hover:bg-bg-surface-2"
          >
            <LogOut className="h-icon w-icon flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
            {t("nav.logout")}
          </button>
        </div>
      )}
    </div>
  );
}

/** Alert sound on/off for this PC only (the owner chooses the sound itself in settings). */
function SoundToggle() {
  const [on, setOn] = useState(() => !soundMuted());
  const label = t(on ? "topbar.soundOn" : "topbar.soundOff");
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={on}
      onClick={() => {
        setSoundMuted(on);
        setOn(!on);
      }}
      className="flex h-9 w-9 items-center justify-center rounded-control border-0 bg-transparent text-text-secondary hover:bg-bg-surface-2 hover:text-text-primary"
    >
      {on ? <Volume2 className="h-icon w-icon" strokeWidth={1.75} aria-hidden /> : <VolumeX className="h-icon w-icon" strokeWidth={1.75} aria-hidden />}
    </button>
  );
}

