import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LayoutGrid, List, Plus, SearchX, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, data } from "@/api/client";
import { keys, useSystemStatus } from "@/api/queries";
import { stateColor } from "@/design/state";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { useNow } from "@/lib/useNow";

import { RoomCard, RoomCardSkeleton } from "./RoomCard";
import { RoomDrawer } from "./RoomDrawer";
import { type BoardRoom, cardLines, TONE_CLASS } from "./roomText";

type Filter = "all" | "ready" | "occupied" | "cleaning" | "maintenance" | "overdue";

const FILTERS: { key: Exclude<Filter, "overdue">; label: string }[] = [
  { key: "all", label: "board.filterAll" },
  { key: "ready", label: "board.filterReady" },
  { key: "occupied", label: "board.filterOccupied" },
  { key: "cleaning", label: "board.filterCleaning" },
  { key: "maintenance", label: "board.filterMaintenance" },
];

function matches(room: BoardRoom, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "overdue") return room.display_status === "overdue";
  return room.status === filter; // «مشغولة» includes overdue rooms, as the artboard counts them
}

export function useRoomBoard() {
  return useQuery({
    queryKey: keys.roomBoard,
    queryFn: () => data(api.GET("/api/v1/rooms/board")),
    refetchInterval: 15_000, // spec §10.5
  });
}

