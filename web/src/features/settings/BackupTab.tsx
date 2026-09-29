import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { session } from "@/api/session";
import { ErrorBanner, Field, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { BACKUP_RUNS, BackupCard, DRIVE_STATUS, formatSize } from "@/features/backup/BackupCard";
import { formatDayMonth, formatTime } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { Cancelled, useConfirmGate } from "./confirm";
import { apiErrorText, Card, HeadRow, linkButton, smallButton } from "./shared";

type Settings = components["schemas"]["BackupSettings"];
type Patch = components["schemas"]["PatchedBackupSettingsUpdateRequest"];
const SETTINGS = ["backup", "settings"] as const;
const GRID = "grid grid-cols-[140px_110px_90px_1fr_90px_120px] items-center gap-4 px-4";
const num = (text: string) => toWestern(text).replace(/\D/g, "");

/**
 * 6.13 A: the backup card, schedule and retention, destinations and Drive account, run log.
 * On the owner PC the same tab reads and writes through `owner/…` (the only writable settings there) and the card
 * offers import instead of a new backup.
 */
export function BackupTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const owner = session.role === "owner";
  const settings = useQuery({
    queryKey: SETTINGS,
    queryFn: () => data(owner ? api.GET("/api/v1/owner/settings") : api.GET("/api/v1/backup/settings")),
  });
  const drive = useQuery({
    queryKey: DRIVE_STATUS,
    queryFn: () => data(owner ? api.GET("/api/v1/owner/drive/status") : api.GET("/api/v1/backup/drive/status")),
  }).data;
  const runs = useQuery({ queryKey: BACKUP_RUNS, queryFn: () => data(api.GET("/api/v1/backup/runs")) }).data;
  const [draft, setDraft] = useState<Settings | null>(null);
  const [text, setText] = useState({ interval: "", keep: "", days: "", size: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (settings.data) {
      setDraft(settings.data);
      setText({
        interval: String(settings.data.interval_hours),
        keep: String(settings.data.keep_count),
        days: String(settings.data.keep_days),
        size: String(settings.data.max_total_mb),
      });
    }
  }, [settings.data]);

  const { gate, modal } = useConfirmGate();
  const save = useMutation({
    mutationFn: () => {
      const body: Patch = {
        version: draft!.version,
        interval_hours: Number(text.interval || 0),
        keep_count: Number(text.keep || 0),
        keep_days: Number(text.days || 0),
        max_total_mb: Number(text.size || 0),
        on_shift_close: draft!.on_shift_close,
        auto_drive: draft!.auto_drive,
        second_dir: draft!.second_dir.trim(),
        owner_recipient: draft!.owner_recipient.trim(),
      };
      // Changing who else receives the backups or the second folder is the owner's, with his password (C-15).
      const current = settings.data;
      const sensitive = !!current && (body.second_dir !== current.second_dir || body.owner_recipient !== current.owner_recipient);
      const send = (headers?: { "X-Confirm-Token"?: string }) =>
        data(owner ? api.PATCH("/api/v1/owner/settings", { headers, body }) : api.PATCH("/api/v1/backup/settings", { headers, body }));
      return sensitive ? gate(t("backup.actRecipients"), send) : send();
    },
    onSuccess: (value) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(SETTINGS, value);
    },
    onError: (e) => !(e instanceof Cancelled) && setError(apiErrorText(e)),
  });
  const link = useMutation({
    mutationFn: () => data(owner ? api.POST("/api/v1/owner/drive/auth-url") : api.POST("/api/v1/backup/drive/auth-url")),
    onSuccess: (res) => window.open(res.url, "_blank", "noopener"),
    onError: (e) => setError(apiErrorText(e)),
  });
  const unlink = useMutation({
    mutationFn: () => data(owner ? api.POST("/api/v1/owner/drive/unlink") : api.POST("/api/v1/backup/drive/unlink")),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: DRIVE_STATUS }),
    onError: (e) => setError(apiErrorText(e)),
  });

  const dirty =
    !!draft &&
    !!settings.data &&
    (JSON.stringify({ ...draft, version: 0 }) !== JSON.stringify({ ...settings.data, version: 0 }) ||
      text.interval !== String(settings.data.interval_hours) ||
      text.keep !== String(settings.data.keep_count) ||
      text.days !== String(settings.data.keep_days) ||
      text.size !== String(settings.data.max_total_mb));
  // The owner PC's own settings are editable by its manager even though every other tab is read-only there.
  const locked = owner ? readOnly && session.role !== "owner" : readOnly;

  return (
    <div className="flex flex-col gap-4">
      {modal}
      <BackupCard onImport={owner ? () => navigate("/backup?import=1") : undefined} />
      {error && <ErrorBanner>{error}</ErrorBanner>}
      {draft && (
        <div className="grid grid-cols-2 gap-4">
          <Card title={t("backup.schedule")}>
            <div className="flex flex-col gap-4 p-4">
              <div className="grid grid-cols-3 gap-4">
                <Field label={t("backup.every")} hint={t("backup.hours")}>
                  <TextInput readOnly={locked} inputMode="numeric" value={text.interval} onChange={(e) => setText({ ...text, interval: num(e.target.value) })} />
                </Field>
                <Field label={t("backup.keep")} hint={t("backup.copies")}>
                  <TextInput readOnly={locked} inputMode="numeric" value={text.keep} onChange={(e) => setText({ ...text, keep: num(e.target.value) })} />
                </Field>
                <Field label={t("backup.keepDays")} hint={t("backup.keepDaysHint")}>
                  <TextInput readOnly={locked} inputMode="numeric" value={text.days} onChange={(e) => setText({ ...text, days: num(e.target.value) })} />
                </Field>
                <Field label={t("backup.maxSize")} hint={t("backup.maxSizeHint")}>
                  <TextInput readOnly={locked} inputMode="numeric" value={text.size} onChange={(e) => setText({ ...text, size: num(e.target.value) })} />
                </Field>
              </div>
              <Switch
                label={t("backup.onShiftClose")}
                hint={t("backup.onShiftCloseHint")}
                checked={draft.on_shift_close}
                disabled={locked}
                onChange={(on_shift_close) => setDraft({ ...draft, on_shift_close })}
              />
              <Switch
                label={t("backup.autoDrive")}
                hint={t("backup.autoDriveHint")}
                checked={draft.auto_drive}
                disabled={locked}
                onChange={(auto_drive) => setDraft({ ...draft, auto_drive })}
              />
            </div>
          </Card>
          <Card title={t("backup.destinations")}>
            <div className="flex flex-col gap-4 p-4">
              <Field label={t("backup.secondDir")} hint={t("backup.secondDirHint")}>
                <TextInput readOnly={locked} dir="ltr" value={draft.second_dir} onChange={(e) => setDraft({ ...draft, second_dir: e.target.value })} />
              </Field>
              <Field label={t("backup.recipient")} hint={t("backup.recipientHint")}>
                <TextInput readOnly={locked} dir="ltr" value={draft.owner_recipient} onChange={(e) => setDraft({ ...draft, owner_recipient: e.target.value })} />
              </Field>
              <div className="flex items-center gap-3">
                <span className="text-label text-text-secondary">{t("backup.driveAccount")}</span>
                {drive?.linked ? (
                  <>
                    <span dir="ltr" className="text-body">
                      {drive.email}
                    </span>
                    {!locked && (
                      <button type="button" disabled={unlink.isPending} onClick={() => unlink.mutate()} className={`${linkButton} h-9 text-danger`}>
                        {t("backup.unlink")}
                      </button>
                    )}
                  </>
                ) : drive && !drive.configured ? (
                  <span className="text-body text-text-secondary">{t("backup.driveNotConfigured")}</span>
                ) : (
                  !locked && (
                    <button type="button" disabled={link.isPending} onClick={() => link.mutate()} className={`${linkButton} h-9`}>
                      {t("backup.link")}
                    </button>
                  )
                )}
              </div>
            </div>
          </Card>
        </div>
      )}
      {!locked && (dirty || saved) && (
        <div className="flex items-center gap-3">
          {dirty && (
            <button type="button" disabled={save.isPending} onClick={() => save.mutate()} className={smallButton("primary")}>
              {t("settings.save")}
            </button>
          )}
          {saved && !dirty && <span className="text-label font-normal text-success-text">{t("settings.savedNow")}</span>}
        </div>
      )}
      <Card title={t("backup.log")} note={runs ? t("backup.logCount", { n: digits(String(runs.count)) }) : undefined}>
        <HeadRow grid={GRID} labels={["time", "kind", "size", "dest", "status", "by"].map((k) => t(`backup.col_${k}`))} />
        {runs?.results.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("backup.logEmpty")}</div>}
        {runs?.results.map((r) => (
          <div key={r.id} className={`${GRID} min-h-11 border-b border-border py-1.5 text-table-cell`}>
            <div className="text-label font-normal text-text-secondary">
              {formatDayMonth(r.created_at)} · <span dir="ltr">{digits(formatTime(r.created_at))}</span>
            </div>
            <div>{r.kind_label}</div>
            <div>{r.size ? formatSize(r.size) : "—"}</div>
            <div className="min-w-0 truncate text-text-secondary">
              {r.status === "ok" ? (
                <span dir="ltr">{r.path}</span>
              ) : (
                r.message
              )}
              {r.second_error && <span className="text-warning-text"> · {r.second_error}</span>}
            </div>
            <div className={r.status === "ok" ? "text-success-text" : r.status === "failed" ? "text-danger" : "text-text-secondary"}>{r.status_label}</div>
            <div className="text-text-secondary">{r.by || t("backup.auto")}</div>
          </div>
        ))}
      </Card>
    </div>
  );
}

function Switch({ label, hint, checked, disabled, onChange }: { label: string; hint: string; checked: boolean; disabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <div className="text-body font-medium">{label}</div>
        <div className="text-label font-normal text-text-secondary">{hint}</div>
      </div>
      <Toggle checked={checked} disabled={disabled} label={label} onChange={onChange} />
    </div>
  );
}
