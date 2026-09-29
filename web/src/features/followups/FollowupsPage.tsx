import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Clock, TriangleAlert } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useNavigate , useSearchParams } from "react-router-dom";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { keys, useSystemStatus } from "@/api/queries";
import { Segmented, Select, TextInput } from "@/components/ui/form";
import { stateColor } from "@/design/state";
import { formatTime, formatWhen } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

type TaskRow = components["schemas"]["TaskRow"];
type UpcomingRow = components["schemas"]["UpcomingRow"];
type Row = { kind: string; rule: string };

const boardKey = ["followups", "board"] as const;

function useBoard() {
  return useQuery({ queryKey: boardKey, queryFn: () => data(api.GET("/api/v1/followups/board")), refetchInterval: 30_000 });
}

const btn =
  "h-9 whitespace-nowrap rounded-control border border-border-strong bg-bg-surface px-3.5 font-sans text-body font-medium text-text-primary hover:bg-bg-surface-2 disabled:border-border disabled:text-text-disabled";

/** 6.6 Follow-ups: متأخرة / اليوم / القادمة (+ system alerts); every task stays until an explicit action. */
export function FollowupsPage() {
  const board = useBoard();
  const offline = useSystemStatus().isError;
  const [kind, setKind] = useState("all");
  const [rule, setRule] = useState("");
  const b = board.data;

  if (!b) return <FollowupsSkeleton />;
  const all: Row[] = [...b.late, ...b.today, ...b.system, ...b.upcoming];
  const rules = [...new Set(all.map((r) => r.rule).filter(Boolean))];
  const keep = (r: Row) => (kind === "all" || r.kind === t(`duration.${kind}`)) && (!rule || r.rule === rule);
  const late = b.late.filter(keep);
  const today = b.today.filter(keep);
  const system = b.system.filter(keep);
  const upcoming = b.upcoming.filter(keep);
  const nothingDue = !b.late.length && !b.today.length && !b.system.length;

  return (
    <div className="flex h-full min-h-[620px] flex-col gap-4 p-6 max-[1599px]:gap-3">
      <div className="flex h-9 items-center gap-6 max-[1599px]:gap-4">
        <h1 className="m-0 text-page-title">{t("followups.title")}</h1>
        <div className="flex gap-2">
          <CountChip tone="bg-danger-soft text-danger-text" label={t("followups.late")} n={b.counts.late} />
          <CountChip tone="bg-warning-soft text-warning-text" label={t("followups.today")} n={b.counts.today} />
          <CountChip tone="bg-bg-surface-2 text-text-secondary" label={t("followups.upcoming")} n={b.counts.upcoming} />
        </div>
        <div className="flex-1" />
        {offline && board.dataUpdatedAt > 0 && (
          <span className="text-body text-text-secondary">
            {t("followups.lastUpdate", { time: "" })}
            <span dir="ltr">{formatTime(new Date(board.dataUpdatedAt))}</span>
          </span>
        )}
        <div className="w-44">
          <Select aria-label={t("followups.allRules")} value={rule} onChange={(e) => setRule(e.target.value)}>
            <option value="">{t("followups.allRules")}</option>
            {rules.map((r) => (
              <option key={r} value={r}>
                {r.replace(/^قاعدة: /, "")}
              </option>
            ))}
          </Select>
        </div>
        <Segmented
          label={t("followups.allKinds")}
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: t("followups.allKinds") },
            { value: "daily", label: t("duration.daily") },
            { value: "weekly", label: t("duration.weekly") },
            { value: "monthly", label: t("duration.monthly") },
          ]}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto max-[1599px]:gap-3">
        {nothingDue && (
          <section className="flex flex-col items-center gap-2 rounded-card border border-border bg-bg-surface p-8 text-center">
            <CircleCheck className={`h-10 w-10 ${stateColor("ready").text}`} strokeWidth={1.75} aria-hidden />
            <div className="text-section-title">{t("followups.emptyTitle")}</div>
            {b.last_action && (
              <div className="text-body text-text-secondary">
                {t("followups.lastAction", { text: b.last_action.text, by: b.last_action.by, time: "" })}
                <span dir="ltr">{formatTime(b.last_action.at)}</span>
              </div>
            )}
          </section>
        )}
        {late.length > 0 && (
          <Group dot="bg-danger" title={t("followups.late")} subtitle={t("followups.lateSub")}>
            {late.map((r) => (
              <TaskLine key={r.id} row={r} late offline={offline} />
            ))}
          </Group>
        )}
        {today.length > 0 && (
          <Group dot="bg-warning" title={t("followups.today")} subtitle={t("followups.todaySub")}>
            {today.map((r) => (
              <TaskLine key={r.id} row={r} offline={offline} />
            ))}
          </Group>
        )}
        {system.length > 0 && (
          <Group dot="bg-info" title={t("followups.system")} subtitle={t("followups.systemSub")}>
            {system.map((r) => (
              <TaskLine key={r.id} row={r} offline={offline} />
            ))}
          </Group>
        )}
        {!offline && (
          <Group dot="bg-text-disabled" title={t("followups.upcoming")} subtitle={t("followups.upcomingSub")}>
            {upcoming.length ? (
              upcoming.map((r) => <UpcomingLine key={`${r.stay}-${r.alert_at}`} row={r} />)
            ) : (
              <div className="px-4 py-3 text-body text-text-secondary">{t("followups.noUpcoming")}</div>
            )}
          </Group>
        )}
      </div>
    </div>
  );
}

