import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError, data } from "@/api/client";
import { useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
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

const LOGIN_MODE = "skytowers.loginMode";

type Mode = "password" | "pin";
type SignedInUser = { id: string; role: string };

function rememberedMode(): Mode {
  try {
    return window.localStorage.getItem(LOGIN_MODE) === "pin" ? "pin" : "password";
  } catch {
    return "password";
  }
}

function rememberMode(mode: Mode) {
  try {
    window.localStorage.setItem(LOGIN_MODE, mode);
  } catch {
    // private mode
  }
}

/**
 * The first screen of every install (owner decision 2026-09-27; replaces artboard 6.1's user picker as the default):
 * a welcome panel beside one username/password form for every role — the account decides what opens. The PIN pad
 * stays as «دخول سريع» for staff (remembered per PC). While the install's default owner account is untouched, a
 * box shows it with a button that fills the form.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const status = useSystemStatus();
  const users = useQuery({ queryKey: ["auth", "users"], queryFn: () => data(api.GET("/api/v1/auth/users")) });
  const now = useNow(1000);

  const [mode, setModeState] = useState<Mode>(rememberedMode);
  const [recovering, setRecovering] = useState(false);
  const owner = status.data?.role === "owner";
  const list = users.data ?? [];

  const setMode = (next: Mode) => {
    rememberMode(next);
    setModeState(next);
  };

  const signedIn = useCallback(
    (token: string, user: SignedInUser) => {
      remember(user.id);
      try {
        window.sessionStorage.removeItem("skytowers.defaultPasswordLater"); // the reminder returns each sign-in
      } catch {
        // storage unavailable
      }
      session.signIn(token);
      queryClient.removeQueries();
      navigate(owner || user.role === "owner" ? "/owner" : "/", { replace: true });
    },
    [navigate, owner, queryClient],
  );

  if (session.token) return <Navigate to={owner ? "/owner" : "/"} replace />;

  return (
    <div className="grid min-h-screen grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] bg-bg-page max-[1100px]:grid-cols-1">
      <section className="relative flex flex-col items-center justify-center px-10 py-16">
        <div className="flex w-full max-w-[420px] flex-col gap-6">
          {/* Always the login fields (owner, 2026-09-27): no setup screens. A PC without a hotel starts with the
              default owner account; the owner opens a hotel from a backup inside the app when he wants. */}
          {mode === "password" ? (
            recovering ? (
              <RecoverForm onBack={() => setRecovering(false)} />
            ) : (
              <PasswordForm
                defaultLogin={status.data?.default_login ?? null}
                onDone={signedIn}
                onPin={() => setMode("pin")}
                onForgot={status.data?.role === "owner" ? undefined : () => setRecovering(true)}
              />
            )
          ) : (
            <PinLogin users={list} loaded={users.isSuccess} onDone={signedIn} onPassword={() => setMode("password")} />
          )}
        </div>
        <div className="absolute inset-x-10 bottom-6 flex justify-between text-label font-normal text-text-disabled">
          <span>
            {t("login.version")} <span dir="ltr">{status.data?.version ?? ""}</span>
            {status.data?.device_name && (
              <>
                {" · "}
                <span dir="ltr">{status.data.device_name}</span>
              </>
            )}
          </span>
        </div>
      </section>
      <Welcome now={now} serverDown={status.isError} owner={owner} importedSeq={status.data?.imported_seq ?? null} dueTasks={status.data?.due_tasks ?? 0} />
    </div>
  );
}

