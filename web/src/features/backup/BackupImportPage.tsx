import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { useSystemStatus } from "@/api/queries";
import { days } from "@/i18n/counts";
import { formatDayMonth, formatTime, formatWhen } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { BackupCard, formatSize } from "./BackupCard";
import { CandidateTag, ImportModal } from "./ImportModal";

type Candidate = components["schemas"]["Candidate"];
const GRID = "grid grid-cols-[130px_80px_110px_1fr_90px_110px] items-center gap-3 px-4";

/** 6.13 B owner PC «النسخ والاستيراد»: the card with import as the primary action, import log, Drive files, data state. */
export function BackupImportPage() {
  // «استيراد نسخة» on the settings tab lands here with `?import=1` and opens the dialog at once.
  const [params, setParams] = useSearchParams();
  const [importing, setImporting] = useState<{ candidate?: Candidate } | null>(params.has("import") ? {} : null);
  useEffect(() => {
    if (params.has("import")) setParams({}, { replace: true });
  }, [params, setParams]);
  const runs = useQuery({ queryKey: ["owner", "import", "runs", "all"], queryFn: () => data(api.GET("/api/v1/owner/import/runs")) });
  const status = useQuery({ queryKey: ["owner", "status"], queryFn: () => data(api.GET("/api/v1/owner/status")), retry: false }).data;
  const candidates = useQuery({
    queryKey: ["owner", "import", "candidates"],
    queryFn: () => data(api.GET("/api/v1/owner/import/candidates")),
    retry: false,
  });
  const last = status?.last_import;
  // Pasted in the reception's backup settings so its backups can be opened here.
  const publicKey = useSystemStatus().data?.owner_public_key;

  return (
    <div className="flex flex-col gap-4 p-6 max-[1599px]:gap-3">
      <div className="flex h-9 items-center gap-3">
        <h1 className="m-0 text-page-title">{t("nav.backup")}</h1>
        <span className="text-body text-text-secondary">{t("ownerBackup.subtitle")}</span>
      </div>
      <BackupCard onImport={() => setImporting({})} />
      <div className="text-label font-normal text-text-secondary">{t("ownerBackup.note")}</div>

      <div className="grid grid-cols-[2fr_1fr] items-start gap-4 max-[1599px]:gap-3">
        <section className="flex flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
          <div className="flex min-h-12 items-center gap-3 border-b border-border px-4">
            <h2 className="m-0 text-section-title">{t("ownerBackup.log")}</h2>
            {runs.data && <span className="text-label font-normal text-text-secondary">{t("ownerBackup.logCount", { n: digits(String(runs.data.count)) })}</span>}
          </div>
          <div className={`${GRID} h-10 bg-bg-surface-2 text-label text-text-secondary`}>
            {["time", "copy", "source", "result", "status", "by"].map((k) => (
              <div key={k}>{t(`ownerBackup.c_${k}`)}</div>
            ))}
          </div>
          {runs.data?.results.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("ownerBackup.logEmpty")}</div>}
          {runs.data?.results.map((r) => (
            <div key={r.id} className={`${GRID} min-h-11 border-t border-border py-1.5 text-table-cell`}>
              <div className="text-label font-normal text-text-secondary">
                {formatDayMonth(r.created_at)} · <span dir="ltr">{digits(formatTime(r.created_at))}</span>
              </div>
              <div className="font-semibold">{r.backup_seq ? digits(String(r.backup_seq)) : "—"}</div>
              <div>{t(`ownerBackup.src_${r.source}`)}</div>
              <div className="min-w-0 truncate text-text-secondary">
                {r.status === "ok" ? t("ownerBackup.dataUntil", { when: r.data_as_of ? formatWhen(r.data_as_of) : "—" }) : r.error}
              </div>
              <div className={r.status === "ok" ? "text-success-text" : "text-danger"}>{t(`ownerBackup.st_${r.status}`)}</div>
              <div className="text-text-secondary">{r.by || "—"}</div>
            </div>
          ))}
        </section>

        <div className="flex flex-col gap-4">
          <section className="flex flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
            <div className="flex min-h-12 items-center border-b border-border px-4">
              <h2 className="m-0 text-section-title">{t("ownerBackup.driveFiles")}</h2>
            </div>
            {candidates.isError && <div className="p-4 text-body text-text-secondary">{t("importDlg.driveUnavailable")}</div>}
            {candidates.data?.length === 0 && <div className="p-4 text-body text-text-secondary">{t("importDlg.noDriveFiles")}</div>}
            {candidates.data?.slice(0, 6).map((c) => (
              <div key={c.name} className="flex min-h-14 items-center gap-3 border-t border-border px-4 py-2 first:border-t-0">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-body font-semibold">
                    {t("importDlg.copyN", { seq: digits(String(c.seq)) })}
                    <CandidateTag state={c.state} />
                  </div>
                  <div className="text-label font-normal text-text-secondary">{formatSize(c.size)}</div>
                </div>
                <button
                  type="button"
                  onClick={() => setImporting({ candidate: c })}
                  className="inline-flex h-9 items-center rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body font-medium text-text-primary hover:bg-bg-surface-2"
                >
                  {c.state === "imported" ? t("ownerBackup.reimport") : t("ownerBackup.importThis")}
                </button>
              </div>
            ))}
          </section>

          <section className="flex flex-col gap-3 rounded-card border border-border bg-bg-surface p-4">
            <h2 className="m-0 text-section-title">{t("ownerBackup.state")}</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-label text-text-secondary">{t("ownerBackup.lastCopy")}</div>
                <div className="text-headline-number">{last?.backup_seq ? digits(String(last.backup_seq)) : "—"}</div>
                <div className="text-label font-normal text-text-secondary">{last ? formatWhen(last.created_at) : t("ownerBackup.never")}</div>
              </div>
              <div>
                <div className="text-label text-text-secondary">{t("ownerBackup.age")}</div>
                <div className="text-headline-number">
                  {status?.hours_old === null || status?.hours_old === undefined
                    ? "—"
                    : status.hours_old < 48
                      ? t("ownerBackup.hours", { n: digits(String(status.hours_old)) })
                      : days(Math.floor(status.hours_old / 24))}
                </div>
                <div className="text-label font-normal text-text-secondary">{t("ownerBackup.alertAfter")}</div>
              </div>
            </div>
            {publicKey && (
              <div className="flex flex-col gap-1">
                <div className="text-label text-text-secondary">{t("ownerBackup.publicKey")}</div>
                <div dir="ltr" className="break-all rounded-control bg-bg-surface-2 p-2 text-label font-normal">
                  {publicKey}
                </div>
              </div>
            )}
            {last && (
              <div className={`text-label font-normal ${last.audit_chain_ok ? "text-success-text" : "text-danger"}`}>
                {last.audit_chain_ok ? t("ownerBackup.chainOk") : t("ownerBackup.chainBroken")}
              </div>
            )}
          </section>
        </div>
      </div>

      {importing && <ImportModal initial={importing.candidate} onClose={() => setImporting(null)} />}
    </div>
  );
}
