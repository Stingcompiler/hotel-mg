import { Link, Navigate, useParams } from "react-router-dom";

import { useMe, useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
import { t } from "@/i18n/t";

import { AlertRulesTab } from "./AlertRulesTab";
import { AuditTab } from "./AuditTab";
import { BackupTab } from "./BackupTab";
import { CurrenciesTab } from "./CurrenciesTab";
import { HotelTab } from "./HotelTab";
import { RoomsTab } from "./RoomsTab";
import { RoomTypesTab } from "./RoomTypesTab";
import { UsersTab } from "./UsersTab";

const TABS = ["users", "roomTypes", "rooms", "currencies", "alerts", "backup", "hotel", "audit"] as const;
type Tab = (typeof TABS)[number];
// Manager-only reads on the server; reception staff see the rest read-only.
const MANAGER_ONLY: Tab[] = ["users", "audit"];

/** 6.11 Settings: tab list on the start side (240 px), the open tab beside it (max 1200 px). */
export function SettingsPage() {
  const { tab } = useParams();
  const me = useMe().data;
  const offline = useSystemStatus().isError;
  if (!me) return null;
  const manager = me.role === "manager" || me.role === "owner";
  // Owner PC is read-only (spec §10.4); reception staff can look but not change; nothing saves without the server.
  const readOnly = !manager || session.role === "owner" || offline;
  const visible = TABS.filter((k) => manager || !MANAGER_ONLY.includes(k));
  const active = visible.find((k) => k === tab);
  if (!active) return <Navigate to={`/settings/${visible[0]}`} replace />;

  return (
    <div className="grid h-full grid-cols-[240px_1fr] grid-rows-[36px_1fr] gap-4 p-6 max-[1599px]:grid-cols-[200px_1fr] max-[1599px]:gap-3">
      <div className="col-span-2 flex items-center gap-3">
        <h1 className="m-0 text-page-title">{t("nav.settings")}</h1>
        <span className="text-text-disabled">/</span>
        <span className="text-section-title">{t(`settings.tabs.${active}`)}</span>
        {readOnly && <span className="text-label font-normal text-text-secondary">{offline ? t("settings.offline") : t("settings.readOnly")}</span>}
      </div>
      <nav className="flex flex-col gap-0.5 self-start rounded-card border border-border bg-bg-surface p-2">
        {visible.map((k) => (
          <Link
            key={k}
            to={`/settings/${k}`}
            aria-current={k === active ? "page" : undefined}
            className={`flex h-10 items-center rounded-control px-3 text-body no-underline ${
              k === active ? "bg-primary-soft font-semibold text-primary" : "font-medium text-text-primary hover:bg-bg-surface-2"
            }`}
          >
            {t(`settings.tabs.${k}`)}
          </Link>
        ))}
      </nav>
      <div className="flex min-h-0 min-w-0 max-w-[1200px] flex-col gap-4 overflow-auto">
        {active === "users" && <UsersTab readOnly={readOnly} />}
        {active === "roomTypes" && <RoomTypesTab readOnly={readOnly} />}
        {active === "rooms" && <RoomsTab readOnly={readOnly} />}
        {active === "currencies" && <CurrenciesTab readOnly={readOnly} owner={me.role === "owner"} />}
        {active === "alerts" && <AlertRulesTab readOnly={readOnly} owner={me.role === "owner"} />}
        {active === "backup" && <BackupTab readOnly={readOnly} />}
        {active === "hotel" && <HotelTab readOnly={readOnly} />}
        {active === "audit" && <AuditTab />}
      </div>
    </div>
  );
}
