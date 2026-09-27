import { DatabaseBackup, Eye, FileUp, LoaderCircle, MonitorCog } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
import { ErrorBanner } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/t";

type Mode = "view" | "work";

/**
 * 1.1 — a new PC opens a hotel from a backup, only when the owner chooses to (never a setup step): the file, the
 * owner's or a manager's login as on the reception PC (it unlocks the file), then view only or work on this PC.
 * The service restarts to take the data; the page waits for it and returns to the login page.
 */
export function AdoptModal({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<Mode>("view");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("mode", mode);
      body.append("username", username.trim());
      body.append("password", password);
      await data(api.POST("/api/v1/backup/adopt", { body: body as never, bodySerializer: (b: unknown) => b as FormData }));
      setRestarting(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  if (restarting) return <Restarting />;

  const field = "h-11 w-full rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body";
  return (
    <Modal
      title={t("adopt.title")}
      width={640}
      onClose={() => !busy && onClose()}
      footer={
        <>
          <button type="submit" form="adopt-form" disabled={!file || !username.trim() || !password || busy} className={buttons.primary}>
            {busy ? t("adopt.opening") : t("adopt.open")}
          </button>
          <div className="flex-1" />
          <button type="button" className={buttons.ghost} disabled={busy} onClick={onClose}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <form id="adopt-form" onSubmit={submit} className="flex flex-col gap-5">
        <div className="text-body text-text-secondary">{t("adopt.intro")}</div>
        {error && <ErrorBanner>{error}</ErrorBanner>}

        <section className="flex flex-col gap-2">
          <div className="text-body font-semibold">{t("adopt.step1")}</div>
          <input
            ref={fileRef}
            type="file"
            accept=".age"
            hidden
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
          />
          <button type="button" className={buttons.secondary} onClick={() => fileRef.current?.click()}>
            <FileUp className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {file ? file.name : t("adopt.pickFile")}
          </button>
        </section>

        <section className="flex flex-col gap-2">
          <div className="text-body font-semibold">{t("adopt.step2")}</div>
          <div className="text-label font-normal text-text-secondary">{t("adopt.step2Hint")}</div>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-label text-text-secondary">
              {t("login.username")}
              <input dir="ltr" className={field} autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-label text-text-secondary">
              {t("login.password")}
              <input dir="ltr" type="password" className={field} autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <div className="text-body font-semibold">{t("adopt.step3")}</div>
          <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label={t("adopt.step3")}>
            {(["view", "work"] as Mode[]).map((m) => {
              const active = mode === m;
              const Icon = m === "view" ? Eye : MonitorCog;
              return (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setMode(m)}
                  className={`flex flex-col items-start gap-2 rounded-card border-2 p-4 text-start font-sans ${
                    active ? "border-primary bg-primary-soft" : "border-border bg-bg-surface hover:bg-bg-surface-2"
                  }`}
                >
                  <span className="flex items-center gap-2 text-body font-semibold">
                    <Icon className="h-icon w-icon text-primary" strokeWidth={1.75} aria-hidden />
                    {t(`adopt.${m}Title`)}
                  </span>
                  <span className="text-label font-normal text-text-secondary">{t(`adopt.${m}Text`)}</span>
                </button>
              );
            })}
          </div>
        </section>
      </form>
    </Modal>
  );
}

/** Waits for the service to come back with the hotel, then returns to the login page (the hotel's accounts). */
function Restarting() {
  const before = useSystemStatus().data;
  useEffect(() => {
    let wentDown = false;
    const timer = window.setInterval(async () => {
      try {
        const res = await fetch("/api/v1/system/status");
        const next = (await res.json()) as { role: string; hotel_id: string | null; can_adopt: boolean };
        const changed = !next.can_adopt && (next.role !== before?.role || next.hotel_id !== before?.hotel_id);
        if (changed || (wentDown && res.ok && !next.can_adopt)) {
          window.clearInterval(timer);
          session.signOut();
          window.location.assign("/login");
        }
      } catch {
        wentDown = true;
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [before]);
  return (
    <Modal title={t("adopt.title")} width={520} onClose={() => undefined} footer={null}>
      <div className="flex flex-col items-center gap-3 py-6 text-center text-body text-text-secondary">
        <LoaderCircle className="h-8 w-8 animate-spin text-primary" strokeWidth={1.75} aria-hidden />
        <div className="font-semibold text-text-primary">{t("adopt.restarting")}</div>
        <div className="text-label font-normal">{t("adopt.restartingHint")}</div>
      </div>
    </Modal>
  );
}

/** Shown only on a new PC (`system/status.can_adopt`): start the hotel here, or open it from a backup. */
export function NewPcCard({ onSetup }: { onSetup?: () => void }) {
  const status = useSystemStatus().data;
  const [open, setOpen] = useState(false);
  if (!status?.can_adopt) return null;
  return (
    <div className="flex items-center gap-4 rounded-card border border-primary bg-primary-soft p-4">
      <DatabaseBackup className="h-8 w-8 flex-none text-primary" strokeWidth={1.5} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="text-body font-semibold">{t("adopt.cardTitle")}</div>
        <div className="text-label font-normal text-text-secondary">{t("adopt.cardText")}</div>
      </div>
      {onSetup && (
        <button type="button" className={buttons.secondary} onClick={onSetup}>
          {t("adopt.setupHere")}
        </button>
      )}
      <button type="button" className={buttons.primary} onClick={() => setOpen(true)}>
        {t("adopt.fromBackup")}
      </button>
      {open && <AdoptModal onClose={() => setOpen(false)} />}
    </div>
  );
}
