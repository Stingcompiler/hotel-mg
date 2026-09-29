import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Plus } from "lucide-react";
import { useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { useMe } from "@/api/queries";
import { ErrorBanner, Field, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { Toggle } from "@/components/ui/Toggle";
import { formatWhen } from "@/i18n/dates";
import { toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { Cancelled, useConfirmGate } from "./confirm";
import { apiErrorText, Card, Footnote, HeadRow, linkButton, smallButton } from "./shared";

type User = components["schemas"]["User"];
type Role = "reception" | "manager" | "owner";
const GRID = "grid grid-cols-[1.4fr_1fr_1fr_100px_1fr_110px_80px] items-center gap-4 px-4";
const USERS = ["settings", "users"] as const;

/** 6.11 A: users table; role, PIN, password and disabling ask for the manager's password first. */
export function UsersTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: USERS, queryFn: () => data(api.GET("/api/v1/users/")) });
  const { gate, modal } = useConfirmGate();
  const [recoveryCode, setRecoveryCode] = useState<string | null>(null);
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: USERS });

  const toggle = useMutation({
    mutationFn: (u: User) =>
      gate(t(u.is_active ? "settings.users.actDisable" : "settings.users.actEnable", { name: u.full_name }), (headers) =>
        data(api.PATCH("/api/v1/users/{id}", { params: { path: { id: u.id } }, headers, body: { version: u.version, is_active: !u.is_active } })),
      ),
    onSuccess: refresh,
    onError: (e) => !(e instanceof Cancelled) && setError(apiErrorText(e)),
  });
  const unlock = useMutation({
    mutationFn: (u: User) => data(api.POST("/api/v1/users/{id}/unlock", { params: { path: { id: u.id } } })),
    onSuccess: refresh,
    onError: (e) => setError(apiErrorText(e)),
  });

  return (
    <Card
      title={t("settings.tabs.users")}
      actions={
        !readOnly && (
          <button type="button" onClick={() => setEditing("new")} className={smallButton()}>
            <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("settings.users.new")}
          </button>
        )
      }
    >
      {error && (
        <div className="p-4 pb-0">
          <ErrorBanner>{error}</ErrorBanner>
        </div>
      )}
      <HeadRow
        grid={GRID}
        labels={["name", "login", "role", "pin", "last", "status", ""].map((k) => (k ? t(`settings.users.col_${k}`) : ""))}
      />
      {(users.data ?? []).map((u) => {
        const locked = !!u.locked_until && new Date(u.locked_until) > new Date();
        return (
          <div key={u.id} className={`${GRID} h-12 border-b border-border text-table-cell ${u.is_active ? "" : "text-text-disabled"}`}>
            <div className="flex items-center gap-2 font-medium">
              {u.full_name}
              {locked && (
                <span className="inline-flex h-6 items-center gap-1 rounded-control bg-danger-soft px-2 text-label text-danger-text">
                  <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("settings.users.locked")}
                </span>
              )}
            </div>
            <div dir="ltr" className="text-end text-text-secondary">
              {u.username}
            </div>
            <div>{t(`roles.${u.role}`)}</div>
            <div className="flex items-center gap-2">
              <span className="tracking-widest text-text-secondary">••••••</span>
              {u.default_pin && (
                <span className="inline-flex h-6 items-center rounded-control bg-warning-soft px-2 text-label text-warning-text">{t("settings.users.defaultPin")}</span>
              )}
            </div>
            <div className="text-text-secondary">{u.last_login ? formatWhen(u.last_login) : "—"}</div>
            <div className="flex items-center gap-2">
              <Toggle checked={u.is_active} disabled={readOnly || toggle.isPending} label={t("settings.users.col_status")} onChange={() => toggle.mutate(u)} />
              <span className="text-label">{t(u.is_active ? "settings.users.active" : "settings.users.inactive")}</span>
            </div>
            <div className="flex gap-3">
              {!readOnly && locked && (
                <button type="button" className={linkButton} onClick={() => unlock.mutate(u)}>
                  {t("settings.users.unlock")}
                </button>
              )}
              {!readOnly && (
                <button type="button" className={linkButton} onClick={() => setEditing(u)}>
                  {t("settings.edit")}
                </button>
              )}
            </div>
          </div>
        );
      })}
      {/* How changes are confirmed: meaningless where nothing can be changed (owner PC, reception staff). */}
      {!readOnly && <Footnote>{t("settings.users.footnote")}</Footnote>}
      {editing && (
        <UserModal
          user={editing === "new" ? null : editing}
          gate={gate}
          onClose={() => setEditing(null)}
          onDone={(code) => {
            setEditing(null);
            refresh();
            if (code) setRecoveryCode(code);
          }}
        />
      )}
      {recoveryCode && <RecoveryCodeModal code={recoveryCode} onClose={() => setRecoveryCode(null)} />}
      {modal}
    </Card>
  );
}