function CountChip({ tone, label, n }: { tone: string; label: string; n: number }) {
  return (
    <span className={`inline-flex h-8 items-center gap-2 rounded-control px-3 text-body font-medium ${tone}`}>
      {label} <span className="text-[16px] font-bold">{digits(String(n))}</span>
    </span>
  );
}

function Group({ dot, title, subtitle, children }: { dot: string; title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="flex flex-col rounded-card border border-border bg-bg-surface">
      <div className="flex h-11 items-center gap-3 border-b border-border px-4">
        <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
        <h2 className="m-0 text-section-title">{title}</h2>
        <span className="text-body text-text-secondary max-[1599px]:hidden">{subtitle}</span>
      </div>
      {children}
    </section>
  );
}

const LINE = "relative grid grid-cols-[72px_280px_1fr_auto] items-center gap-4 border-b border-border px-4 last:border-b-0 max-[1599px]:grid-cols-[64px_200px_1fr_auto]";

function RoomChip({ room, state }: { room: string | null; state: string }) {
  const color = stateColor(state === "overdue" ? "overdue" : "occupied");
  if (!room) return <span />;
  return <span className={`inline-flex h-8 items-center justify-center rounded-control text-body font-bold ${color.soft} ${color.text}`}>{digits(room)}</span>;
}

function GuestCell({ guest, kind, title }: { guest: string; kind: string; title?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="truncate text-body font-semibold">{guest || title}</span>
      {kind && <span className="inline-flex h-6 flex-none items-center rounded-control bg-bg-surface-2 px-2 text-label text-text-primary">{kind}</span>}
    </div>
  );
}

function TaskLine({ row, late = false, offline }: { row: TaskRow; late?: boolean; offline: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const focused = params.get("task") === row.id;
  const line = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focused) line.current?.scrollIntoView({ block: "center" });
  }, [focused]);
  const [pop, setPop] = useState<null | "snooze" | "waiting">(null);
  const [error, setError] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: (body: { action: "snooze" | "waiting" | "done"; until?: string | null; note?: string }) =>
      data(api.POST("/api/v1/followups/tasks/{id}/actions", { params: { path: { id: row.id } }, body: { ...body, version: row.version } })),
    onSuccess: () => {
      setPop(null);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: boardKey });
      void queryClient.invalidateQueries({ queryKey: keys.taskCount });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.error")),
  });
  const disabled = offline || act.isPending;
  const waiting = row.status === "waiting";
  const neglected = row.status === "neglected";

  return (
    <div ref={line} className={`${LINE} min-h-16 py-2 ${late ? "bg-danger-soft" : ""} ${focused ? "outline outline-2 -outline-offset-2 outline-primary" : ""}`}>
      <RoomChip room={row.room} state={row.room_state} />
      <GuestCell guest={row.guest} kind={row.kind} title={row.title} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className={`flex items-center gap-2 text-body font-medium leading-5 ${late ? "text-danger" : "text-text-primary"}`}>
          <span>{row.when || row.title}</span>
          {neglected && (
            <span className="inline-flex h-[22px] items-center gap-1 rounded-control bg-danger px-2 text-label font-semibold text-primary-text-on">
              <TriangleAlert className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {row.neglected_shift_user ? t("followups.neglected", { name: row.neglected_shift_user.split(" ")[0] }) : t("followups.neglectedNoShift")}
            </span>
          )}
          {waiting && row.next_at && (
            <span className="inline-flex h-[22px] items-center gap-1 rounded-control bg-warning-soft px-2 text-label text-warning-text">
              <Clock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("followups.waitingBadge", { time: "" })}
              <span dir="ltr">{formatTime(row.next_at)}</span>
            </span>
          )}
        </div>
        <div className="truncate text-label font-normal text-text-secondary">
          {row.rule}
          {row.note && ` · «${row.note}»`}
        </div>
        {error && <span className="text-label font-normal text-danger">{error}</span>}
      </div>
      <div className="flex items-center gap-2">
        {row.stay ? (
          <>
            <button type="button" disabled={disabled} onClick={() => navigate(`/stays/${row.stay}?action=extend`)} className={btn}>
              {t("followups.extend")}
            </button>
            <button type="button" disabled={disabled} onClick={() => navigate(`/stays/${row.stay}?action=checkout`)} className={btn}>
              {t("followups.confirmCheckout")}
            </button>
            <button type="button" disabled={disabled || !row.can_snooze} onClick={() => setPop(pop === "waiting" ? null : "waiting")} className={btn}>
              {t("followups.waiting")}
            </button>
          </>
        ) : (
          <button type="button" disabled={disabled} onClick={() => act.mutate({ action: "done" })} className={btn}>
            {t("followups.done")}
          </button>
        )}
        <button
          type="button"
          disabled={disabled || !row.can_snooze}
          aria-expanded={pop === "snooze"}
          onClick={() => setPop(pop === "snooze" ? null : "snooze")}
          className={`${btn} ${pop === "snooze" ? "border-primary bg-primary-soft text-primary" : ""}`}
        >
          {digits(row.snooze_label)}
        </button>
      </div>
      {pop && (
        <WhenPopover
          kind={pop}
          heading={pop === "snooze" ? t("followups.snoozeTo", { n: digits(String(row.snooze_count + 1)), max: digits(String(row.max_snoozes)) }) : t("followups.waitingTitle")}
          busy={act.isPending}
          onPick={(until, note) => act.mutate({ action: pop, until, note })}
          onClose={() => setPop(null)}
        />
      )}
    </div>
  );
}

