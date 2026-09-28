import { Outlet } from "react-router-dom";

import { useCurrentShift, useMe, useSystemStatus, useTaskCount } from "@/api/queries";
import { formatTime, formatWhen } from "@/i18n/dates";
import { t } from "@/i18n/t";

import { OWNER_NAV, RECEPTION_NAV } from "../nav";
import { DefaultPasswordNotice } from "./DefaultPasswordNotice";
import { ClockGuard } from "./ClockGuard";
import { DesktopBridge } from "./DesktopBridge";
import { Notices } from "./Notices";
import { SessionLock } from "./SessionLock";
import { Sidebar } from "./Sidebar";
import { SystemBars } from "./SystemBars";
import { Toasts } from "./Toasts";
import { TopBar } from "./TopBar";
import { useLogout } from "./useLogout";
import { useSidebar } from "./useSidebar";

export function ReceptionShell() {
  const me = useMe().data;
  const status = useSystemStatus().data;
  const shift = useCurrentShift().data?.shift ?? null;
  const alerts = useTaskCount().data?.count ?? 0;
  const logout = useLogout();
  const sidebar = useSidebar();

  const userName = me?.full_name ?? "";
  // The account decides the menu (owner decision 2026-09-27): the owner also gets «لوحة المالك», first.
  const items = me?.role === "owner" ? [OWNER_NAV[0], ...RECEPTION_NAV] : RECEPTION_NAV;
  const backup =
    status?.backup_stale_hours != null
      ? ({ kind: "stale", hours: status.backup_stale_hours } as const)
      : status?.last_backup
        ? ({ kind: "ok", when: formatWhen(status.last_backup) } as const)
        : ({ kind: "never" } as const);

  return (
    <div className="flex h-screen">
      <Sidebar
        items={items}
        userName={userName}
        roleName={me ? t(`roles.${me.role}`) : ""}
        followups={alerts}
        collapsed={sidebar.collapsed}
        onToggle={sidebar.toggle}
        onLogout={logout}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          userName={userName}
          roleName={me ? t(`roles.${me.role}`) : ""}
          onLogout={logout}
          shift={shift ? { userName: shift.opened_by, since: formatTime(shift.opened_at) } : null}
          backup={backup}
          alerts={alerts}
        />
        <SystemBars />
        {me?.default_password ? (
          <DefaultPasswordNotice />
        ) : (
          me?.default_pin && me.role !== "reception" && <DefaultPasswordNotice kind="pin" />
        )}
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <Toasts />
      <Notices />
      <DesktopBridge />
      <ClockGuard />
      <SessionLock />
    </div>
  );
}
