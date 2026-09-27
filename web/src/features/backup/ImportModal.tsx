import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleX, FileUp, LoaderCircle, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { keys } from "@/api/queries";
import { ErrorBanner } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { Cancelled, useConfirmGate } from "@/features/settings/confirm";
import { formatDate, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { formatSize } from "./BackupCard";

type Candidate = components["schemas"]["Candidate"];
type Run = components["schemas"]["ImportRun"];
type Check = components["schemas"]["ImportCheck"];
type Source = { kind: "drive"; candidate: Candidate } | { kind: "file"; file: File };
type Counts = Record<string, { inserted: number; updated: number; ignored: number }>;

const STEPS = ["pick", "verify", "merge", "result"] as const;

/**
 * 6.13 C import stepper: choose (Drive or USB file) → the server's five checks → merge → result.
 * The server runs checks and merge in one request; a rejected file comes back 422 with its checks.
 */
export function ImportModal({ initial, onClose }: { initial?: Candidate; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // Importing is a sensitive action (spec §6.8): the server asks for the manager's password once users exist.
  const { gate, modal: confirmModal } = useConfirmGate();
  const candidates = useQuery({ queryKey: ["owner", "import", "candidates"], queryFn: () => data(api.GET("/api/v1/owner/import/candidates")), retry: false });
  const [source, setSource] = useState<Source | null>(initial ? { kind: "drive", candidate: initial } : null);
  const [result, setResult] = useState<{ run: Run; ok: boolean } | null>(null);
  // 1.1: a file this PC has no key for opens with the owner's or a manager's login (key slots).
  const [login, setLogin] = useState({ username: "", password: "" });
  const fileRef = useRef<HTMLInputElement>(null);

  const run = useMutation({
    mutationFn: ({ src, allowOlder, creds }: { src: Source; allowOlder: boolean; creds?: { username: string; password: string } }): Promise<Run> =>
      gate(t("importDlg.title"), (headers) => {
        if (src.kind === "drive") {
          return data(
            api.POST("/api/v1/owner/import/drive", {
              headers,
              // A file already downloaded to incoming/ is imported by name; otherwise by its Drive id.
              body: src.candidate.local
                ? { name: src.candidate.name, allow_older: allowOlder }
                : { drive_file_id: src.candidate.drive_file_id ?? undefined, name: src.candidate.name, allow_older: allowOlder },
            }),
          );
        }
        const body = new FormData();
        body.append("file", src.file);
        body.append("allow_older", allowOlder ? "true" : "false");
        if (creds) {
          body.append("username", creds.username.trim());
          body.append("password", creds.password);
        }
        return data(api.POST("/api/v1/owner/import/run", { headers, body: body as never, bodySerializer: (b: unknown) => b as FormData }));
      }),
    onSuccess: (value) => setResult({ run: value, ok: true }),
    onError: (e) => {
      // 422: the checks rejected the file; the body is the failed ImportRun. A closed password window is not an error.
      if (e instanceof ApiError && e.status === 422 && Array.isArray(e.extra.checks)) setResult({ run: e.extra as unknown as Run, ok: false });
      else if (e instanceof Cancelled) setSource(null);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["owner"] });
      void queryClient.invalidateQueries({ queryKey: ["reports"] });
      void queryClient.invalidateQueries({ queryKey: keys.systemStatus });
      void queryClient.invalidateQueries({ queryKey: keys.importRuns });
    },
  });

  const start = (src: Source, allowOlder = false, creds?: { username: string; password: string }) => {
    setSource(src);
    setResult(null);
    run.mutate({ src, allowOlder, creds });
  };

  const step = result?.ok ? 3 : run.isPending || result ? 1 : 0;
  const older = !!result && !result.ok && result.run.checks.some((c) => c.key === "audit" && c.status === "warn");
  const needsLogin = !!result && !result.ok && (result.run.code === "credentials_required" || result.run.code === "credentials_wrong");
  const newest = candidates.data?.filter((c) => c.state === "new").sort((a, b) => b.seq - a.seq)[0];
  const seq = result?.run.backup_seq ?? (source?.kind === "drive" ? source.candidate.seq : null);
  const title = seq ? t("importDlg.titleSeq", { seq: digits(String(seq)) }) : t("importDlg.title");

  const footer = (() => {
    if (result?.ok) {
      return (
        <>
          <button type="button" className={buttons.primary} onClick={() => (onClose(), navigate("/owner"))}>
            {t("importDlg.openDashboard")}
          </button>
          <button type="button" className={buttons.ghost} onClick={onClose}>
            {t("common.close")}
          </button>
        </>
      );
    }
    if (older && source) {
      return (
        <>
          <button type="button" className={buttons.secondary} onClick={() => start(source, true)}>
            {t("importDlg.continueOlder")}
          </button>
          {newest && (
            <button type="button" className={buttons.primary} onClick={() => start({ kind: "drive", candidate: newest })}>
              {t("importDlg.pickNewest", { seq: digits(String(newest.seq)) })}
            </button>
          )}
          <div className="flex-1" />
          <button type="button" className={buttons.ghost} onClick={onClose}>
            {t("common.cancel")}
          </button>
        </>
      );
    }
    return (
      <>
        {result && (
          <button type="button" className={buttons.secondary} onClick={() => (setResult(null), setSource(null))}>
            {t("importDlg.back")}
          </button>
        )}
        <div className="flex-1" />
        <button type="button" className={buttons.ghost} disabled={run.isPending} onClick={onClose}>
          {t("common.cancel")}
        </button>
      </>
    );
  })();

  return (
    <Modal title={title} width={640} onClose={() => !run.isPending && onClose()} footer={footer}>
      <Steps current={step} />
      {run.isError && !result && !(run.error instanceof Cancelled) && <ErrorBanner>{(run.error as ApiError).message ?? t("errors.error")}</ErrorBanner>}
      {confirmModal}

      {step === 0 && (
        <div className="flex flex-col gap-3">
          <div className="text-label text-text-secondary">{t("importDlg.fromDrive")}</div>
          {candidates.isError && <div className="text-body text-text-secondary">{t("importDlg.driveUnavailable")}</div>}
          {candidates.data?.length === 0 && <div className="text-body text-text-secondary">{t("importDlg.noDriveFiles")}</div>}
          <div className="flex flex-col gap-2">
            {candidates.data?.slice(0, 5).map((c) => (
              <button
                key={c.name}
                type="button"
                onClick={() => start({ kind: "drive", candidate: c })}
                className="flex min-h-12 items-center gap-3 rounded-control border border-border-strong bg-bg-surface px-4 text-start font-sans text-body hover:bg-bg-surface-2"
              >
                <span className="font-semibold">{t("importDlg.copyN", { seq: digits(String(c.seq)) })}</span>
                <CandidateTag state={c.state} />
                <span className="flex-1" />
                <span className="text-label font-normal text-text-secondary">{formatSize(c.size)}</span>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3 text-label text-text-disabled">
            <span className="h-px flex-1 bg-border" />
            {t("importDlg.or")}
            <span className="h-px flex-1 bg-border" />
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".age"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) start({ kind: "file", file });
              e.target.value = "";
            }}
          />
          <button type="button" className={buttons.secondary} onClick={() => fileRef.current?.click()}>
            <FileUp className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("importDlg.pickFile")}
          </button>
        </div>
      )}

      {step === 1 && run.isPending && (
        <div className="flex flex-col items-center gap-3 py-6 text-body text-text-secondary">
          <LoaderCircle className="h-8 w-8 animate-spin text-primary" strokeWidth={1.75} aria-hidden />
          {t("importDlg.checking")}
          <div className="text-label font-normal">{t("importDlg.dontClose")}</div>
        </div>
      )}

      {needsLogin && source && (
        <form
          className="flex flex-col gap-3 rounded-card border border-primary bg-primary-soft p-4"
          onSubmit={(e) => {
            e.preventDefault();
            start(source, false, login);
          }}
        >
          <div className="text-body font-semibold">{t("adopt.step2")}</div>
          <div className="text-label font-normal text-text-secondary">{t("adopt.step2Hint")}</div>
          <div className="grid grid-cols-2 gap-3">
            <input
              dir="ltr"
              aria-label={t("login.username")}
              placeholder={t("login.username")}
              className="h-11 rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body"
              value={login.username}
              onChange={(e) => setLogin({ ...login, username: e.target.value })}
            />
            <input
              dir="ltr"
              type="password"
              aria-label={t("login.password")}
              placeholder={t("login.password")}
              className="h-11 rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body"
              value={login.password}
              onChange={(e) => setLogin({ ...login, password: e.target.value })}
            />
          </div>
          <button type="submit" className={buttons.primary} disabled={!login.username.trim() || !login.password}>
            {t("adopt.open")}
          </button>
        </form>
      )}

      {result && !result.ok && (
        <div className="flex flex-col gap-3">
          {older ? (
            <div className="rounded-card bg-warning-soft p-4 text-warning-text">
              <div className="text-body font-semibold">{t("importDlg.olderTitle")}</div>
              <div className="mt-1 text-body">{t("importDlg.olderText")}</div>
            </div>
          ) : (
            <ErrorBanner>{result.run.error}</ErrorBanner>
          )}
          <Checks checks={result.run.checks} />
          {!older && <div className="text-label font-normal text-text-secondary">{t("importDlg.untouched")}</div>}
        </div>
      )}

      {result?.ok && <ResultTable run={result.run} />}
    </Modal>
  );
}

