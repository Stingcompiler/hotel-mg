import { useQueryClient } from "@tanstack/react-query";
import { Clock } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError, CLOCK_EVENT, data } from "@/api/client";
import { keys, useMe, useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
import { buttons } from "@/components/ui/Modal";
import { Cancelled, useConfirmGate } from "@/features/settings/confirm";
import { formatDayDate, formatTime } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";
import { useNow } from "@/lib/useNow";

/**
 * 6.14 A clock guard: a blocking dialog (48 % scrim, no close) while the server refuses writes because the PC clock
 * went back. Fix the Windows clock and re-check; a manager may accept the clock with a password (spec §6.7).
 */
export function ClockGuard() {
  const status = useSystemStatus().data;
  const me = useMe().data;
  const now = useNow(1000);
  const queryClient = useQueryClient();
  const { gate, modal } = useConfirmGate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const onRefused = () => void queryClient.invalidateQueries({ queryKey: keys.systemStatus });
    window.addEventListener(CLOCK_EVENT, onRefused);
    return () => window.removeEventListener(CLOCK_EVENT, onRefused);
  }, [queryClient]);
  if (!status?.clock_blocked) return null;

  const manager = me?.role === "manager" || me?.role === "owner";
  const recheck = () => void queryClient.invalidateQueries({ queryKey: keys.systemStatus });
  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      await gate(t("clock.approveAction"), (headers) => data(api.POST("/api/v1/system/clock/approve", { headers })));
      recheck();
    } catch (e) {
      if (!(e instanceof Cancelled)) setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };
  const when = (d: string | Date) => (
    <>
      {formatDayDate(d)} · <span dir="ltr">{digits(formatTime(d))}</span>
    </>
  );

  return (
    <div className="scrim-48 fixed inset-0 z-50 flex items-center justify-center">
      <div role="alertdialog" aria-modal="true" aria-labelledby="clock-title" className="flex w-[560px] flex-col gap-4 rounded-modal bg-bg-surface p-6 shadow-elevated">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-danger-soft text-danger">
            <Clock className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          </span>
          <div>
            <h2 id="clock-title" className="m-0 text-page-title">
              {t("clock.title")}
            </h2>
            <div className="text-body text-text-secondary">{t("clock.subtitle")}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-card bg-danger-soft p-3 text-danger-text">
            <div className="text-label">{t("clock.deviceClock")}</div>
            <div className="text-body font-semibold">{when(now)}</div>
          </div>
          <div className="rounded-card bg-bg-surface-2 p-3">
            <div className="text-label text-text-secondary">{t("clock.lastRecorded")}</div>
            <div className="text-body font-semibold">{status.clock_last_seen_at ? when(status.clock_last_seen_at) : "—"}</div>
          </div>
        </div>
        <div className="text-body">{t("clock.why")}</div>
        <ol className="m-0 flex flex-col gap-1 ps-5 text-body text-text-secondary">
          <li>{t("clock.step1")}</li>
          <li>{t("clock.step2")}</li>
        </ol>
        {error && <div className="text-body text-danger">{error}</div>}
        <div className="flex items-center gap-3">
          <button type="button" onClick={recheck} className={buttons.primary}>
            {t("clock.recheck")}
          </button>
          <div className="flex-1" />
          {manager ? (
            <button type="button" disabled={busy} onClick={() => void approve()} className="border-0 bg-transparent p-0 font-sans text-label text-text-secondary underline">
              {t("clock.approve")}
            </button>
          ) : (
            <button type="button" onClick={() => session.signOut()} className="border-0 bg-transparent p-0 font-sans text-label text-text-secondary underline">
              {t("clock.managerSignIn")}
            </button>
          )}
        </div>
      </div>
      {modal}
    </div>
  );
}