type Gate = ReturnType<typeof useConfirmGate>["gate"];

function UserModal({ user, gate, onClose, onDone }: { user: User | null; gate: Gate; onClose: () => void; onDone: (recoveryCode?: string | null) => void }) {
  const [form, setForm] = useState({
    username: user?.username ?? "",
    full_name: user?.full_name ?? "",
    role: (user?.role ?? "reception") as Role,
    pin: "",
    password: "",
    confirm: "",
    email: user?.email ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const owner = user?.role === "owner";
  // Only the owner may give the owner role (accounts.rules.can_manage_user).
  const me = useMe().data;
  const actorIsOwner = me?.role === "owner";

  const action = () => {
    if (!user) return t("settings.users.actCreate", { name: form.full_name });
    if (form.role !== user.role) return t("settings.users.actRole", { name: user.full_name, role: t(`roles.${form.role}`) });
    return t("settings.users.actEdit", { name: user.full_name });
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    let newCode: string | null = null;
    try {
      await gate(action(), async (headers) => {
        if (!user) {
          await data(
            api.POST("/api/v1/users/", {
              headers,
              body: {
                username: form.username.trim(),
                full_name: form.full_name.trim(),
                role: form.role,
                pin: form.pin,
                email: form.email.trim(),
                ...(form.password ? { password: form.password } : {}),
              },
            }),
          );
          return;
        }
        const body: components["schemas"]["PatchedUserUpdateRequest"] = { version: user.version };
        if (form.full_name.trim() !== user.full_name) body.full_name = form.full_name.trim();
        if (form.username.trim() && form.username.trim() !== user.username) body.username = form.username.trim();
        if (!owner && form.role !== user.role) body.role = form.role;
        if (form.password) body.password = form.password;
        if (form.email.trim() !== (user.email ?? "")) body.email = form.email.trim();
        if (Object.keys(body).length > 1) {
          const saved = await data(api.PATCH("/api/v1/users/{id}", { params: { path: { id: user.id } }, headers, body }));
          // The owner's new password comes with a new one-time recovery code: shown once (review 2026-09-29, C-1).
          if (saved.recovery_code) newCode = saved.recovery_code;
        }
        if (form.pin) await data(api.POST("/api/v1/users/{id}/reset-pin", { params: { path: { id: user.id } }, headers, body: { pin: form.pin } }));
      });
      onDone(newCode);
    } catch (e) {
      if (!(e instanceof Cancelled)) setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  };

  // «رمز استعادة جديد»: the owner, for his own account (the old code stops working).
  const renewCode = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await gate(t("settings.users.actRecovery"), (headers) =>
        data(api.POST("/api/v1/users/{id}/recovery-code", { params: { path: { id: user!.id } }, headers })),
      );
      onDone(res.recovery_code);
    } catch (e) {
      if (!(e instanceof Cancelled)) setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  };

  const pinOk = user ? form.pin === "" || /^\d{4,6}$/.test(form.pin) : /^\d{4,6}$/.test(form.pin);
  const needsPassword = !user && form.role !== "reception";
  // A new password is typed twice (review 2026-09-28, UI-14): a typo would lock the owner out of their own PC.
  const mismatch = !!form.password && form.confirm !== form.password;
  // 8 characters at least: backup keys are only as strong as the owner's and managers' passwords (C-6).
  const shortPassword = !!form.password && form.password.length < 8;
  const valid = form.full_name.trim() && (user || form.username.trim()) && pinOk && (!needsPassword || form.password) && !mismatch && !shortPassword;
  const self = !!user && user.id === me?.id;

  return (
    <Modal
      title={user ? t("settings.users.editTitle", { name: user.full_name }) : t("settings.users.new")}
      width={520}
      onClose={onClose}
      footer={
        <>
          <button type="button" disabled={!valid || busy} onClick={save} className={buttons.primary}>
            {t("settings.save")}
          </button>
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="grid grid-cols-2 gap-4">
        <Field label={t("settings.users.col_name")} required>
          <TextInput value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} />
        </Field>
        <Field label={t("settings.users.col_login")} required={!user}>
          <TextInput dir="ltr" value={form.username} onChange={(e) => set({ username: e.target.value })} />
        </Field>
      </div>
      <Field label={t("settings.users.email")} hint={t("settings.users.emailHint")}>
        <TextInput dir="ltr" type="email" autoComplete="off" value={form.email} onChange={(e) => set({ email: e.target.value })} />
      </Field>
      {!owner && (
        <Field label={t("settings.users.col_role")}>
          <Segmented<Role>
            label={t("settings.users.col_role")}
            value={form.role}
            onChange={(role) => set({ role })}
            options={[
              { value: "reception", label: t("roles.reception") },
              { value: "manager", label: t("roles.manager") },
              ...(actorIsOwner ? [{ value: "owner" as Role, label: t("roles.owner") }] : []),
            ]}
          />
        </Field>
      )}
      <div className="grid grid-cols-2 gap-4">
        <Field
          label={user ? t("settings.users.newPin") : t("settings.users.pin")}
          required={!user}
          error={pinOk ? null : t("settings.users.pinRule")}
          hint={user ? t("settings.users.keepEmpty") : t("settings.users.pinRule")}
        >
          <TextInput
            dir="ltr"
            inputMode="numeric"
            maxLength={6}
            value={form.pin}
            invalid={!pinOk}
            onChange={(e) => set({ pin: toWestern(e.target.value).replace(/\D/g, "") })}
          />
        </Field>
        <Field
          label={user ? t("settings.users.newPassword") : t("settings.users.password")}
          required={needsPassword}
          hint={needsPassword ? t("settings.users.passwordManager") : t("settings.users.keepEmpty")}
          error={shortPassword ? t("settings.users.passwordShort") : null}
        >
          <TextInput type="password" autoComplete="new-password" value={form.password} onChange={(e) => set({ password: e.target.value })} />
        </Field>
      </div>
      {form.password && (
        <Field
          label={t("settings.users.confirmPassword")}
          required
          error={form.confirm && mismatch ? t("settings.users.passwordMismatch") : null}
          className="w-[calc(50%-8px)] self-end"
        >
          <TextInput
            type="password"
            autoComplete="new-password"
            value={form.confirm}
            invalid={!!form.confirm && mismatch}
            onChange={(e) => set({ confirm: e.target.value })}
          />
        </Field>
      )}
      {self && user?.role === "owner" && (
        <div className="flex flex-wrap items-center gap-3 rounded-control bg-bg-surface-2 px-3 py-2.5">
          <span className="flex-1 text-body">{user.has_recovery_code ? t("settings.users.recoveryHas") : t("settings.users.recoveryNone")}</span>
          <button type="button" disabled={busy} onClick={() => void renewCode()} className={linkButton}>
            {t("settings.users.recoveryNew")}
          </button>
        </div>
      )}
      <div className="text-label font-normal text-text-secondary">{t("settings.users.footnote")}</div>
    </Modal>
  );
}

/** The owner's one-time recovery code, shown once (review 2026-09-29, C-1): written down or printed, never stored. */
export function RecoveryCodeModal({ code, onClose }: { code: string; onClose: () => void }) {
  return (
    <Modal
      title={t("settings.users.recoveryTitle")}
      width={480}
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose} className={buttons.primary}>
          {t("settings.users.recoverySaved")}
        </button>
      }
    >
      <div className="text-body text-text-secondary">{t("settings.users.recoveryText")}</div>
      <div dir="ltr" className="rounded-card border border-border-strong bg-bg-surface-2 py-4 text-center font-mono text-[28px] font-semibold tracking-widest text-text-primary">
        {code}
      </div>
      <div className="rounded-control bg-warning-soft px-3 py-2.5 text-body text-warning-text">{t("settings.users.recoveryWarn")}</div>
    </Modal>
  );
}
