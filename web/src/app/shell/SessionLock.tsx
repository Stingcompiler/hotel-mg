import { Lock } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api, ApiError, data } from "@/api/client";
import { useCurrentShift, useHotelSettings, useMe } from "@/api/queries";
import { session } from "@/api/session";
import { PIN_LENGTH, PIN_MIN, PinDots, PinPad } from "@/components/ui/PinPad";
import { formatTime } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

const ACTIVITY = ["pointerdown", "keydown", "wheel", "touchstart"] as const;

/**
 * 6.14 B session lock: after `session_lock_minutes` without input the screen is covered and the same user types
 * their PIN to carry on where they stopped; the page underneath stays mounted, so unsaved forms survive.
 * «تبديل المستخدم» signs out to the login screen.
 */
export function SessionLock() {
  const minutes = useHotelSettings().data?.session_lock_minutes ?? 0;
  const me = useMe().data;
  const shift = useCurrentShift().data?.shift;
  const [locked, setLocked] = useState(false);
  const [lastAction, setLastAction] = useState<Date>(new Date());
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number>();

  // Restart the idle timer on any input while unlocked.
  useEffect(() => {
    if (!minutes || locked) return;
    const arm = () => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setLocked(true), minutes * 60_000);
    };
    const onActivity = () => {
      setLastAction(new Date());
      arm();
    };
    arm();
    ACTIVITY.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));
    return () => {
      window.clearTimeout(timer.current);
      ACTIVITY.forEach((e) => window.removeEventListener(e, onActivity));
    };
  }, [minutes, locked]);

  const submit = useCallback(
    async (value: string) => {
      if (!me || busy) return;
      setBusy(true);
      try {
        const result = await data(api.POST("/api/v1/auth/pin", { body: { user_id: me.id, pin: value } }));
        session.signIn(result.token);
        setLocked(false);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : t("errors.error"));
      } finally {
        setPin("");
        setBusy(false);
      }
    },
    [me, busy],
  );

  const press = useCallback(
    (d: string) => {
      if (busy) return;
      setError(null);
      setPin((p) => {
        const next = (p + d).slice(0, PIN_LENGTH);
        return next;
      });
    },
    [busy],
  );

  // Submit once six digits are in (outside the state updater: StrictMode runs updaters twice).
  useEffect(() => {
    if (locked && pin.length === PIN_LENGTH) void submit(pin);
  }, [locked, pin, submit]);

  useEffect(() => {
    if (!locked) return;
    const onKey = (e: KeyboardEvent) => {
      const key = toWestern(e.key);
      if (/^[0-9]$/.test(key)) press(key);
      else if (e.key === "Backspace") setPin((p) => p.slice(0, -1));
      else if (e.key === "Escape") setPin("");
      else if (e.key === "Enter" && pin.length >= 4) void submit(pin);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [locked, press, pin, submit]);

  // The page underneath stays mounted (unsaved forms survive) but takes no focus, click or key while locked: Enter on
  // a button focused before the lock opened a dialog behind it (review 2026-09-28, UI-2).
  useEffect(() => {
    const root = document.getElementById("root");
    if (!locked || !root) return;
    (document.activeElement as HTMLElement | null)?.blur();
    root.inert = true;
    return () => {
      root.inert = false;
    };
  }, [locked]);

  if (!locked || !me) return null;
  return createPortal(
    <div className="scrim-48 fixed inset-0 z-50 flex items-center justify-center">
      <div role="dialog" aria-modal="true" aria-labelledby="lock-title" className="flex w-[400px] flex-col items-center gap-5 rounded-modal bg-bg-surface p-8 shadow-elevated">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-soft text-primary">
          <Lock className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex flex-col items-center gap-1 text-center">
          <h2 id="lock-title" className="m-0 text-page-title">
            {t("lock.title", { minutes: digits(String(minutes)) })}
          </h2>
          <div className="text-body text-text-secondary">
            {me.full_name}
            {shift && ` · ${t("lock.shiftOpen")}`} · {t("lock.lastAction")} <span dir="ltr">{digits(formatTime(lastAction))}</span>
          </div>
          <div className="text-body text-text-secondary">{t("lock.hint")}</div>
        </div>
        <PinDots count={pin.length} />
        {error && <div className="text-center text-body font-medium text-danger">{error}</div>}
        <PinPad
          disabled={busy}
          onDigit={press}
          onClear={() => setPin("")}
          onBackspace={() => setPin((p) => p.slice(0, -1))}
          onEnter={() => void submit(pin)}
          canEnter={pin.length >= PIN_MIN}
        />
        <div className="flex w-full items-center justify-between text-label">
          <button type="button" onClick={() => session.signOut()} className="border-0 bg-transparent p-0 font-sans text-label font-medium text-primary">
            {t("lock.switchUser")}
          </button>
          <span className="text-text-secondary">{t("lock.kept")}</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