function Steps({ current }: { current: number }) {
  return (
    <ol className="m-0 flex list-none items-center gap-2 p-0">
      {STEPS.map((key, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={key} className="flex flex-1 items-center gap-2">
            <span
              className={`inline-flex h-7 w-7 flex-none items-center justify-center rounded-full border text-label font-semibold ${
                done ? "border-primary bg-primary text-primary-text-on" : active ? "border-primary bg-primary-soft text-primary" : "border-border-strong bg-bg-surface text-text-disabled"
              }`}
            >
              {done ? <Check className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden /> : digits(String(i + 1))}
            </span>
            <span className={`whitespace-nowrap text-label ${active ? "font-semibold text-text-primary" : "text-text-secondary"}`}>{t(`importDlg.step_${key}`)}</span>
            {i < STEPS.length - 1 && <span className={`h-px flex-1 ${done ? "bg-primary" : "bg-border"}`} />}
          </li>
        );
      })}
    </ol>
  );
}

function Checks({ checks }: { checks: Check[] }) {
  return (
    <div className="flex flex-col divide-y divide-border rounded-card border border-border">
      {checks.map((c) => (
        <div key={c.key} className="flex min-h-11 items-center gap-3 px-4 py-2">
          <span
            className={`inline-flex h-6 w-6 flex-none items-center justify-center rounded-full ${
              c.status === "ok" ? "bg-success-soft text-success" : c.status === "warn" ? "bg-warning-soft text-warning" : "bg-danger-soft text-danger"
            }`}
          >
            {c.status === "ok" ? (
              <Check className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden />
            ) : c.status === "warn" ? (
              <TriangleAlert className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
            ) : (
              <CircleX className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
            )}
          </span>
          <span className="text-body font-medium">{c.label}</span>
          <span className="flex-1" />
          <span dir="ltr" className="text-label font-normal text-text-secondary">
            {c.detail}
          </span>
        </div>
      ))}
    </div>
  );
}