/** The welcome half: the hotel's mark, a greeting, the live date and time, and the server state. */
function Welcome({
  now,
  serverDown,
  owner,
  importedSeq,
  dueTasks,
}: {
  now: Date;
  serverDown: boolean;
  owner: boolean;
  importedSeq: number | null;
  dueTasks: number;
}) {
  const chip = "inline-flex h-7 items-center gap-1.5 rounded-control bg-primary-hover px-2.5 text-label";
  return (
    <aside className="relative flex flex-col justify-between overflow-hidden bg-gradient-to-b from-primary to-primary-hover px-12 py-10 text-primary-text-on max-[1100px]:hidden">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-card bg-primary-text-on text-body font-bold text-primary" dir="ltr">
          {t("app.logo")}
        </span>
        <div className="flex flex-col">
          <span className="text-section-title font-bold" dir="ltr">
            {t("app.name")}
          </span>
          <span className="text-label font-normal">{t("app.subtitle")}</span>
        </div>
      </div>

      <div className="flex flex-col items-center gap-6 text-center">
        <Skyline />
        <h1 className="m-0 text-[36px] font-bold leading-tight">{t("login.welcomeTitle")}</h1>
        <p className="m-0 max-w-[460px] text-body">{t("login.welcomeText")}</p>
      </div>

      <div className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-headline-number" dir="ltr">
            {formatTime(now)}
          </span>
          <span className="text-body">{formatDayDate(now)}</span>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <span className={chip}>
            <span className={`h-2 w-2 rounded-full ${serverDown ? "bg-danger" : "bg-success"}`} />
            {serverDown ? t("login.serverDown") : owner ? (importedSeq ? t("login.ownerDbSeq", { seq: digits(String(importedSeq)) }) : t("login.ownerDb")) : t("login.serverUp")}
          </span>
          {owner && <span className={chip}>{t("login.ownerDevice")}</span>}
          {/* Artboard 6.1 backlog chip: a count only, from the public status (design gap #13). */}
          {dueTasks > 0 && <span className={`${chip} bg-warning-soft text-warning-text`}>{t("login.backlog", { n: digits(String(dueTasks)) })}</span>}
        </div>
      </div>
    </aside>
  );
}

/** The app icon's three towers and star, drawn large (build/icons/make_icons.py uses the same geometry). */
function Skyline() {
  const towers: [number, number, number][] = [
    [230, 470, 410],
    [430, 250, 594],
    [614, 370, 794],
  ];
  const windows = towers.flatMap(([x0, top, x1]) => {
    const cols = x1 - x0 > 170 ? 3 : 2;
    const gap = (x1 - x0 - 30 * cols) / (cols + 1);
    const out: { x: number; y: number }[] = [];
    for (let y = top + 50; y + 34 < 770; y += 70) for (let c = 0; c < cols; c++) out.push({ x: x0 + gap + c * (30 + gap), y });
    return out;
  });
  return (
    <svg viewBox="150 120 760 760" className="h-[240px] w-[240px]" aria-hidden>
      {towers.map(([x0, top, x1]) => (
        <rect key={x0} x={x0} y={top} width={x1 - x0} height={800 - top} rx={14} className="fill-primary-text-on" />
      ))}
      <polygon points="492,252 532,252 512,150" className="fill-primary-text-on" />
      <rect x={190} y={816} width={644} height={34} rx={17} className="fill-primary-text-on" />
      {windows.map((w) => (
        <rect key={`${w.x}-${w.y}`} x={w.x} y={w.y} width={30} height={34} className="fill-primary" />
      ))}
      <polygon points="812,94 846,180 932,214 846,248 812,334 778,248 692,214 778,180" className="fill-warning" />
    </svg>
  );
}

/** The same counters as the PIN pad (review 2026-09-28, UI-12): attempts left, then until when it is locked. */
function passwordError(err: unknown): string {
  if (!(err instanceof ApiError)) return t("errors.error");
  if (err.code === "account_locked" && typeof err.extra.locked_until === "string") {
    return t("login.passwordLocked", { time: formatTime(err.extra.locked_until) });
  }
  if (err.code === "authentication_failed" && typeof err.extra.attempts_left === "number") {
    const n = err.extra.attempts_left;
    return n === 1 ? t("login.wrongPasswordLast") : t("login.wrongPassword", { n: digits(String(n)) });
  }
  return err.message;
}

