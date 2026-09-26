import { useCallback, useRef, useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/t";

type Headers = { "X-Confirm-Token"?: string };

type Gate = <T>(action: string, run: (h: Headers) => Promise<T>) => Promise<T>;

/** Thrown when the manager closes the password window; callers ignore it. */
export class Cancelled extends Error {}

// One confirmation covers the next sensitive saves until it expires (server: five minutes).
let cached: { token: string; until: number } | null = null;

/**
 * Sensitive saves (users, prices, disabling an alert rule) need the manager's password again
 * (Gap Fill 6.11 A, spec §6.8). `gate(action, run)` sends the request; when the server answers
 * `confirmation_required` it asks for the password once and repeats `run` with `X-Confirm-Token`.
 */
export function useConfirmGate() {
  const [ask, setAsk] = useState<{ action: string; resolve: (h: Headers) => void; reject: (e: unknown) => void } | null>(null);

  const askPassword = useCallback((action: string) => new Promise<Headers>((resolve, reject) => setAsk({ action, resolve, reject })), []);

  const gate: Gate = useCallback(
    async (action, run) => {
      const token = cached && cached.until > Date.now() ? cached.token : null;
      try {
        return await run(token ? { "X-Confirm-Token": token } : {});
      } catch (e) {
        if (e instanceof ApiError && e.code === "confirmation_required") {
          cached = null;
          return run(await askPassword(action));
        }
        throw e;
      }
    },
    [askPassword],
  );

  const modal = ask && (
    <ConfirmModal
      action={ask.action}
      onCancel={() => {
        ask.reject(new Cancelled());
        setAsk(null);
      }}
      onToken={(token, seconds) => {
        cached = { token, until: Date.now() + Math.max(0, seconds - 10) * 1000 };
        ask.resolve({ "X-Confirm-Token": token });
        setAsk(null);
      }}
    />
  );
  return { gate, modal };
}

function ConfirmModal({ action, onCancel, onToken }: { action: string; onCancel: () => void; onToken: (token: string, seconds: number) => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = async () => {
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await data(api.POST("/api/v1/auth/confirm", { body: { password } }));
      onToken(res.confirm_token, res.expires_in);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
      setPassword("");
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("settings.confirm.title")}
      width={480}
      onClose={onCancel}
      footer={
        <>
          <button type="button" disabled={!password || busy} onClick={submit} className={buttons.primary}>
            {t("settings.confirm.submit")}
          </button>
          <button type="button" onClick={onCancel} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="text-body text-text-secondary">{t("settings.confirm.action", { action })}</div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <Field label={t("settings.confirm.password")} error={null}>
        <TextInput
          ref={inputRef}
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          invalid={!!error}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
      </Field>
      <div className="text-label font-normal text-text-secondary">{t("settings.confirm.note")}</div>
    </Modal>
  );
}
