import { Outlet } from "react-router-dom";

import { useLatestImport, useMe, useSystemStatus } from "@/api/queries";
import { t } from "@/i18n/t";
import { useMediaQuery } from "@/lib/useMediaQuery";

import { OWNER_NAV } from "../nav";
import { Notices } from "./Notices";
import { OwnerBanner } from "./OwnerBanner";
import { ClockGuard } from "./ClockGuard";
import { SessionLock } from "./SessionLock";
import { Sidebar } from "./Sidebar";
import { SystemBars } from "./SystemBars";
import { useLogout } from "./useLogout";

/** Owner PC: read-only; the amber banner replaces the top bar (spec §10.4, artboard 6.12). */
export function OwnerShell() {
  const me = useMe().data;
  const status = useSystemStatus().data;
  const lastImport = useLatestImport().data ?? null;
  const logout = useLogout();
  // 1366×768 artboards: the sidebar folds to the 64 px rail below 1600 px.
  const narrow = useMediaQuery("(max-width: 1599px)");

  return (
    <div className="flex h-screen">
      <Sidebar
        items={OWNER_NAV}
        userName={me?.full_name ?? ""}
        roleName={t("roles.owner")}
        collapsed={narrow}
        onLogout={logout}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <OwnerBanner
          dataAsOf={status?.data_as_of ?? null}
          lastImport={lastImport ? { seq: lastImport.backup_seq ?? null, at: lastImport.created_at } : null}
        />
        <SystemBars reception={false} />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <Notices />
      <ClockGuard />
      <SessionLock />
    </div>
  );
}
