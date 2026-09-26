import { Outlet } from "react-router-dom";

import { useLatestImport, useMe, useSystemStatus } from "@/api/queries";
import { t } from "@/i18n/t";

import { OWNER_NAV } from "../nav";
import { OwnerBanner } from "./OwnerBanner";
import { Sidebar } from "./Sidebar";
import { useLogout } from "./useLogout";

/** Owner PC: read-only; the amber banner replaces the top bar (spec §10.4, artboard 6.12). */
export function OwnerShell() {
  const me = useMe().data;
  const status = useSystemStatus().data;
  const lastImport = useLatestImport().data ?? null;
  const logout = useLogout();

  return (
    <div className="flex h-screen">
      <Sidebar
        items={OWNER_NAV}
        userName={me?.full_name ?? ""}
        roleName={t("roles.owner")}
        onLogout={logout}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <OwnerBanner
          dataAsOf={status?.data_as_of ?? null}
          lastImport={lastImport ? { seq: lastImport.backup_seq ?? null, at: lastImport.created_at } : null}
        />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
