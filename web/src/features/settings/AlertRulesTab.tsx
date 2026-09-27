import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format } from "date-fns";
import { useEffect, useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { ErrorBanner, MoneyInput, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { days } from "@/i18n/counts";
import { formatDayDate, formatTime } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { formatMoney, parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { Cancelled, useConfirmGate } from "./confirm";
import { apiErrorText, Card, HeadRow, linkButton, smallButton } from "./shared";

type Rule = components["schemas"]["AlertRule"];
type Patch = components["schemas"]["PatchedAlertRuleUpdateRequest"];
const RULES = ["followups", "rules"] as const;
const GRID = "grid grid-cols-[110px_1fr_1fr_110px_1fr_110px_90px_110px] items-center gap-4 px-4";
const OTHER_GRID = "grid grid-cols-[1.6fr_1fr_1fr_90px_110px] items-center gap-4 px-4";
const DURATION_ORDER = ["daily", "weekly", "monthly"];
// Sample stay length for the preview line only («إقامة شهرية تنتهي …»).
const SAMPLE_NIGHTS: Record<string, number> = { daily: 1, weekly: 7, monthly: 30 };

const num = (text: string) => toWestern(text).replace(/\D/g, "");
const hhmm = (time: string) => time.slice(0, 5);
const before = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n === 0 ? t("settings.alerts.onEndDay") : t("settings.alerts.daysBefore", { d: days(n) });
const repeat = (h: number) => (h ? t("settings.alerts.everyHours", { h: digits(String(h)) }) : t("settings.alerts.noRepeat"));

/** 6.11 «قواعد التنبيه»: stay-ending rules edited in their row with a live preview; neglect limits; other alerts. */
export function AlertRulesTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const rules = useQuery({ queryKey: RULES, queryFn: () => data(api.GET("/api/v1/followups/rules")) });
  const [error, setError] = useState<string | null>(null);
  const { gate, modal } = useConfirmGate();
  const all = rules.data ?? [];
  const ending = all
    .filter((r) => r.trigger_kind === "stay_ending")
    .sort((a, b) => DURATION_ORDER.indexOf(a.duration_kind) - DURATION_ORDER.indexOf(b.duration_kind));
  const others = all.filter((r) => r.trigger_kind !== "stay_ending");

  const patch = useMutation({
    mutationFn: async (changes: { rule: Rule; body: Patch }[]) => {
      for (const { rule, body } of changes) {
        // Turning a rule off asks for the manager's password (spec §6.8); other edits go straight through.
        await gate(t("settings.alerts.actDisable", { name: rule.name }), (headers) =>
          data(api.PATCH("/api/v1/followups/rules/{id}", { params: { path: { id: rule.id } }, headers, body: { ...body, version: rule.version } })),
        );
      }
    },
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: RULES });
    },
    onError: (e) => {
      if (!(e instanceof Cancelled)) setError(apiErrorText(e));
      void queryClient.invalidateQueries({ queryKey: RULES });
    },
  });
  const save = (rule: Rule, body: Patch) => patch.mutateAsync([{ rule, body }]);

  if (rules.isSuccess && all.length === 0) {
    return <div className="rounded-card border border-border bg-bg-surface p-6 text-center text-body text-text-secondary">{t("settings.alerts.empty")}</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {modal}
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <Card title={t("settings.alerts.title")} note={t("settings.alerts.note")}>
        <HeadRow grid={GRID} labels={["type", "first", "second", "time", "repeat", "windows", "active", ""].map((k) => (k ? t(`settings.alerts.col_${k}`) : ""))} />
        {ending.map((rule) => (
          <EndingRow key={rule.id} rule={rule} readOnly={readOnly} busy={patch.isPending} onSave={save} />
        ))}
      </Card>
      <div className="grid grid-cols-2 items-start gap-4">
        <NeglectCard rules={ending} readOnly={readOnly} busy={patch.isPending} onSave={(body) => patch.mutateAsync(ending.map((rule) => ({ rule, body })))} />
        <Card title={t("settings.alerts.others")}>
          <HeadRow grid={OTHER_GRID} labels={["kind", "value", "repeat", "active", ""].map((k) => (k ? t(`settings.alerts.col_${k}`) : ""))} />
          {others.map((rule) => (
            <OtherRow key={rule.id} rule={rule} readOnly={readOnly} busy={patch.isPending} onSave={save} />
          ))}
        </Card>
      </div>
    </div>
  );
}

