import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Plus } from "lucide-react";
import { useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { ErrorBanner, Field, Segmented, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { Toggle } from "@/components/ui/Toggle";
import { formatWhen } from "@/i18n/dates";
import { toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { Cancelled, useConfirmGate } from "./confirm";
import { apiErrorText, Card, Footnote, HeadRow, linkButton, smallButton } from "./shared";

type User = components["schemas"]["User"];
type Role = "reception" | "manager";
const GRID = "grid grid-cols-[1.4fr_1fr_1fr_100px_1fr_110px_80px] items-center gap-4 px-4";
const USERS = ["settings", "users"] as const;

/** 6.11 A: users table; role, PIN, password and disabling ask for the manager's password first. */
export function UsersTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: USERS, queryFn: () => data(api.GET("/api/v1/users/")) });
  const { gate, modal } = useConfirmGate();
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
            <div className="tracking-widest text-text-secondary">••••••</div>
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
      <Footnote>{t("settings.users.footnote")}</Footnote>
      {editing && (
        <UserModal
          user={editing === "new" ? null : editing}
          gate={gate}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            refresh();
          }}
        />
      )}
      {modal}
    </Card>
  );
}

type Gate = ReturnType<typeof useConfirmGate>["gate"];

function UserModal({ user, gate, onClose, onDone }: { user: User | null; gate: Gate; onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({
    username: user?.username ?? "",
    full_name: user?.full_name ?? "",
    role: (user?.role === "manager" ? "manager" : "reception") as Role,
    pin: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const owner = user?.role === "owner";

  const action = () => {
    if (!user) return t("settings.users.actCreate", { name: form.full_name });
    if (form.role !== user.role) return t("settings.users.actRole", { name: user.full_name, role: t(`roles.${form.role}`) });
    return t("settings.users.actEdit", { name: user.full_name });
  };

  const save = async () => {
    setBusy(true);
    setError(null);
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
                ...(form.password ? { password: form.password } : {}),
              },
            }),
          );
          return;
        }
        const body: components["schemas"]["PatchedUserUpdateRequest"] = { version: user.version };
        if (form.full_name.trim() !== user.full_name) body.full_name = form.full_name.trim();
        if (!owner && form.role !== user.role) body.role = form.role;
        if (form.password) body.password = form.password;
        if (Object.keys(body).length > 1) await data(api.PATCH("/api/v1/users/{id}", { params: { path: { id: user.id } }, headers, body }));
        if (form.pin) await data(api.POST("/api/v1/users/{id}/reset-pin", { params: { path: { id: user.id } }, headers, body: { pin: form.pin } }));
      });
      onDone();
    } catch (e) {
      if (!(e instanceof Cancelled)) setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  };

  const pinOk = user ? form.pin === "" || /^\d{4,6}$/.test(form.pin) : /^\d{4,6}$/.test(form.pin);
  const needsPassword = !user && form.role === "manager";
  const valid = form.full_name.trim() && (user || form.username.trim()) && pinOk && (!needsPassword || form.password);

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
          <TextInput dir="ltr" value={form.username} readOnly={!!user} onChange={(e) => set({ username: e.target.value })} />
        </Field>
      </div>
      {!owner && (
        <Field label={t("settings.users.col_role")}>
          <Segmented<Role>
            label={t("settings.users.col_role")}
            value={form.role}
            onChange={(role) => set({ role })}
            options={[
              { value: "reception", label: t("roles.reception") },
              { value: "manager", label: t("roles.manager") },
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
        >
          <TextInput type="password" autoComplete="new-password" value={form.password} onChange={(e) => set({ password: e.target.value })} />
        </Field>
      </div>
      <div className="text-label font-normal text-text-secondary">{t("settings.users.footnote")}</div>
    </Modal>
  );
}
