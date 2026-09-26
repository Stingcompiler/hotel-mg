import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { ErrorBanner, Field, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { BACKUP_RUNS, BackupCard, DRIVE_STATUS, formatSize } from "@/features/backup/BackupCard";
import { formatDayMonth, formatTime } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { apiErrorText, Card, HeadRow, linkButton, smallButton } from "./shared";

type Settings = components["schemas"]["BackupSettings"];
const SETTINGS = ["backup", "settings"] as const;
const GRID = "grid grid-cols-[140px_110px_90px_1fr_90px_120px] items-center gap-4 px-4";
const num = (text: string) => toWestern(text).replace(/\D/g, "");

/** 6.13 A: the backup card, schedule and retention, destinations and Drive account, run log. */
export function BackupTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: SETTINGS, queryFn: () => data(api.GET("/api/v1/backup/settings")) });
  const drive = useQuery({ queryKey: DRIVE_STATUS, queryFn: () => data(api.GET("/api/v1/backup/drive/status")) }).data;
  const runs = useQuery({ queryKey: BACKUP_RUNS, queryFn: () => data(api.GET("/api/v1/backup/runs")) }).data;
  const [draft, setDraft] = useState<Settings | null>(null);
  const [text, setText] = useState({ interval: "", keep: "" });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (settings.data) {
      setDraft(settings.data);
      setText({ interval: String(settings.data.interval_hours), keep: String(settings.data.keep_count) });
    }
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () =>
      data(
        api.PATCH("/api/v1/backup/settings", {
          body: {
            version: draft!.version,
            interval_hours: Number(text.interval || 0),
            keep_count: Number(text.keep || 0),
            on_shift_close: draft!.on_shift_close,
            auto_drive: draft!.auto_drive,
            second_dir: draft!.second_dir.trim(),
            owner_recipient: draft!.owner_recipient.trim(),
          },
        }),
      ),
    onSuccess: (value) => {
      setError(null);
      queryClient.setQueryData(SETTINGS, value);
    },
    onError: (e) => setError(apiErrorText(e)),
  });
  const link = useMutation({
    mutationFn: () => data(api.POST("/api/v1/backup/drive/auth-url")),
    onSuccess: (res) => window.open(res.url, "_blank", "noopener"),
    onError: (e) => setError(apiErrorText(e)),
  });
  const unlink = useMutation({
    mutationFn: () => data(api.POST("/api/v1/backup/drive/unlink")),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: DRIVE_STATUS }),
    onError: (e) => setError(apiErrorText(e)),
  });

  const dirty =
    !!draft &&
    !!settings.data &&
    (JSON.stringify({ ...draft, version: 0 }) !== JSON.stringify({ ...settings.data, version: 0 }) ||
      text.interval !== String(settings.data.interval_hours) ||
      text.keep !== String(settings.data.keep_count));

  return (
    <div className="flex flex-col gap-4">
      <BackupCard />
      {error && <ErrorBanner>{error}</ErrorBanner>}
      {draft && (
        <div className="grid grid-cols-2 gap-4">
          <Card title={t("backup.schedule")}>
            <div className="flex flex-col gap-4 p-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label={t("backup.every")} hint={t("backup.hours")}>
                  <TextInput readOnly={readOnly} inputMode="numeric" value={text.interval} onChange={(e) => setText({ ...text, interval: num(e.target.value) })} />
                </Field>
                <Field label={t("backup.keep")} hint={t("backup.copies")}>
                  <TextInput readOnly={readOnly} inputMode="numeric" value={text.keep} onChange={(e) => setText({ ...text, keep: num(e.target.value) })} />
                </Field>
              </div>
              <Switch
                label={t("backup.onShiftClose")}
                hint={t("backup.onShiftCloseHint")}
                checked={draft.on_shift_close}
                disabled={readOnly}
                onChange={(on_shift_close) => setDraft({ ...draft, on_shift_close })}
              />
              <Switch
                label={t("backup.autoDrive")}
                hint={t("backup.autoDriveHint")}
                checked={draft.auto_drive}
                disabled={readOnly}
                onChange={(auto_drive) => setDraft({ ...draft, auto_drive })}
              />
            </div>
          </Card>
          <Card title={t("backup.destinations")}>
            <div className="flex flex-col gap-4 p-4">
              <Field label={t("backup.secondDir")} hint={t("backup.secondDirHint")}>
                <TextInput readOnly={readOnly} dir="ltr" value={draft.second_dir} onChange={(e) => setDraft({ ...draft, second_dir: e.target.value })} />
              </Field>
              <Field label={t("backup.recipient")} hint={t("backup.recipientHint")}>
                <TextInput readOnly={readOnly} dir="ltr" value={draft.owner_recipient} onChange={(e) => setDraft({ ...draft, owner_recipient: e.target.value })} />
              </Field>
              <div className="flex items-center gap-3">
                <span className="text-label text-text-secondary">{t("backup.driveAccount")}</span>
                {drive?.linked ? (
                  <>
                    <span dir="ltr" className="text-body">
                      {drive.email}
                    </span>
                    {!readOnly && (
                      <button type="button" disabled={unlink.isPending} onClick={() => unlink.mutate()} className={`${linkButton} text-danger`}>
                        {t("backup.unlink")}
                      </button>
                    )}
                  </>
                ) : drive && !drive.configured ? (
                  <span className="text-body text-text-secondary">{t("backup.driveNotConfigured")}</span>
                ) : (
                  !readOnly && (
                    <button type="button" disabled={link.isPending} onClick={() => link.mutate()} className={linkButton}>
                      {t("backup.link")}
                    </button>
                  )
                )}
              </div>
            </div>
          </Card>
        </div>
      )}
      {!readOnly && dirty && (
        <div>
          <button type="button" disabled={save.isPending} onClick={() => save.mutate()} className={smallButton("primary")}>
            {t("settings.save")}
          </button>
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