type RowProps = { rule: Rule; readOnly: boolean; busy: boolean; onSave: (rule: Rule, body: Patch) => Promise<unknown> };

function EndingRow({ rule, readOnly, busy, onSave }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ first: "", second: "", time: "", repeat: "" });
  const start = () => {
    setDraft({
      first: String(rule.days_before),
      second: rule.second_days_before === null ? "" : String(rule.second_days_before),
      time: hhmm(rule.at_time),
      repeat: String(rule.repeat_hours),
    });
    setEditing(true);
  };
  const body = (): Patch => ({
    days_before: Number(draft.first || 0),
    second_days_before: draft.second === "" ? null : Number(draft.second),
    at_time: draft.time || "09:00",
    repeat_hours: Number(draft.repeat || 0),
  });
  const toggle = (field: "windows_notification" | "is_active") => (value: boolean) => void onSave(rule, { [field]: value }).catch(() => undefined);

  if (!editing) {
    return (
      <div className={`${GRID} h-12 border-b border-border text-table-cell ${rule.is_active ? "" : "text-text-disabled"}`}>
        <div>
          <span className="inline-flex h-6 items-center rounded-control bg-bg-surface-2 px-2 text-label">{t(`duration.${rule.duration_kind}`)}</span>
        </div>
        <div>{before(rule.days_before)}</div>
        <div>{before(rule.second_days_before)}</div>
        <div dir="ltr" className="text-end">
          {digits(hhmm(rule.at_time))}
        </div>
        <div>{repeat(rule.repeat_hours)}</div>
        <Toggle checked={rule.windows_notification} disabled={readOnly || busy} label={t("settings.alerts.col_windows")} onChange={toggle("windows_notification")} />
        <Toggle checked={rule.is_active} disabled={readOnly || busy} label={t("settings.alerts.col_active")} onChange={toggle("is_active")} />
        <div>
          {!readOnly && (
            <button type="button" onClick={start} className={linkButton}>
              {t("settings.edit")}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="border-b border-border bg-primary-soft">
      <div className={`${GRID} min-h-16 py-2 text-table-cell`}>
        <div>
          <span className="inline-flex h-6 items-center rounded-control bg-bg-surface px-2 text-label">{t(`duration.${rule.duration_kind}`)}</span>
        </div>
        <DaysField label={t("settings.alerts.col_first")} value={draft.first} onChange={(first) => setDraft({ ...draft, first })} />
        <DaysField label={t("settings.alerts.col_second")} value={draft.second} placeholder="—" onChange={(second) => setDraft({ ...draft, second })} />
        <TextInput type="time" dir="ltr" aria-label={t("settings.alerts.col_time")} value={draft.time} onChange={(e) => setDraft({ ...draft, time: e.target.value })} />
        <label className="flex items-center gap-2">
          <TextInput
            aria-label={t("settings.alerts.col_repeat")}
            inputMode="numeric"
            className="w-20"
            value={draft.repeat}
            onChange={(e) => setDraft({ ...draft, repeat: num(e.target.value) })}
          />
          <span className="text-text-secondary">{t("settings.alerts.hours")}</span>
        </label>
        <div />
        <div />
        <div />
      </div>
      <div className="flex items-center gap-3 px-4 pb-3">
        <Preview rule={rule} body={body()} />
        <button
          type="button"
          disabled={busy}
          onClick={() => void onSave(rule, body()).then(() => setEditing(false), () => undefined)}
          className={smallButton("primary")}
        >
          {t("settings.alerts.saveRule")}
        </button>
        <button type="button" onClick={() => setEditing(false)} className={linkButton}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

function DaysField({ label, value, placeholder, onChange }: { label: string; value: string; placeholder?: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-2">
      <TextInput aria-label={label} inputMode="numeric" className="w-16" placeholder={placeholder} value={value} onChange={(e) => onChange(num(e.target.value))} />
      <span className="whitespace-nowrap text-text-secondary">{t("settings.alerts.daysBeforeEnd")}</span>
    </label>
  );
}

/** «معاينة»: the server turns the draft rule into real dates for a sample stay and counts affected stays. */
function Preview({ rule, body }: { rule: Rule; body: Patch }) {
  const [debounced, setDebounced] = useState(body);
  const text = JSON.stringify(body);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(JSON.parse(text) as Patch), 300);
    return () => window.clearTimeout(id);
  }, [text]);
  const nights = Math.max(SAMPLE_NIGHTS[rule.duration_kind] ?? 7, (debounced.days_before ?? 0) + 1);
  const lastNight = format(addDays(new Date(), nights), "yyyy-MM-dd");
  const preview = useQuery({
    queryKey: ["followups", "rules", "preview", rule.duration_kind, lastNight, debounced],
    queryFn: () =>
      data(
        api.POST("/api/v1/followups/rules/preview", {
          body: {
            last_night: lastNight,
            duration_kind: rule.duration_kind as components["schemas"]["BookingDurationKindEnum"],
            days_before: debounced.days_before ?? 0,
            second_days_before: debounced.second_days_before ?? null,
            at_time: debounced.at_time,
            repeat_hours: debounced.repeat_hours ?? 0,
          },
        }),
      ),
  });
  const p = preview.data;
  const at = (iso: string) => `${formatDayDate(iso)} ${digits(formatTime(iso))}`;
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 text-body">
      <span className="font-medium">{t("settings.alerts.previewFor", { kind: t(`duration.${rule.duration_kind}`), date: formatDayDate(lastNight) })}</span>
      {p && (
        <span className="text-text-secondary">
          {t("settings.alerts.previewFirst")} <strong className="text-text-primary">{at(p.first_at)}</strong>
          {p.second_at && (
            <>
              {" · "}
              {t("settings.alerts.previewSecond")} <strong className="text-text-primary">{at(p.second_at)}</strong>
            </>
          )}
          {" · "}
          {p.repeat_hours ? t("settings.alerts.previewRepeat", { h: digits(String(p.repeat_hours)) }) : t("settings.alerts.noRepeat")}
          {" · "}
          {t("settings.alerts.previewAffected", { n: digits(String(p.affected_stays)) })}
        </span>
      )}
      {p && p.stays.length > 0 && (
        <ul className="m-0 flex w-full list-none flex-wrap gap-x-3 gap-y-1 p-0 text-label font-normal text-text-secondary">
          {p.stays.map((s) => (
            <li key={`${s.room}-${s.guest}`} className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-5 items-center rounded-control bg-bg-surface-2 px-1.5 font-medium text-text-primary">{digits(s.room)}</span>
              {s.guest} · {formatDayDate(s.last_night)}
            </li>
          ))}
          {p.affected_stays > p.stays.length && <li>{t("settings.alerts.previewMore", { n: digits(String(p.affected_stays - p.stays.length)) })}</li>}
        </ul>
      )}
      {preview.isError && <span className="text-danger">{apiErrorText(preview.error)}</span>}
    </div>
  );
}