function ResultTable({ run }: { run: Run }) {
  const counts = (run.counts ?? {}) as Counts;
  const rows = Object.entries(counts);
  const total = rows.reduce((acc, [, c]) => ({ inserted: acc.inserted + c.inserted, updated: acc.updated + c.updated, ignored: acc.ignored + c.ignored }), {
    inserted: 0,
    updated: 0,
    ignored: 0,
  });
  const grid = "grid grid-cols-[2fr_1fr_1fr_1fr] items-center gap-3 px-4";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 rounded-card bg-success-soft p-4 text-success-text">
        <Check className="h-icon w-icon flex-none" strokeWidth={2.5} aria-hidden />
        <div>
          <div className="text-body font-semibold">{t("importDlg.done")}</div>
          {run.data_as_of && (
            <div className="text-label font-normal">
              {t("importDlg.dataNow", { date: formatDate(run.data_as_of) })} <span dir="ltr">{digits(formatTime(run.data_as_of))}</span>
            </div>
          )}
        </div>
      </div>
      <div className="overflow-hidden rounded-card border border-border">
        <div className={`${grid} h-9 bg-bg-surface-2 text-label text-text-secondary`}>
          {["table", "added", "updated", "ignored"].map((k) => (
            <div key={k}>{t(`importDlg.c_${k}`)}</div>
          ))}
        </div>
        {rows.map(([table, c]) => (
          <div key={table} className={`${grid} h-9 border-t border-border text-table-cell`}>
            <div>{table}</div>
            <div>{digits(String(c.inserted))}</div>
            <div>{digits(String(c.updated))}</div>
            <div className="text-text-secondary">{digits(String(c.ignored))}</div>
          </div>
        ))}
        <div className={`${grid} h-9 border-t border-border bg-bg-surface-2 text-table-cell font-semibold`}>
          <div>{t("importDlg.total")}</div>
          <div>{digits(String(total.inserted))}</div>
          <div>{digits(String(total.updated))}</div>
          <div>{digits(String(total.ignored))}</div>
        </div>
      </div>
    </div>
  );
}

export function CandidateTag({ state }: { state: Candidate["state"] }) {
  const cls =
    state === "new" ? "bg-primary-soft text-primary" : state === "imported" ? "bg-bg-surface-2 text-text-secondary" : "bg-warning-soft text-warning-text";
  return <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${cls}`}>{t(`importDlg.state_${state}`)}</span>;
}