function PasswordForm({
  defaultLogin,
  onDone,
  onPin,
  onForgot,
}: {
  defaultLogin: { username: string; password: string; pin: string } | null;
  onDone: (token: string, user: SignedInUser) => void;
  onPin: () => void;
  onForgot?: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await data(api.POST("/api/v1/auth/password", { body: { username: username.trim(), password } }));
      onDone(result.token, result.user);
    } catch (err) {
      setError(passwordError(err));
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  const field =
    "h-12 w-full rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body text-text-primary focus:border-primary";
  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-page-title">{t("login.signInTitle")}</h2>
        <div className="text-body text-text-secondary">{t("login.signInHint")}</div>
      </div>

      {defaultLogin && (
        <div className="flex flex-col gap-2 rounded-card border border-primary bg-primary-soft p-4">
          <div className="text-body font-semibold text-primary-hover">{t("login.firstTime")}</div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-body">
            <span>
              {t("login.username")}: <b dir="ltr">{defaultLogin.username}</b>
            </span>
            <span>
              {t("login.password")}: <b dir="ltr">{defaultLogin.password}</b>
            </span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-label font-normal text-text-secondary">{t("login.firstTimeHint")}</span>
            <button
              type="button"
              onClick={() => {
                setUsername(defaultLogin.username);
                setPassword(defaultLogin.password);
                setError(null);
              }}
              className="h-9 flex-none rounded-control border border-primary bg-bg-surface px-3 font-sans text-body font-medium text-primary hover:bg-primary-soft"
            >
              {t("login.fillDefault")}
            </button>
          </div>
        </div>
      )}

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
        disabled={busy || !username.trim() || !password}
        className="h-12 rounded-control border-0 bg-primary font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:opacity-50"
      >
        {t("login.signIn")}
      </button>
      <button type="button" onClick={onPin} className="border-0 bg-transparent font-sans text-body font-medium text-primary hover:text-primary-hover">
        {t("login.quickPin")}
      </button>
      {onForgot && (
        <button type="button" onClick={onForgot} className="border-0 bg-transparent font-sans text-body font-medium text-text-secondary hover:text-primary">
          {t("login.forgot")}
        </button>
      )}
    </form>
  );
}

/** «نسيت كلمة المرور؟» (owner decision 2026-09-28): offline, the email saved on the account confirms who asks.
 *  Wrong emails count like wrong passwords (locked after 5); nothing is sent anywhere. */
