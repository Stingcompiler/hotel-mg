import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CloudUpload, DatabaseBackup, Download, TriangleAlert, Usb } from "lucide-react";
import { type ReactNode, useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { keys, useSystemStatus } from "@/api/queries";
import { formatWhen } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

export const BACKUP_RUNS = ["backup", "runs"] as const;
export const DRIVE_STATUS = ["backup", "drive"] as const;

export function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${digits((bytes / (1024 * 1024)).toFixed(1))} MB`;
  return `${digits(String(Math.max(1, Math.round(bytes / 1024))))} KB`;
}

const button = (primary: boolean) =>
  `inline-flex h-11 w-full items-center justify-center gap-2 rounded-control px-4 font-sans text-body font-semibold disabled:border-border disabled:bg-bg-surface-2 disabled:text-text-disabled ${
    primary ? "border-0 bg-primary text-primary-text-on hover:bg-primary-hover" : "border border-border-strong bg-bg-surface text-text-primary hover:bg-bg-surface-2"
  }`;

/**
 * 6.13 «النسخة الاحتياطية والمزامنة»: three equal buttons with a result line under each. The primary button is
 * each device's main job: «نسخة احتياطية الآن» at reception, «استيراد نسخة» on the owner PC. Import is shown
 * disabled at reception (owner PC only) so staff learn where it lives.
 */
export function BackupCard({ onImport }: { onImport?: () => void }) {
  const queryClient = useQueryClient();
  const offline = useSystemStatus().isError;
  const owner = !!onImport;
  const runs = useQuery({ queryKey: BACKUP_RUNS, queryFn: () => data(api.GET("/api/v1/backup/runs")) });
  const drive = useQuery({
    queryKey: DRIVE_STATUS,
    queryFn: () => data(owner ? api.GET("/api/v1/owner/drive/status") : api.GET("/api/v1/backup/drive/status")),
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["backup"] });
    void queryClient.invalidateQueries({ queryKey: ["owner"] });
    void queryClient.invalidateQueries({ queryKey: keys.systemStatus });
  };
  const run = useMutation({
    mutationFn: () => data(owner ? api.POST("/api/v1/owner/backup/run") : api.POST("/api/v1/backup/run")),
    onSettled: refresh,
  });
  const sync = useMutation({
    mutationFn: () => data(owner ? api.POST("/api/v1/owner/drive/sync") : api.POST("/api/v1/backup/drive/sync")),
    onSettled: refresh,
  });

  const last = runs.data?.results[0];
  const d = drive.data;

  const backupLine = (): ReactNode => {
    if (offline) return <Line tone="muted">{t("backup.needsServer")}</Line>;
    if (run.isError) return <Line tone="danger">{(run.error as ApiError).message}</Line>;
    if (!last) return <Line tone="muted">{t("backup.none")}</Line>;
    if (last.status === "failed") return <Line tone="danger">{t("backup.failed", { when: formatWhen(last.created_at), message: last.message })}</Line>;
    return (
      <Line tone="success">
        {t("backup.done", { when: formatWhen(last.created_at), size: formatSize(last.size) })}{" "}
        <span dir="ltr" className="text-text-secondary">
          {last.path}
        </span>
      </Line>
    );
  };

  const syncLine = (): ReactNode => {
    if (d && !d.configured) return <Line tone="muted">{t("backup.driveNotConfigured")}</Line>;
    if (d && !d.linked) return <Line tone="muted">{t("backup.driveNotLinked")}</Line>;
    if (sync.isPending) return <Line tone="muted">{t("backup.syncing")}</Line>;
    if (sync.isError) return <Line tone="danger">{(sync.error as ApiError).message}</Line>;
    if (sync.data) {
      return (
        <Line tone="success">
          {sync.data.uploaded ? t("backup.uploaded", { n: digits(String(sync.data.uploaded)) }) : t("backup.nothingNew")}
          {sync.data.downloaded.length > 0 && ` · ${t("backup.downloaded", { n: digits(String(sync.data.downloaded.length)) })}`}
          {sync.data.message && ` · ${sync.data.message}`}
        </Line>
      );
    }
    if (d?.last_upload_at) {
      return (
        <Line tone="muted">
          {t("backup.lastUpload", { when: formatWhen(d.last_upload_at) })} · <span dir="ltr">{d.email}</span>
          {d.pending_uploads > 0 && ` · ${t("backup.pending", { n: digits(String(d.pending_uploads)) })}`}
        </Line>
      );
    }
    return <Line tone="muted">{d?.email ? <span dir="ltr">{d.email}</span> : "—"}</Line>;
  };

  return (
    <section className="flex flex-col gap-4 rounded-card border border-border bg-bg-surface p-4">
      <div className="flex items-baseline gap-3">
        <h2 className="m-0 text-section-title">{t("backup.title")}</h2>
        <span className="text-body text-text-secondary">{t("backup.subtitle")}</span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="flex flex-col gap-2">
          <button type="button" disabled={offline || run.isPending} title={offline ? t("common.offlineHint") : undefined} onClick={() => run.mutate()} className={button(!owner)}>
            <DatabaseBackup className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {run.isPending ? t("backup.running") : t("backup.now")}
          </button>
          {backupLine()}
        </div>
        <div className="flex flex-col gap-2">
          <button type="button" disabled={!d?.linked || sync.isPending} onClick={() => sync.mutate()} className={button(false)}>
            <CloudUpload className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("backup.sync")}
          </button>
          {syncLine()}
        </div>
        <div className="flex flex-col gap-2">
          <button type="button" disabled={!onImport} title={onImport ? undefined : t("backup.ownerOnly")} onClick={onImport} className={button(owner)}>
            <Download className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("backup.import")}
          </button>
          <Line tone="muted">{owner ? t("backup.importHint") : t("backup.ownerOnly")}</Line>
        </div>
      </div>
      {!owner && <UsbSave disabled={offline || !last || last.status !== "ok"} />}
    </section>
  );
}

type Drive = { drive: string; label: string; free: number };

/** «حفظ على فلاشة»: the backups folder is for administrators only, so the service copies the newest backup to the
 *  stick itself (review 2026-09-29, E-16). One stick: copied at once; several: pick one. */
function UsbSave({ disabled }: { disabled: boolean }) {
  const [drives, setDrives] = useState<Drive[] | null>(null);
  const copy = useMutation({
    mutationFn: (drive: string) => data(api.POST("/api/v1/backup/usb/copy", { body: { drive } })),
  });
  const look = useMutation({
    mutationFn: () => data(api.GET("/api/v1/backup/usb")),
    onSuccess: (found) => {
      setDrives(found);
      if (found.length === 1) copy.mutate(found[0].drive);
    },
  });
  const busy = look.isPending || copy.isPending;
  const line = (): ReactNode => {
    if (copy.isPending) return <Line tone="muted">{t("backup.usbCopying")}</Line>;
    if (copy.isError) return <Line tone="danger">{(copy.error as ApiError).message}</Line>;
    if (look.isError) return <Line tone="danger">{(look.error as ApiError).message}</Line>;
    if (copy.data) {
      return (
        <Line tone="success">
          {t("backup.usbDone")} <span dir="ltr">{copy.data.folder}</span>
        </Line>
      );
    }
    if (drives && drives.length === 0) return <Line tone="muted">{t("backup.usbNone")}</Line>;
    return <Line tone="muted">{t("backup.usbHint")}</Line>;
  };
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => {
          copy.reset();
          look.mutate();
        }}
        className="inline-flex h-10 items-center gap-2 rounded-control border border-border-strong bg-bg-surface px-4 font-sans text-body font-semibold text-text-primary hover:bg-bg-surface-2 disabled:text-text-disabled"
      >
        <Usb className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
        {t("backup.usb")}
      </button>
      {drives &&
        drives.length > 1 &&
        !copy.data &&
        drives.map((d) => (
          <button
            key={d.drive}
            type="button"
            disabled={busy}
            onClick={() => copy.mutate(d.drive)}
            className="inline-flex h-10 items-center gap-2 rounded-control border border-primary bg-primary-soft px-3 font-sans text-body text-primary"
          >
            <span dir="ltr">{d.drive}</span> {d.label} · {formatSize(d.free)}
          </button>
        ))}
      <div className="min-w-0 flex-1">{line()}</div>
    </div>
  );
}

export function Line({ tone, children }: { tone: "success" | "danger" | "muted"; children: ReactNode }) {
  const color = tone === "success" ? "text-success-text" : tone === "danger" ? "text-danger" : "text-text-secondary";
  return (
    <div className={`flex items-start gap-1.5 text-label font-normal ${color}`}>
      {tone === "success" && <Check className="mt-0.5 h-3.5 w-3.5 flex-none" strokeWidth={2.5} aria-hidden />}
      {tone === "danger" && <TriangleAlert className="mt-0.5 h-3.5 w-3.5 flex-none" strokeWidth={2} aria-hidden />}
      <span className="min-w-0">{children}</span>
    </div>
  );
}
