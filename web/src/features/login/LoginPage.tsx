import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError, data } from "@/api/client";
import { useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
import { Brand } from "@/components/ui/Brand";
import { buttons } from "@/components/ui/Modal";
import { ImportModal } from "@/features/backup/ImportModal";
import { PIN_LENGTH, PinDots, PinPad } from "@/components/ui/PinPad";
import { formatDayDate, formatTime } from "@/i18n/dates";
import { digits, toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";
import { useNow } from "@/lib/useNow";

const LAST_USER = "skytowers.lastUser";

function remembered(): string | null {
  try {
    return window.localStorage.getItem(LAST_USER);
  } catch {
    return null;
  }
}

function remember(userId: string) {
  try {
    window.localStorage.setItem(LAST_USER, userId);
  } catch {
    // private mode
  }
}

function countdown(until: Date, now: Date): string {
  const seconds = Math.max(0, Math.ceil((until.getTime() - now.getTime()) / 1000));
  return digits(`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`);
}

/** Login 6.1: user picker, six-digit PIN on dots + keypad (or the keyboard), password as the fallback. */
export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const status = useSystemStatus();
  const users = useQuery({ queryKey: ["auth", "users"], queryFn: () => data(api.GET("/api/v1/auth/users")) });
  const now = useNow(1000);

  const [userId, setUserId] = useState<string | null>(remembered);
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lockedUntil, setLockedUntil] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"pin" | "password">("pin");

  const owner = status.data?.role === "owner";
  const list = users.data ?? [];
  const selected = list.find((u) => u.id === userId) ?? list[0] ?? null;
  const locked = lockedUntil !== null && lockedUntil > now;

  useEffect(() => {
    if (lockedUntil && lockedUntil <= now) {
      setLockedUntil(null);
      setError(null);
    }
  }, [lockedUntil, now]);

  const signedIn = useCallback(
    (token: string, id: string) => {
      remember(id);
      session.signIn(token);
      queryClient.removeQueries();
      navigate(owner ? "/owner" : "/", { replace: true });
    },
    [navigate, owner, queryClient],
  );

  const fail = (e: unknown) => {
    setPin("");
    if (!(e instanceof ApiError)) return setError(t("errors.error"));
    if (e.code === "account_locked" && typeof e.extra.locked_until === "string") {
      setLockedUntil(new Date(e.extra.locked_until));
      return setError(t("login.lockedError"));
    }
    if (e.code === "authentication_failed" && typeof e.extra.attempts_left === "number") {
      const n = e.extra.attempts_left;
      return setError(n === 1 ? t("login.wrongPinLast") : t("login.wrongPin", { n: digits(String(n)) }));
    }
    setError(e.message);
  };

  const submitPin = useCallback(
    async (value: string) => {
      if (!selected || busy || locked) return;
      setBusy(true);
      try {
        const result = await data(api.POST("/api/v1/auth/pin", { body: { user_id: selected.id, pin: value } }));
        signedIn(result.token, selected.id);
      } catch (e) {
        fail(e);
      } finally {
        setBusy(false);
      }
    },
    [selected, busy, locked, signedIn],
  );

  const press = useCallback(
    (d: string) => {
      if (locked || busy) return;
      if (pin.length >= PIN_LENGTH) return;
      setError(null);
      const next = pin + d;
      setPin(next);
      // Submitted outside the state update: updaters run twice in StrictMode and would log two failures.
      if (next.length === PIN_LENGTH) void submitPin(next);
    },
    [locked, busy, pin, submitPin],
  );

  // Keyboard: digits on either keyboard layout, Backspace, Escape clears, Enter submits a 4–5 digit PIN.
  useEffect(() => {
    if (mode !== "pin") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      const key = toWestern(e.key);
      if (/^[0-9]$/.test(key)) press(key);
      else if (e.key === "Backspace") setPin((p) => p.slice(0, -1));
      else if (e.key === "Escape") setPin("");
      else if (e.key === "Enter" && pin.length >= 4) void submitPin(pin);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, press, pin, submitPin]);

  if (session.token) return <Navigate to={owner ? "/owner" : "/"} replace />;

  const chooseUser = (id: string) => {
    setUserId(id);
    setPin("");
    setError(null);
    setLockedUntil(null);
  };

  const server = status.isError
    ? { text: t("login.serverDown"), tone: "bg-danger-soft text-danger-text", dot: "bg-danger" }
    : owner
      ? {
          text: status.data?.imported_seq
            ? t("login.ownerDbSeq", { seq: digits(String(status.data.imported_seq)) })
            : t("login.ownerDb"),
          tone: "bg-bg-surface-2 text-text-secondary",
          dot: "bg-text-disabled",
        }
      : { text: t("login.serverUp"), tone: "bg-success-soft text-success-text", dot: "bg-success" };

  const firstName = selected?.full_name.split(" ")[0] ?? "";
  const title = locked ? t("login.lockedTitle") : owner ? t("login.helloOwner") : t("login.hello", { name: firstName });
  const hint = locked
    ? t("login.lockedHint", { time: countdown(lockedUntil!, now) })
    : owner
      ? t("login.ownerHint")
      : t("login.pinHint");

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-bg-page">
      {owner && <div className="absolute inset-x-0 top-0 h-2 bg-owner-banner-bg" />}
      <div className="absolute start-6 top-6">
        <Brand />
      </div>
      <div className="absolute end-6 top-6 flex items-center gap-2">
        <span className={`inline-flex h-7 items-center gap-1.5 rounded-control px-2.5 text-label ${server.tone}`}>
          <span className={`h-2 w-2 rounded-full ${server.dot}`} />
          {server.text}
        </span>
        <span className="inline-flex h-7 items-center rounded-control bg-bg-surface-2 px-2.5 text-label text-text-secondary">
          {owner ? t("login.ownerDevice") : t("login.receptionDevice")}
        </span>
      </div>

      <div className="flex w-[400px] flex-col items-center gap-5 rounded-modal border border-border bg-bg-surface p-8 shadow-elevated">
        {status.data?.needs_setup ? (
          <FirstSetup onDone={signedIn} />
        ) : owner && users.isSuccess && list.length === 0 ? (
          <FirstImport publicKey={status.data?.owner_public_key ?? null} onDone={() => void users.refetch()} />
        ) : mode === "pin" ? (
          <>
            <div className="flex flex-col items-center gap-1 text-center">
              <h1 className="m-0 text-page-title">{title}</h1>
              <div className="text-body text-text-secondary">{hint}</div>
            </div>

            {list.length === 0 && users.isSuccess ? (
              <div className="text-body text-text-secondary">{t("login.noUsers")}</div>
            ) : (
              <div className="flex w-full flex-wrap justify-center gap-2" role="radiogroup">
                {list.map((u) => {
                  const active = u.id === selected?.id;
                  return (
                    <button
                      key={u.id}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      onClick={() => chooseUser(u.id)}
                      className={`flex min-w-24 flex-col items-center gap-1.5 rounded-control border px-3 py-2 font-sans ${
                        active ? "border-primary bg-primary-soft text-primary" : "border-border bg-bg-surface text-text-primary hover:bg-bg-surface-2"
                      }`}
                    >
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-soft text-body font-semibold text-primary">
                        {u.full_name.charAt(0)}
                      </span>
                      <span className={`text-label ${active ? "font-semibold" : "font-medium"}`}>{u.full_name}</span>
                    </button>
                  );
                })}
              </div>
            )}

            <PinDots count={pin.length} />

            {error && (
              <div role="alert" className="flex w-full items-center gap-2 rounded-control bg-danger-soft px-3 py-2.5 text-body font-medium text-danger-text">
                <CircleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
                {error}
              </div>
            )}

            <PinPad
              disabled={locked || busy || !selected}
              onDigit={press}
              onClear={() => setPin("")}
              onBackspace={() => setPin((p) => p.slice(0, -1))}
            />

            <button
              type="button"
              onClick={() => setMode("password")}
              className="border-0 bg-transparent font-sans text-body font-medium text-primary hover:text-primary-hover"
            >
              {locked ? t("login.askManager") : t("login.usePassword")}
            </button>
          </>
        ) : (
          <PasswordForm onDone={signedIn} onBack={() => setMode("pin")} />
        )}
      </div>

      <div className="absolute inset-x-6 bottom-6 flex justify-between text-label font-normal text-text-disabled">
        <span>
          {t("login.version")} <span dir="ltr">{status.data?.version ?? ""}</span>
          {status.data?.device_name && (
            <>
              {" · "}
              <span dir="ltr">{status.data.device_name}</span>
            </>
          )}
        </span>
        <span>
          {formatDayDate(now)} · <span dir="ltr">{formatTime(now)}</span>
        </span>
      </div>
    </div>
  );
}