function UpcomingLine({ row }: { row: UpcomingRow }) {
  const navigate = useNavigate();
  return (
    <div className={`${LINE} min-h-16 py-2`}>
      <RoomChip room={row.room} state={row.room_state} />
      <GuestCell guest={row.guest} kind={row.kind} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="text-body font-medium leading-5">{row.when}</div>
        <div className="truncate text-label font-normal text-text-secondary">
          {row.rule} · {t("followups.willAlert", { when: formatWhen(row.alert_at) })}
        </div>
      </div>
      <div className="flex gap-2">
        {row.stay && (
          <button type="button" onClick={() => navigate(`/stays/${row.stay}?action=extend`)} className={btn}>
            {t("followups.extend")}
          </button>
        )}
      </div>
    </div>
  );
}

const pad = (n: number) => String(n).padStart(2, "0");
const localInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** «تأجيل إلى» / «بانتظار الرد» choices, anchored under the row's action buttons on the end (left) side. */
function WhenPopover({
  kind,
  heading,
  busy,
  onPick,
  onClose,
}: {
  kind: "snooze" | "waiting";
  heading: string;
  busy: boolean;
  onPick: (untilIso: string, note: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [custom, setCustom] = useState<string | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => {
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const now = new Date();
  const inHours = (h: number) => new Date(now.getTime() + h * 3_600_000);
  const tomorrow9 = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 9, 0);
  const choices: [string, Date][] = [
    [t("followups.inHour"), inHours(1)],
    [t("followups.in3Hours"), inHours(3)],
    [t("followups.tomorrowMorning"), tomorrow9],
  ];
  const item = "flex h-9 w-full items-center justify-between rounded-control border-0 bg-transparent px-3 text-start font-sans text-body text-text-primary hover:bg-bg-surface-2 disabled:text-text-disabled";

  return (
    <div ref={ref} role="dialog" aria-label={heading} className="absolute end-4 top-14 z-30 flex w-72 flex-col rounded-card border border-border bg-bg-surface p-1 shadow-elevated">
      <div className="px-3 py-1.5 text-label text-text-secondary">{heading}</div>
      {kind === "waiting" && (
        <div className="px-2 pb-2">
          <TextInput aria-label={t("followups.waitingNote")} placeholder={t("followups.waitingNote")} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
      )}
      {choices.map(([label, when]) => (
        <button key={label} type="button" disabled={busy} onClick={() => onPick(when.toISOString(), note.trim())} className={item}>
          <span>{label}</span>
          <span dir="ltr" className="text-label font-normal text-text-secondary">
            {formatTime(when)}
          </span>
        </button>
      ))}
      {custom === null ? (
        <button type="button" onClick={() => setCustom(localInput(inHours(2)))} className={item}>
          {t("followups.customTime")}
        </button>
      ) : (
        <div className="flex gap-2 px-2 py-1">
          <TextInput type="datetime-local" value={custom} onChange={(e) => setCustom(e.target.value)} />
          <button type="button" disabled={busy || !custom} onClick={() => onPick(new Date(custom).toISOString(), note.trim())} className={btn}>
            {t("followups.apply")}
          </button>
        </div>
      )}
      {kind === "snooze" && <div className="mt-1 border-t border-border px-3 pb-1 pt-2 text-label font-normal text-text-secondary">{t("followups.snoozeNote")}</div>}
    </div>
  );
}

/** 6.6 D: loading. */
function FollowupsSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex h-9 items-center gap-6">
        <div className="h-6 w-28 rounded bg-bg-surface-2" />
        <div className="flex gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-8 w-24 rounded-control" />
          ))}
        </div>
      </div>
      {[1, 2, 3].map((g) => (
        <section key={g} className="flex flex-col gap-3 rounded-card border border-border bg-bg-surface p-4">
          <div className="h-4 w-32 rounded bg-bg-surface-2" />
          {[1, 2].map((i) => (
            <div key={i} className="skeleton h-10 w-full rounded" />
          ))}
        </section>
      ))}
    </div>
  );
}

