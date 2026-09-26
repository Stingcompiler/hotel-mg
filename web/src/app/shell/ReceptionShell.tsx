import { Outlet } from "react-router-dom";

import { useCurrentShift, useMe, useSystemStatus, useTaskCount } from "@/api/queries";
import { formatTime, formatWhen } from "@/i18n/dates";
import { t } from "@/i18n/t";
import { useMediaQuery } from "@/lib/useMediaQuery";

import { RECEPTION_NAV } from "../nav";
import { ClockGuard } from "./ClockGuard";
import { SessionLock } from "./SessionLock";
import { Sidebar } from "./Sidebar";
import { SystemBars } from "./SystemBars";
import { Toasts } from "./Toasts";
import { TopBar } from "./TopBar";
import { useLogout } from "./useLogout";

export function ReceptionShell() {
  const me = useMe().data;
  const status = useSystemStatus().data;
  const shift = useCurrentShift().data?.shift ?? null;
  const alerts = useTaskCount().data?.count ?? 0;
  const logout = useLogout();
  // 1366×768 artboards: the sidebar folds to the 64 px rail below 1600 px.
  const narrow = useMediaQuery("(max-width: 1599px)");

  const userName = me?.full_name ?? "";
  const backup =
    status?.backup_stale_hours != null
      ? ({ kind: "stale", hours: status.backup_stale_hours } as const)
      : status?.last_backup
        ? ({ kind: "ok", when: formatWhen(status.last_backup) } as const)
        : ({ kind: "never" } as const);

  return (
    <div className="flex h-screen">
      <Sidebar
        items={RECEPTION_NAV}
        userName={userName}
        roleName={me ? t(`roles.${me.role}`) : ""}
        followups={alerts}
        collapsed={narrow}
        onLogout={logout}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          userName={userName}
          shift={shift ? { userName: shift.opened_by, since: formatTime(shift.opened_at) } : null}
          backup={backup}
          alerts={alerts}
        />
        <SystemBars />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <Toasts />
      <ClockGuard />
      <SessionLock />
    </div>
  );
}