function PasswordForm({ onDone, onBack }: { onDone: (token: string, userId: string) => void; onBack: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await data(api.POST("/api/v1/auth/password", { body: { username, password } }));
      onDone(result.token, result.user.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("errors.error"));
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  const field =
    "h-11 w-full rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body text-text-primary";
  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-4">
      <div className="flex flex-col items-center gap-1 text-center">
        <h1 className="m-0 text-page-title">{t("login.passwordTitle")}</h1>
        <div className="text-body text-text-secondary">{t("login.passwordHint")}</div>
      </div>
      <label className="flex flex-col gap-1.5 text-label text-text-secondary">
        {t("login.username")}
        <input dir="ltr" autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className={field} />
      </label>
      <label className="flex flex-col gap-1.5 text-label text-text-secondary">
        {t("login.password")}
        <input
          dir="ltr"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={field}
        />
      </label>
      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-control bg-danger-soft px-3 py-2.5 text-body font-medium text-danger-text">
          <CircleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          {error}
        </div>
      )}
      <button
        type="submit"
        disabled={busy || !username || !password}
        className="h-11 rounded-control border-0 bg-primary font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:opacity-50"
      >
        {t("login.signIn")}
      </button>
      <button type="button" onClick={onBack} className="border-0 bg-transparent font-sans text-body font-medium text-primary">
        {t("login.usePin")}
      </button>
    </form>
  );
}

