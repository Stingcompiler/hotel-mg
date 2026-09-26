import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, CalendarX, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { keys, useSystemStatus } from "@/api/queries";
import { ErrorBanner, Field, Segmented, Select, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { reservedSoon, stateColor } from "@/design/state";
import { useRoomBoard } from "@/features/rooms/RoomBoardPage";
import { formatDayMonth, formatRange } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { useMediaQuery } from "@/lib/useMediaQuery";

type Reservation = components["schemas"]["Reservation"];
type Status = Reservation["status"];

const DAY = 86_400_000;
const toTime = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
const addDays = (iso: string, n: number) => new Date(toTime(iso) + n * DAY).toISOString().slice(0, 10);
const diffDays = (a: string, b: string) => Math.round((toTime(a) - toTime(b)) / DAY);
const DOW = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];

/** 6.3 Reservations: 14-day timeline (7 at 1366) where time moves to the left from today on the right, and a list. */
export function ReservationsPage() {
  const [params] = useSearchParams();
  const [view, setView] = useState<"timeline" | "list">(params.get("focus") ? "list" : "timeline");
  const [focus, setFocus] = useState<string | null>(params.get("focus"));
  return (
    <div className="flex h-full flex-col gap-4 p-6 max-[1599px]:gap-3">
      {view === "timeline" ? (
        <Timeline
          header={<ViewSwitch view={view} onChange={setView} />}
          onPick={(id) => {
            setFocus(id);
            setView("list");
          }}
        />
      ) : (
        <ListView header={<ViewSwitch view={view} onChange={setView} />} focus={focus} onFocus={setFocus} />
      )}
    </div>
  );
}

function ViewSwitch({ view, onChange }: { view: "timeline" | "list"; onChange: (v: "timeline" | "list") => void }) {
  return (
    <>
      <h1 className="m-0 text-page-title">{t("reservations.title")}</h1>
      <Segmented
        label={t("reservations.title")}
        value={view}
        onChange={onChange}
        options={[
          { value: "timeline", label: t("reservations.timeline") },
          { value: "list", label: t("reservations.list") },
        ]}
      />
    </>
  );
}

function NewButton() {
  const navigate = useNavigate();
  const offline = useSystemStatus().isError;
  return (
    <button type="button" disabled={offline} onClick={() => navigate("/reservations/new")} className={`${buttons.primary} h-9 px-4`}>
      <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
      {t("reservations.new")}
    </button>
  );
}

function useWindow(from: string | undefined, to: string | undefined) {
  return useQuery({
    queryKey: ["reservations", from, to],
    queryFn: () => data(api.GET("/api/v1/reservations/", { params: { query: { date_from: from!, date_to: to! } } })),
    enabled: !!from && !!to,
  });
}