function NeglectCard({ rules, readOnly, busy, onSave }: { rules: Rule[]; readOnly: boolean; busy: boolean; onSave: (body: Patch) => Promise<unknown> }) {
  const first = rules[0];
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ hours: "", snoozes: "" });
  if (!first) return null;
  return (
    <Card
      title={t("settings.alerts.neglect")}
      actions={
        !readOnly &&
        !editing && (
          <button
            type="button"
            className={linkButton}
            onClick={() => {
              setDraft({ hours: String(first.escalate_after_hours), snoozes: String(first.max_snoozes) });
              setEditing(true);
            }}
          >
            {t("settings.edit")}
          </button>
        )
      }
    >
      <div className="grid grid-cols-2 gap-4 p-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("settings.alerts.neglectAfter")}</span>
          {editing ? (
            <label className="flex items-center gap-2">
              <TextInput inputMode="numeric" className="w-20" value={draft.hours} onChange={(e) => setDraft({ ...draft, hours: num(e.target.value) })} />
              <span className="text-text-secondary">{t("settings.alerts.hoursNoAction")}</span>
            </label>
          ) : (
            <span className="text-body font-medium">{t("settings.alerts.hoursNoActionN", { h: digits(String(first.escalate_after_hours)) })}</span>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-label text-text-secondary">{t("settings.alerts.maxSnoozes")}</span>
          {editing ? (
            <label className="flex items-center gap-2">
              <TextInput inputMode="numeric" className="w-20" value={draft.snoozes} onChange={(e) => setDraft({ ...draft, snoozes: num(e.target.value) })} />
              <span className="text-text-secondary">{t("settings.alerts.timesPerAlert")}</span>
            </label>
          ) : (
            <span className="text-body font-medium">{t("settings.alerts.timesPerAlertN", { n: digits(String(first.max_snoozes)) })}</span>
          )}
        </div>
      </div>
      {editing && (
        <div className="flex gap-2 px-4 pb-4">
          <button
            type="button"
            disabled={busy || !draft.hours || !draft.snoozes}
            className={smallButton("primary")}
            onClick={() =>
              void onSave({ escalate_after_hours: Number(draft.hours), max_snoozes: Number(draft.snoozes) }).then(() => setEditing(false), () => undefined)
            }
          >
            {t("settings.save")}
          </button>
          <button type="button" className={linkButton} onClick={() => setEditing(false)}>
            {t("common.cancel")}
          </button>
        </div>
      )}
      <div className="border-t border-border px-4 py-3 text-label font-normal text-text-secondary">{t("settings.alerts.neglectNote")}</div>
    </Card>
  );
}

const usesMoney = (rule: Rule) => rule.trigger_kind === "checkout_debt";
const usesHours = (rule: Rule) => rule.threshold_hours !== null && !usesMoney(rule);

function OtherRow({ rule, readOnly, busy, onSave }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [rep, setRep] = useState("");
  const shown = usesMoney(rule)
    ? rule.threshold
      ? t("settings.alerts.above", { amount: `${formatMoney(rule.threshold)} ${t("money.currency")}` })
      : t("settings.alerts.anyDebt")
    : usesHours(rule)
      ? t("settings.alerts.afterHours", { h: digits(String(rule.threshold_hours)) })
      : "—";
  const body = (): Patch =>
    usesMoney(rule)
      ? { threshold: parseMoney(value || "0") ?? 0, repeat_hours: Number(rep || 0) }
      : usesHours(rule)
        ? { threshold_hours: Number(value || 0), repeat_hours: Number(rep || 0) }
        : { repeat_hours: Number(rep || 0) };

  return (
    <div className={`${OTHER_GRID} min-h-12 border-b border-border py-1.5 text-table-cell ${editing ? "bg-primary-soft" : ""} ${rule.is_active ? "" : "text-text-disabled"}`}>
      <div>{t(`settings.alerts.kind_${rule.trigger_kind}`)}</div>
      <div>
        {editing && usesMoney(rule) ? (
          <MoneyInput aria-label={t("settings.alerts.col_value")} value={value} onChange={(e) => setValue(e.target.value)} />
        ) : editing && usesHours(rule) ? (
          <label className="flex items-center gap-2">
            <TextInput aria-label={t("settings.alerts.col_value")} inputMode="numeric" className="w-20" value={value} onChange={(e) => setValue(num(e.target.value))} />
            <span className="text-text-secondary">{t("settings.alerts.hours")}</span>
          </label>
        ) : (
          shown
        )}
      </div>
      <div>
        {editing ? (
          <label className="flex items-center gap-2">
            <TextInput aria-label={t("settings.alerts.col_repeat")} inputMode="numeric" className="w-16" value={rep} onChange={(e) => setRep(num(e.target.value))} />
            <span className="text-text-secondary">{t("settings.alerts.hours")}</span>
          </label>
        ) : (
          repeat(rule.repeat_hours)
        )}
      </div>
      <Toggle
        checked={rule.is_active}
        disabled={readOnly || busy}
        label={t("settings.alerts.col_active")}
        onChange={(is_active) => void onSave(rule, { is_active }).catch(() => undefined)}
      />
      <div className="flex gap-2">
        {editing ? (
          <>
            <button type="button" disabled={busy} className={smallButton("primary")} onClick={() => void onSave(rule, body()).then(() => setEditing(false), () => undefined)}>
              {t("settings.save")}
            </button>
            <button type="button" className={linkButton} onClick={() => setEditing(false)}>
              {t("common.cancel")}
            </button>
          </>
        ) : (
          !readOnly && (
            <button
              type="button"
              className={linkButton}
              onClick={() => {
                setValue(usesMoney(rule) ? formatMoney(rule.threshold ?? 0) : String(rule.threshold_hours ?? ""));
                setRep(String(rule.repeat_hours));
                setEditing(true);
              }}
            >
              {t("settings.edit")}
            </button>
          )
        )}
      </div>
    </div>
  );
}