/** New owner PC: no users until the first backup is imported (spec §9.3); the server allows that one import.
 * The owner's public key is shown here so it can be copied into the reception PC before that first backup. */
function FirstImport({ publicKey, onDone }: { publicKey: string | null; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex w-full flex-col gap-4 text-center">
      <h1 className="m-0 text-page-title">{t("login.ownerSetupTitle")}</h1>
      {publicKey && (
        <div className="flex flex-col gap-2 text-start">
          <div className="text-body font-semibold">{t("login.ownerStep1")}</div>
          <div dir="ltr" className="break-all rounded-control border border-border bg-bg-surface-2 p-2 text-label font-normal">
            {publicKey}
          </div>
          <button
            type="button"
            className={buttons.secondary}
            onClick={() => void navigator.clipboard?.writeText(publicKey).then(() => setCopied(true))}
          >
            {copied ? t("login.copied") : t("login.copyKey")}
          </button>
        </div>
      )}
      <div className="flex flex-col gap-2 text-start">
        <div className="text-body font-semibold">{t("login.ownerStep2")}</div>
        <div className="text-body text-text-secondary">{t("login.ownerFirstImport")}</div>
        <button type="button" className={`${buttons.primary} w-full`} onClick={() => setOpen(true)}>
          {t("login.ownerFirstImportButton")}
        </button>
      </div>
      {open && (
        <ImportModal
          onClose={() => {
            setOpen(false);
            onDone();
          }}
        />
      )}
    </div>
  );
}

/** New reception PC: no users yet. The first manager is created here (no command line needed). */
function FirstSetup({ onDone }: { onDone: (token: string, id: string) => void }) {
  const [form, setForm] = useState({ full_name: "", username: "", password: "", confirm: "", pin: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const mismatch = form.confirm !== "" && form.confirm !== form.password;
  const valid =
    form.full_name.trim() && form.username.trim() && form.password.length >= 6 && !mismatch && form.confirm && /^\d{4,6}$/.test(form.pin);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await data(
        api.POST("/api/v1/auth/setup", {
          body: { full_name: form.full_name.trim(), username: form.username.trim(), password: form.password, pin: form.pin },
        }),
      );
      onDone(result.token, result.user.id);
    } catch (err) {
      const fields = err instanceof ApiError ? (err.extra.errors as Record<string, string[]> | undefined) : undefined;
      setError(fields ? Object.values(fields).flat().join(" · ") : err instanceof ApiError ? err.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  const field = "h-11 w-full rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body";
  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-3">
      <div className="text-center">
        <h1 className="m-0 text-page-title">{t("login.setupTitle")}</h1>
        <div className="text-body text-text-secondary">{t("login.setupHint")}</div>
      </div>
      {error && (
        <div role="alert" className="rounded-control bg-danger-soft px-3 py-2.5 text-body font-medium text-danger-text">
          {error}
        </div>
      )}
      <label className="flex flex-col gap-1 text-label text-text-secondary">
        {t("login.setupName")}
        <input className={field} value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} autoFocus />
      </label>
      <label className="flex flex-col gap-1 text-label text-text-secondary">
        {t("login.username")}
        <input className={field} dir="ltr" autoComplete="username" value={form.username} onChange={(e) => set({ username: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1 text-label text-text-secondary">
        {t("login.setupPassword")}
        <input className={field} type="password" autoComplete="new-password" value={form.password} onChange={(e) => set({ password: e.target.value })} />
      </label>
      <label className={`flex flex-col gap-1 text-label ${mismatch ? "text-danger" : "text-text-secondary"}`}>
        {mismatch ? t("login.setupMismatch") : t("login.setupConfirm")}
        <input className={field} type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => set({ confirm: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1 text-label text-text-secondary">
        {t("login.setupPin")}
        <input
          className={field}
          dir="ltr"
          inputMode="numeric"
          maxLength={6}
          value={form.pin}
          onChange={(e) => set({ pin: toWestern(e.target.value).replace(/\D/g, "") })}
        />
      </label>
      <button type="submit" disabled={!valid || busy} className={`${buttons.primary} w-full`}>
        {t("login.setupSubmit")}
      </button>
    </form>
  );
}