function Timeline({ header, onPick }: { header: React.ReactNode; onPick: (id: string) => void }) {
  const navigate = useNavigate();
  const offline = useSystemStatus().isError;
  const board = useRoomBoard().data;
  const narrow = useMediaQuery("(max-width: 1599px)");
  const span = narrow ? 7 : 14;
  const today = board?.date;
  const [offset, setOffset] = useState(0);
  const [floor, setFloor] = useState<number | null>(null);
  const start = today ? addDays(today, offset) : undefined;
  const end = start ? addDays(start, span) : undefined;
  const list = useWindow(start, end).data ?? [];

  if (!board || !start || !end) return <div className="skeleton h-96 rounded-card" />;
  const days = Array.from({ length: span }, (_, i) => addDays(start, i));
  const floors = [...new Set(board.rooms.map((r) => r.floor))].sort((a, b) => a - b);
  const rooms = board.rooms.filter((r) => r.in_service && (floor === null || r.floor === floor));
  const pct = (n: number) => `${(n / span) * 100}%`;

  type Bar = { key: string; from: number; to: number; label: string; sub: string; tone: string; onClick?: () => void; conflict?: boolean };
  const barsFor = (roomId: string, room: (typeof rooms)[number]): Bar[] => {
    const bars: Bar[] = list
      .filter((r) => r.room === roomId && (r.status === "confirmed" || r.status === "checked_in"))
      .map((r) => {
        const overdue = r.status === "checked_in" && diffDays(r.check_out_date, today!) <= 0;
        const tone =
          r.status === "confirmed"
            ? `bg-bg-surface ${reservedSoon.border} ${reservedSoon.text}`
            : `${stateColor(overdue ? "overdue" : "occupied").solid} text-primary-text-on`;
        return {
          key: r.id,
          from: Math.max(diffDays(r.check_in_date, start), 0),
          // An overdue stay still holds the room: draw it through today.
          to: Math.min(overdue ? Math.max(diffDays(today!, start) + 1, diffDays(r.check_out_date, start)) : diffDays(r.check_out_date, start), span),
          label: r.guest_name,
          sub: r.status === "confirmed" ? (r.deposit ? t("reservations.depositSub", { amount: formatMoney(r.deposit) }) : t("reservations.stConfirmed")) : t(`duration.${r.duration_kind}`),
          tone,
          onClick: () => (r.stay ? navigate(`/stays/${r.stay}`) : onPick(r.id)),
        };
      })
      .filter((b) => b.to > b.from);
    // A booking drawn over another bar of the same room is flagged (e.g. an overdue stay running into it).
    for (const b of bars) b.conflict = bars.some((o) => o !== b && o.from < b.to && b.from < o.to);
    if (room.status === "maintenance") {
      const m = stateColor("maintenance");
      bars.push({ key: `m-${roomId}`, from: 0, to: 1, label: t("reservations.maintenance", { reason: room.maintenance_reason }), sub: "", tone: `${m.soft} ${m.text}` });
    }
    return bars;
  };

  return (
    <>
      <div className="flex h-9 items-center gap-3">
        {header}
        <div className="inline-flex h-9 items-center overflow-hidden rounded-control border border-border-strong bg-bg-surface">
          {/* The window moves back in time to the right and forward to the left (RTL notes «الزمن الأفقي»). */}
          <button type="button" aria-label={t("reservations.prev")} onClick={() => setOffset((o) => o - span)} className="flex h-9 w-9 items-center justify-center border-0 bg-bg-surface text-text-primary">
            <ChevronRight className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          </button>
          <span className="flex h-9 items-center border-x border-border px-3 text-body font-medium">{formatRange(start, addDays(end, -1))}</span>
          <button type="button" aria-label={t("reservations.next")} onClick={() => setOffset((o) => o + span)} className="flex h-9 w-9 items-center justify-center border-0 bg-bg-surface text-text-primary">
            <ChevronLeft className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
        <button type="button" onClick={() => setOffset(0)} className={`${buttons.secondary} h-9 px-3`}>
          {t("reservations.today")}
        </button>
        <div className="w-40">
          <Select aria-label={t("reservations.allFloors")} value={floor ?? ""} onChange={(e) => setFloor(e.target.value === "" ? null : Number(e.target.value))}>
            <option value="">{t("reservations.allFloors")}</option>
            {floors.map((f) => (
              <option key={f} value={f}>
                {t("reservations.floor", { n: digits(String(f)) })}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-4 text-label font-normal text-text-secondary max-[1599px]:hidden">
          <Legend tone={stateColor("occupied").solid} label={t("reservations.legendIn")} />
          <Legend tone={reservedSoon.border} label={t("reservations.legendConfirmed")} />
          <Legend tone={stateColor("overdue").solid} label={t("reservations.legendOverdue")} />
          <Legend tone={stateColor("maintenance").soft} label={t("reservations.legendMaintenance")} />
        </div>
        <NewButton />
      </div>

      <section className="grid min-h-0 flex-1 grid-cols-[120px_1fr] grid-rows-[48px_1fr] overflow-hidden rounded-card border border-border bg-bg-surface">
        <div className="flex items-center border-b border-e border-border bg-bg-surface-2 px-4 text-label text-text-secondary">{t("reservations.room")}</div>
        <div className="grid border-b border-border bg-bg-surface-2" style={{ gridTemplateColumns: `repeat(${span}, 1fr)` }}>
          {days.map((d) => {
            const isToday = d === today;
            return (
              <div key={d} className={`flex flex-col items-center justify-center border-s border-border text-label ${isToday ? "bg-primary-soft text-primary" : "text-text-secondary"}`}>
                <span className="font-medium">{DOW[new Date(toTime(d)).getUTCDay()]}</span>
                <span className={`text-body ${isToday ? "font-bold" : "font-medium"}`}>{digits(String(new Date(toTime(d)).getUTCDate()))}</span>
              </div>
            );
          })}
        </div>
        <div className="col-span-2 min-h-0 overflow-auto">
          <div className="grid grid-cols-[120px_1fr]">
            {rooms.map((room, i) => (
              <div key={room.id} className="contents">
                <div className={`flex h-14 items-center gap-2 border-b border-e border-border px-4 ${i % 2 ? "bg-bg-page" : "bg-bg-surface"}`}>
                  <span className="text-section-title font-bold">{digits(room.number)}</span>
                  <span className="text-label font-normal text-text-secondary">{room.room_type_name}</span>
                </div>
                <div className="relative h-14 border-b border-border">
                  <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${span}, 1fr)` }}>
                    {days.map((d) => {
                      const dow = new Date(toTime(d)).getUTCDay();
                      const weekend = dow === 5 || dow === 6;
                      // An empty day from today on starts a booking for this room on that day (artboard 6.3 «انقر يومًا فارغًا»).
                      const bookable = d >= today! && room.status !== "maintenance";
                      return bookable ? (
                        <button
                          key={d}
                          type="button"
                          disabled={offline}
                          aria-label={t("reservations.bookCell", { room: digits(room.number), date: formatDayMonth(d) })}
                          title={t("reservations.bookCell", { room: digits(room.number), date: formatDayMonth(d) })}
                          onClick={() => navigate(`/reservations/new?room=${room.id}&date=${d}`)}
                          className={`group border-0 border-s border-border p-0 ${weekend ? "bg-bg-page" : "bg-transparent"} hover:bg-primary-soft focus-visible:bg-primary-soft`}
                        >
                          <Plus className="mx-auto h-icon w-icon text-primary opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100" strokeWidth={1.75} aria-hidden />
                        </button>
                      ) : (
                        <div key={d} className={`border-s border-border ${weekend ? "bg-bg-page" : ""}`} />
                      );
                    })}
                  </div>
                  {offset <= 0 && offset > -span && <div className="absolute inset-y-0 z-[2] w-0.5 bg-primary" style={{ insetInlineStart: pct(-offset) }} />}
                  {barsFor(room.id, room).map((b) => (
                    <button
                      key={b.key}
                      type="button"
                      onClick={b.onClick}
                      title={b.label}
                      className={`absolute top-2.5 z-[1] flex h-9 items-center gap-2 overflow-hidden whitespace-nowrap rounded-control border-0 px-2.5 text-start font-sans text-label font-semibold ${b.tone} ${
                        b.conflict ? "z-[3] outline-dashed outline-2 outline-danger" : ""
                      }`}
                      style={{ insetInlineStart: `calc(${pct(b.from)} + 3px)`, width: `calc(${pct(b.to - b.from)} - 6px)` }}
                    >
                      <span className="truncate">{b.label}</span>
                      {b.sub && <span className="truncate font-medium opacity-85">{b.conflict ? t("reservations.conflict") : b.sub}</span>}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

function Legend({ tone, label }: { tone: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-3 w-3 rounded-sm ${tone}`} />
      {label}
    </span>
  );
}

type Range = "next2" | "month" | "last";

function rangeOf(kind: Range, today: string): [string, string] {
  const [y, m] = today.split("-").map(Number);
  const iso = (yy: number, mm: number, dd: number) => new Date(Date.UTC(yy, mm - 1, dd)).toISOString().slice(0, 10);
  if (kind === "next2") return [today, addDays(today, 14)];
  if (kind === "month") return [iso(y, m, 1), iso(y, m + 1, 1)];
  return [iso(y, m - 1, 1), iso(y, m, 1)];
}

const STATUS_FILTERS: { value: Status | "all"; label: string }[] = [
  { value: "confirmed", label: "reservations.stConfirmed" },
  { value: "checked_in", label: "reservations.stIn" },
  { value: "checked_out", label: "reservations.stOut" },
  { value: "cancelled", label: "reservations.stCancelled" },
  { value: "all", label: "reservations.stAll" },
];

function ListView({ header, focus, onFocus }: { header: React.ReactNode; focus: string | null; onFocus: (id: string | null) => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const offline = useSystemStatus().isError;
  const today = useRoomBoard().data?.date;
  const [range, setRange] = useState<Range>("next2");
  const [status, setStatus] = useState<Status | "all">(focus ? "all" : "confirmed");
  const [cancelling, setCancelling] = useState<Reservation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [from, to] = today ? rangeOf(range, today) : [undefined, undefined];
  const list = useWindow(from, to);
  const all = useMemo(() => list.data ?? [], [list.data]);
  const rows = all.filter((r) => status === "all" || r.status === status || (status === "cancelled" && r.status === "no_show"));
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["reservations"] });
    void queryClient.invalidateQueries({ queryKey: keys.roomBoard });
  };
  const act = useMutation({
    mutationFn: async ({ r, action }: { r: Reservation; action: "checkin" | "noshow" }) =>
      action === "checkin"
        ? data(api.POST("/api/v1/stays/check-in", { body: { reservation: r.id, version: r.version } }))
        : data(api.POST("/api/v1/reservations/{id}/no-show", { params: { path: { id: r.id } }, body: { version: r.version } })),
    onSuccess: (result, { action }) => {
      refresh();
      if (action === "checkin" && result && "id" in result) navigate(`/stays/${result.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  const GRID = "grid grid-cols-[120px_80px_1.5fr_1fr_1fr_100px_120px_140px_130px] items-center gap-3 px-4";
  const chip: Record<string, string> = {
    confirmed: `bg-bg-surface ${reservedSoon.border} ${reservedSoon.text}`,
    checked_in: `${stateColor("occupied").solid} text-primary-text-on`,
    checked_out: "bg-bg-surface-2 text-text-secondary",
    cancelled: "bg-bg-surface-2 text-text-disabled",
    no_show: "bg-bg-surface-2 text-text-disabled",
  };
  const statusLabel: Record<Status, string> = {
    confirmed: t("reservations.stConfirmed"),
    checked_in: t("reservations.stIn"),
    checked_out: t("reservations.stOut"),
    cancelled: t("reservations.stCancelled"),
    no_show: t("reservations.stNoShow"),
  };

  return (
    <>
      <div className="flex h-9 items-center gap-3">
        {header}
        <Segmented
          label={t("reservations.colStatus")}
          value={status}
          onChange={setStatus}
          options={STATUS_FILTERS.map((f) => ({
            value: f.value,
            label: `${t(f.label)} ${digits(String(f.value === "all" ? all.length : all.filter((r) => r.status === f.value).length))}`,
          }))}
        />
        <div className="w-60">
          <Select aria-label={t("reservations.rangeNext2")} value={range} onChange={(e) => setRange(e.target.value as Range)}>
            <option value="next2">{t("reservations.rangeNext2")}</option>
            <option value="month">{t("reservations.rangeMonth")}</option>
            <option value="last">{t("reservations.rangeLast")}</option>
          </Select>
        </div>
        <div className="flex-1" />
        <NewButton />
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
        <div className={`${GRID} h-10 flex-none bg-bg-surface-2 text-label text-text-secondary`}>
          {["colNo", "colRoom", "colGuest", "colArrival", "colDeparture", "colNights", "colKind", "colDeposit", "colStatus"].map((k) => (
            <div key={k} className={k === "colDeposit" ? "text-end" : ""}>
              {t(`reservations.${k}`)}
            </div>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {list.isSuccess && rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 p-10 text-center">
              <CalendarX className="h-10 w-10 text-text-disabled" strokeWidth={1.75} aria-hidden />
              <div className="text-body text-text-secondary">{t("reservations.empty")}</div>
              <div className="text-label font-normal text-text-disabled">{t("reservations.emptyHint")}</div>
            </div>
          )}
          {rows.map((r, i) => {
            const sel = r.id === focus;
            const dead = r.status === "cancelled" || r.status === "no_show";
            return (
              <div
                key={r.id}
                onClick={() => onFocus(sel ? null : r.id)}
                className={`${GRID} h-10 cursor-pointer border-b border-border text-table-cell ${sel ? "bg-primary-soft" : i % 2 ? "bg-bg-page" : "bg-bg-surface"} ${dead ? "text-text-secondary line-through" : ""}`}
              >
                <div dir="ltr" className="text-end text-label text-text-secondary">
                  {r.invoice}
                </div>
                <div className="font-semibold">{r.room_number ? digits(r.room_number) : t("reservations.noRoom")}</div>
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate">{r.guest_name}</span>
                  {r.status === "confirmed" && r.check_in_date === today && (
                    <span className="inline-flex h-5 flex-none items-center rounded-control bg-warning-soft px-1.5 text-label text-warning-text">{t("reservations.arrivesToday")}</span>
                  )}
                </div>
                {sel && !dead ? (
                  <div className="col-span-4 flex items-center gap-2 no-underline" onClick={(e) => e.stopPropagation()}>
                    {r.stay && (
                      <button type="button" onClick={() => navigate(`/stays/${r.stay}`)} className={`${buttons.secondary} h-8 px-3`}>
                        {t("reservations.openStay")}
                      </button>
                    )}
                    {r.status === "confirmed" && (
                      <>
                        <button
                          type="button"
                          disabled={offline || !r.room || !today || r.check_in_date > today || act.isPending}
                          onClick={() => act.mutate({ r, action: "checkin" })}
                          className={`${buttons.primary} h-8 px-3`}
                        >
                          {t("reservations.checkIn")}
                        </button>
                        <button type="button" disabled={offline} onClick={() => setCancelling(r)} className={`${buttons.secondary} h-8 px-3`}>
                          {t("reservations.cancel")}
                        </button>
                        <button type="button" disabled={offline || act.isPending} onClick={() => window.confirm(t("reservations.noShowConfirm")) && act.mutate({ r, action: "noshow" })} className={`${buttons.ghost} h-8 px-3`}>
                          {t("reservations.noShow")}
                        </button>
                      </>
                    )}
                  </div>
                ) : (
                  <>
                    <div>{formatDayMonth(r.check_in_date)}</div>
                    <div>{formatDayMonth(r.check_out_date)}</div>
                    <div>{digits(String(r.nights))}</div>
                    <div>{t(`duration.${r.duration_kind}`)}</div>
                  </>
                )}
                <div className="text-end">{r.deposit ? formatMoney(r.deposit) : "—"}</div>
                <div>
                  <span className={`inline-flex h-6 items-center rounded-control px-2 text-label no-underline ${chip[r.status]}`}>{statusLabel[r.status]}</span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex h-10 flex-none items-center justify-between border-t border-border px-4 text-label font-normal text-text-secondary">
          <span>{t("reservations.count", { n: digits(String(rows.length)) })}</span>
          <CalendarDays className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
        </div>
      </section>
      {cancelling && (
        <CancelReservationModal
          reservation={cancelling}
          onClose={() => setCancelling(null)}
          onDone={() => {
            setCancelling(null);
            refresh();
          }}
        />
      )}
    </>
  );
}

function CancelReservationModal({ reservation, onClose, onDone }: { reservation: Reservation; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cancel = useMutation({
    mutationFn: () => data(api.POST("/api/v1/reservations/{id}/cancel", { params: { path: { id: reservation.id } }, body: { reason: reason.trim(), version: reservation.version } })),
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  return (
    <Modal
      title={t("reservations.cancelTitle", { guest: reservation.guest_name })}
      onClose={onClose}
      width={480}
      footer={
        <>
          <button type="button" disabled={!reason.trim() || cancel.isPending} onClick={() => cancel.mutate()} className={buttons.danger}>
            {t("reservations.cancelConfirm")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="text-body">
        {reservation.room_number && `${digits(reservation.room_number)} · `}
        {formatRange(reservation.check_in_date, addDays(reservation.check_out_date, -1))}
      </div>
      <div className="text-body text-text-secondary">{t("reservations.cancelNote")}</div>
      <Field label={t("reservations.cancelReason")} required>
        <TextInput autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}