function RecoverForm({ onBack }: { onBack: () => void }) {
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [newCode, setNewCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mismatch = !!confirm && confirm !== password;
  const ready = !!username.trim() && !!secret.trim() && password.length >= 8 && password === confirm && !busy;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      // Staff type the email on their account; the owner types his recovery code (owner decision 2026-09-29).
      const proof = secret.trim().includes("@") ? { email: secret.trim() } : { recovery_code: secret.trim() };
      const res = await data(api.POST("/api/v1/auth/recover", { body: { username: username.trim(), password, ...proof } }));
      setNewCode(res.recovery_code ?? null);
      setDone(true);
    } catch (err) {
      setError(passwordError(err));
    } finally {
      setBusy(false);
    }
  };

  const field =
    "h-12 w-full rounded-control border border-border-strong bg-bg-surface px-3 font-sans text-body text-text-primary focus:border-primary";
  if (done) {
    return (
      <div className="flex w-full flex-col gap-4">
        <h2 className="m-0 text-page-title">{t("login.recoverDoneTitle")}</h2>
        <div className="text-body text-text-secondary">{t("login.recoverDone")}</div>
        {newCode && (
          <>
            <div className="text-body font-semibold">{t("login.newRecoveryCode")}</div>
            <div dir="ltr" className="rounded-card border border-border-strong bg-bg-surface-2 py-3 text-center font-mono text-[24px] font-semibold tracking-widest text-text-primary">
              {newCode}
            </div>
          </>
        )}
        <button type="button" onClick={onBack} className="h-12 rounded-control border-0 bg-primary font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover">
          {t("login.backToSignIn")}
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-page-title">{t("login.recoverTitle")}</h2>
        <div className="text-body text-text-secondary">{t("login.recoverHint")}</div>
      </div>
      <label className="flex flex-col gap-1.5 text-label text-text-secondary">
        {t("login.username")}
        <input dir="ltr" autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className={field} />
      </label>
      <label className="flex flex-col gap-1.5 text-label text-text-secondary">
        {t("login.email")}
        <input dir="ltr" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} className={field} />
        <span className="text-label font-normal text-text-secondary">{t("login.emailHint")}</span>
      </label>
      <label className="flex flex-col gap-1.5 text-label text-text-secondary">
        {t("login.newPassword")}
        <input dir="ltr" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={field} />
      </label>
      <label className="flex flex-col gap-1.5 text-label text-text-secondary">
        {t("login.confirmPassword")}
        <input dir="ltr" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={field} />
        {mismatch && <span className="text-label font-normal text-danger">{t("settings.users.passwordMismatch")}</span>}
      </label>
      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-control bg-danger-soft px-3 py-2.5 text-body font-medium text-danger-text">
          <CircleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          {error}
        </div>
      )}
      <button
        type="submit"
        disabled={!ready}
        className="h-12 rounded-control border-0 bg-primary font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:opacity-50"
      >
        {t("login.recoverSubmit")}
      </button>
      <button type="button" onClick={onBack} className="border-0 bg-transparent font-sans text-body font-medium text-primary hover:text-primary-hover">
        {t("login.backToSignIn")}
      </button>
    </form>
  );
}

/** «دخول سريع»: the user tiles and six-digit PIN of artboard 6.1 (keyboard digits work too). */
function PinLogin({
  users,
  loaded,
  onDone,
  onPassword,
}: {
  users: { id: string; full_name: string; role: string }[];
  loaded: boolean;
  onDone: (token: string, user: SignedInUser) => void;
  onPassword: () => void;
}) {
  const now = useNow(1000);
  const [userId, setUserId] = useState<string | null>(remembered);
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lockedUntil, setLockedUntil] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = users.find((u) => u.id === userId) ?? users[0] ?? null;
  const locked = lockedUntil !== null && lockedUntil > now;

  useEffect(() => {
    if (lockedUntil && lockedUntil <= now) {
      setLockedUntil(null);
      setError(null);
    }
  }, [lockedUntil, now]);

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
        onDone(result.token, result.user);
      } catch (e) {
        fail(e);
      } finally {
        setBusy(false);
      }
    },
    [selected, busy, locked, onDone],
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
  }, [press, pin, submitPin]);

  const chooseUser = (id: string) => {
    setUserId(id);
    setPin("");
    setError(null);
    setLockedUntil(null);
  };

  const firstName = selected?.full_name.split(" ")[0] ?? "";
  return (
    <div className="flex w-full flex-col items-center gap-5">
      <div className="flex flex-col items-center gap-1 text-center">
        <h2 className="m-0 text-page-title">{locked ? t("login.lockedTitle") : t("login.hello", { name: firstName })}</h2>
        <div className="text-body text-text-secondary">
          {locked ? t("login.lockedHint", { time: countdown(lockedUntil!, now) }) : t("login.pinHint")}
        </div>
      </div>

      {users.length === 0 && loaded ? (
        <div className="text-body text-text-secondary">{t("login.noUsers")}</div>
      ) : (
        <div className="flex w-full flex-wrap justify-center gap-2" role="radiogroup">
          {users.map((u) => {
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

      <PinPad disabled={locked || busy || !selected} onDigit={press} onClear={() => setPin("")} onBackspace={() => setPin((p) => p.slice(0, -1))} />

      <button type="button" onClick={onPassword} className="border-0 bg-transparent font-sans text-body font-medium text-primary hover:text-primary-hover">
        {locked ? t("login.askManager") : t("login.backToPassword")}
      </button>
    </div>
  );
}
