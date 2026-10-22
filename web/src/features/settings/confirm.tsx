import { useCallback, useRef, useState } from "react";

import { api, ApiError, data } from "@/api/client";
import { useMe } from "@/api/queries";
import { ErrorBanner, Field, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/t";
import { useSingleFlight } from "@/lib/useSingleFlight";

type Headers = { "X-Confirm-Token"?: string };

type Gate = <T>(action: string, run: (h: Headers) => Promise<T>) => Promise<T>;

/** Thrown when the manager closes the password window; callers ignore it. */
export class Cancelled extends Error {}

type Method = "pin" | "password";

// One confirmation covers the next sensitive saves until it expires (server: five minutes).
let cached: { token: string; until: number } | null = null;
// The way this PC's manager confirmed last time is offered first next time.
let lastMethod: Method | null = null;

/**
 * Sensitive saves need the manager to confirm again (Gap Fill 6.11 A, spec §6.8). `gate(action, run)` sends the
 * request; when the server answers `confirmation_required` it asks once — the PIN or the password — and repeats `run`
 * with `X-Confirm-Token`. Actions that guard the accounts or the backups answer `password_confirmation_required` to a
 * PIN confirmation, and the window then asks for the password only (decision 237).
 */
export function useConfirmGate() {
  const [ask, setAsk] = useState<{
    action: string;
    passwordOnly: boolean;
    resolve: (h: Headers) => void;
    reject: (e: unknown) => void;
  } | null>(null);

  const askConfirm = useCallback(
    (action: string, passwordOnly: boolean) => new Promise<Headers>((resolve, reject) => setAsk({ action, passwordOnly, resolve, reject })),
    [],
  );

  const gate: Gate = useCallback(
    async (action, run) => {
      const token = cached && cached.until > Date.now() ? cached.token : null;
      try {
        return await run(token ? { "X-Confirm-Token": token } : {});
      } catch (e) {
        if (e instanceof ApiError && (e.code === "confirmation_required" || e.code === "password_confirmation_required")) {
          cached = null;
          const passwordOnly = e.code === "password_confirmation_required";
          try {
            return await run(await askConfirm(action, passwordOnly));
          } catch (again) {
            // A PIN confirmation reaching an account or backup action: ask once more, for the password.
            if (!passwordOnly && again instanceof ApiError && again.code === "password_confirmation_required") {
              cached = null;
              return run(await askConfirm(action, true));
            }
            throw again;
          }
        }
        throw e;
      }
    },
    [askConfirm],
  );

  const modal = ask && (
    <ConfirmModal
      action={ask.action}
      passwordOnly={ask.passwordOnly}
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

function ConfirmModal({
  action,
  passwordOnly,
  onCancel,
  onToken,
}: {
  action: string;
  passwordOnly: boolean;
  onCancel: () => void;
  onToken: (token: string, seconds: number) => void;
}) {
  const me = useMe().data;
  // The PIN first, unless it is still the default one (never accepted) or the action needs the password.
  const [chosen, setChosen] = useState<Method>(lastMethod ?? (me?.default_pin ? "password" : "pin"));
  const method: Method = passwordOnly ? "password" : chosen;
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const once = useSingleFlight();
  const submit = () => once(submitNow);
  const submitNow = async () => {
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await data(api.POST("/api/v1/auth/confirm", { body: method === "pin" ? { pin: password } : { password } }));
      if (!passwordOnly) lastMethod = method;
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
      {passwordOnly ? (
        <div className="text-body text-text-secondary">{t("settings.confirm.passwordOnly")}</div>
      ) : (
        <Segmented<Method>
          label={t("settings.confirm.method")}
          value={method}
          onChange={(m) => {
            setChosen(m);
            setPassword("");
            setError(null);
            inputRef.current?.focus();
          }}
          options={[
            { value: "pin", label: t("settings.confirm.byPin") },
            { value: "password", label: t("settings.confirm.byPassword") },
          ]}
        />
      )}
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <Field label={t(method === "pin" ? "settings.confirm.pin" : "settings.confirm.password")} error={null}>
        <TextInput
          key={method}
          ref={inputRef}
          type="password"
          autoFocus
          dir="ltr"
          inputMode={method === "pin" ? "numeric" : undefined}
          maxLength={method === "pin" ? 6 : undefined}
          autoComplete={method === "pin" ? "off" : "current-password"}
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