/** 6.2 Room board: KPI tiles, filters, 30 room cards (grid or list), room drawer. */
export function RoomBoardPage() {
  const navigate = useNavigate();
  const board = useRoomBoard();
  const offline = useSystemStatus().isError;
  const now = useNow(60_000);
  const [filter, setFilter] = useState<Filter>("all");
  const [floor, setFloor] = useState<number | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [openId, setOpenId] = useState<string | null>(null);

  const rooms = board.data?.rooms.filter((r) => r.in_service) ?? [];
  const floors = useMemo(() => [...new Set(rooms.map((r) => r.floor))].sort((a, b) => a - b), [rooms]);
  const shown = rooms.filter((r) => matches(r, filter) && (floor === null || r.floor === floor));
  const count = (f: Filter) => rooms.filter((r) => matches(r, f)).length;
  const summary = board.data?.summary;
  const openRoom = board.data?.rooms.find((r) => r.id === openId) ?? null;

  const kpis = summary && [
    {
      label: t("board.kpiOccupied"),
      value: digits(String(summary.occupied)),
      suffix: `/${digits(String(summary.rooms))}`,
      hint: t("board.kpiOccupancy", { p: digits(String(summary.occupancy_percent)) }),
      active: filter === "occupied",
      onClick: () => setFilter(filter === "occupied" ? "all" : "occupied"),
    },
    {
      label: t("board.kpiArrivals"),
      value: digits(String(summary.arrivals_today)),
      hint: t("board.kpiArrivalsHint"),
      onClick: () => navigate("/reports/arrivals_departures"),
    },
    {
      label: t("board.kpiDepartures"),
      value: digits(String(summary.departures_today)),
      hint: t("board.kpiDeparturesHint"),
      onClick: () => navigate("/reports/arrivals_departures"),
    },
    {
      label: t("board.kpiOverdue"),
      value: digits(String(summary.overdue)),
      hint: t("board.kpiOverdueHint"),
      danger: summary.overdue > 0,
      active: filter === "overdue",
      onClick: () => setFilter(filter === "overdue" ? "all" : "overdue"),
    },
  ];

  const newButton = (
    <button
      type="button"
      disabled={offline}
      onClick={() => navigate("/reservations/new")}
      className="inline-flex h-9 items-center gap-2 rounded-control border-0 bg-primary px-4 font-sans text-body font-medium text-primary-text-on hover:bg-primary-hover disabled:bg-bg-surface-2 disabled:text-text-disabled"
    >
      <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
      {t("board.newReservation")}
    </button>
  );

  return (
    <div className="flex h-full flex-col">
      {summary && summary.overdue > 0 && (
        <div className="flex h-11 flex-none items-center gap-3 bg-danger-soft px-6 text-body font-medium text-danger-text">
          <TriangleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          <span>
            {summary.overdue === 1
              ? t("board.overdueBannerOne")
              : t("board.overdueBanner", { n: digits(String(summary.overdue)) })}
          </span>
          <button
            type="button"
            onClick={() => setFilter("overdue")}
            className="border-0 bg-transparent p-0 font-sans text-body font-medium text-danger-text underline"
          >
            {t("board.show")}
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-6 max-[1599px]:gap-3">
        <div className="flex h-9 items-center justify-between">
          <h1 className="m-0 text-page-title">{t("board.title")}</h1>
          {newButton}
        </div>

        <div className="grid grid-cols-4 gap-4 max-[1599px]:gap-3">
          {kpis
            ? kpis.map((k) => (
                <button
                  key={k.label}
                  type="button"
                  onClick={k.onClick}
                  aria-pressed={k.active ?? undefined}
                  className={`rounded-card border bg-bg-surface p-4 text-start font-sans text-text-primary hover:border-border-strong max-[1599px]:flex max-[1599px]:items-baseline max-[1599px]:justify-between max-[1599px]:gap-2 max-[1599px]:px-4 max-[1599px]:py-3 ${
                    k.active ? "border-primary outline outline-1 -outline-offset-1 outline-primary" : "border-border"
                  }`}
                >
                  <div className="text-label text-text-secondary">{k.label}</div>
                  <div className={`mt-1 text-headline-number max-[1599px]:mt-0 ${k.danger ? "text-danger" : ""}`}>
                    {k.value}
                    {k.suffix && <span className="text-[16px] font-medium text-text-secondary">{k.suffix}</span>}
                  </div>
                  <div className="mt-1 text-label font-normal text-text-secondary max-[1599px]:hidden">{k.hint}</div>
                </button>
              ))
            : [1, 2, 3, 4].map((i) => (
                <div key={i} className="flex h-[60px] items-center justify-between rounded-card border border-border bg-bg-surface px-4 py-3">
                  <div className="h-3 w-[72px] rounded bg-bg-surface-2" />
                  <div className="skeleton h-6 w-12 rounded" />
                </div>
              ))}
        </div>

        <div className="flex h-9 items-center gap-3">
          {board.data ? (
            <>
              <div className="inline-flex h-9 overflow-hidden rounded-control border border-border-strong bg-bg-surface" role="radiogroup">
                {FILTERS.map(({ key, label }) => {
                  const active = filter === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      onClick={() => setFilter(key)}
                      className={`flex items-center gap-1.5 border-0 border-border px-4 font-sans text-body [&:not(:first-child)]:border-s max-[1599px]:px-3 ${
                        active ? "bg-primary-soft font-semibold text-primary" : "bg-bg-surface font-normal text-text-primary hover:bg-bg-surface-2"
                      }`}
                    >
                      {t(label)}
                      <span className={`text-label font-normal ${active ? "text-primary" : "text-text-secondary"}`}>
                        {digits(String(count(key)))}
                      </span>
                    </button>
                  );
                })}
              </div>
              <label className="relative">
                <span className="sr-only">{t("board.allFloors")}</span>
                <select
                  value={floor ?? ""}
                  onChange={(e) => setFloor(e.target.value === "" ? null : Number(e.target.value))}
                  className={`h-9 min-w-40 appearance-none rounded-control border pe-9 ps-3 font-sans text-body max-[1599px]:min-w-36 ${
                    floor === null
                      ? "border-border-strong bg-bg-surface text-text-primary"
                      : "border-primary bg-primary-soft font-medium text-primary"
                  }`}
                >
                  <option value="">{t("board.allFloors")}</option>
                  {floors.map((f) => (
                    <option key={f} value={f}>
                      {t("board.floor", { n: digits(String(f)) })}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute end-3 top-2.5 h-icon-inline w-icon-inline text-text-secondary"
                  strokeWidth={1.75}
                  aria-hidden
                />
              </label>
              <div className="flex-1" />
              <div className="inline-flex h-9 overflow-hidden rounded-control border border-border-strong bg-bg-surface">
                {(["grid", "list"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    aria-label={t(v === "grid" ? "board.gridView" : "board.listView")}
                    aria-pressed={view === v}
                    onClick={() => setView(v)}
                    className={`flex w-10 items-center justify-center border-0 border-border [&:not(:first-child)]:border-s ${
                      view === v ? "bg-primary-soft text-primary" : "bg-bg-surface text-text-secondary"
                    }`}
                  >
                    {v === "grid" ? (
                      <LayoutGrid className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
                    ) : (
                      <List className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
                    )}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="h-9 w-[420px] rounded-control bg-bg-surface-2" />
              <div className="h-9 w-36 rounded-control bg-bg-surface-2" />
            </>
          )}
        </div>

        {!board.data ? (
          <div className="grid min-h-0 flex-1 grid-cols-[repeat(auto-fill,minmax(190px,1fr))] content-start gap-3 overflow-hidden">
            {Array.from({ length: 18 }, (_, i) => (
              <RoomCardSkeleton key={i} />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-card border border-dashed border-border-strong text-center">
            <SearchX className="h-10 w-10 text-text-disabled" strokeWidth={1.75} aria-hidden />
            <div className="text-body text-text-secondary">
              {t("board.empty", {
                what: t(`board.emptyWhat.${filter}`),
                floor: floor === null ? "" : t("board.emptyInFloor", { n: digits(String(floor)) }),
              })}
            </div>
            <button
              type="button"
              onClick={() => {
                setFilter("all");
                setFloor(null);
              }}
              className="h-9 rounded-control border border-border-strong bg-bg-surface px-4 font-sans text-body font-medium text-text-primary hover:bg-bg-surface-2"
            >
              {t("board.showAll")}
            </button>
          </div>
        ) : view === "grid" ? (
          <div className="grid min-h-0 flex-1 grid-cols-[repeat(auto-fill,minmax(190px,1fr))] content-start gap-3 overflow-auto">
            {shown.map((room) => (
              <RoomCard
                key={room.id}
                room={room}
                boardDate={board.data.date}
                now={now}
                selected={room.id === openId}
                onOpen={() => setOpenId(room.id)}
              />
            ))}
          </div>
        ) : (
          <RoomTable rooms={shown} boardDate={board.data.date} now={now} onOpen={setOpenId} />
        )}
      </div>

      {openRoom && board.data && (
        <RoomDrawer room={openRoom} boardDate={board.data.date} now={now} offline={offline} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function RoomTable({
  rooms,
  boardDate,
  now,
  onOpen,
}: {
  rooms: BoardRoom[];
  boardDate: string;
  now: Date;
  onOpen: (id: string) => void;
}) {
  const head = "h-table-row px-3 text-start text-label text-text-secondary";
  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-card border border-border bg-bg-surface">
      <table className="w-full border-collapse text-table-cell">
        <thead className="sticky top-0 bg-bg-surface-2">
          <tr>
            <th className={head}>{t("board.colRoom")}</th>
            <th className={head}>{t("board.colType")}</th>
            <th className={head}>{t("board.colState")}</th>
            <th className={head}>{t("board.colGuest")}</th>
            <th className={head}>{t("board.colNote")}</th>
            {/* Numeric columns align to the line end so the digits line up (RTL notes «الجداول»). */}
            <th className={`${head} text-end`}>{t("board.colBalance")}</th>
          </tr>
        </thead>
        <tbody>
          {rooms.map((room) => {
            const color = stateColor(room.display_status);
            const lines = cardLines(room, boardDate, now);
            return (
              <tr
                key={room.id}
                onClick={() => onOpen(room.id)}
                className="h-table-row cursor-pointer border-t border-border hover:bg-bg-surface-2"
              >
                <td className="px-3 font-semibold">{digits(room.number)}</td>
                <td className="px-3 text-text-secondary">{room.room_type_name}</td>
                <td className="px-3">
                  <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${color.soft} ${color.text}`}>
                    {t(`roomState.${room.display_status}`)}
                  </span>
                </td>
                <td className="px-3">{lines.main}</td>
                <td className={`px-3 ${TONE_CLASS[lines.tone]}`}>{lines.sub}</td>
                <td className="px-3 text-end">
                  {room.stay?.balance ? formatMoney(room.stay.balance) : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
