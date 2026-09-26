import { LogOut } from "lucide-react";
import { NavLink } from "react-router-dom";

import { t } from "@/i18n/t";
import { digits } from "@/i18n/digits";

import type { NavItem } from "../nav";

type Props = {
  items: NavItem[];
  userName: string;
  roleName: string;
  followups?: number;
  collapsed?: boolean;
  onLogout: () => void;
};

/** «Shell Sidebar»: 240 px (rail 64 px when collapsed), on the start (right) side in RTL. */
export function Sidebar({ items, userName, roleName, followups = 0, collapsed = false, onLogout }: Props) {
  const justify = collapsed ? "justify-center" : "justify-start";
  return (
    <aside
      className={`${collapsed ? "w-sidebar-rail" : "w-sidebar"} flex h-full flex-none flex-col overflow-hidden border-e border-border bg-bg-surface`}
    >
      <div className="flex h-topbar items-center gap-2.5 border-b border-border px-4">
        {/* Latin brand text stays LTR inside the RTL layout (RTL notes «المقاطع LTR»). */}
        <div
          dir="ltr"
          className="flex h-8 w-8 flex-none items-center justify-center rounded-control bg-primary text-label font-bold text-primary-text-on"
        >
          {t("app.logo")}
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div dir="ltr" className="text-end text-section-title leading-5">
              {t("app.name")}
            </div>
            <div className="text-label font-normal text-text-secondary">{t("app.subtitle")}</div>
          </div>
        )}
      </div>

      <nav className={`flex flex-1 flex-col gap-0.5 py-3 ${collapsed ? "px-2" : "px-3"}`}>
        {items.map(({ key, path, icon: Icon }) => (
          <NavLink
            key={key}
            to={path}
            end={path === "/"}
            title={collapsed ? t(`nav.${key}`) : undefined}
            className={({ isActive }) =>
              `relative flex h-10 items-center gap-3 rounded-control px-3 text-body ${justify} ${
                isActive
                  ? "bg-primary-soft font-semibold text-primary hover:text-primary"
                  : "font-medium text-text-primary hover:bg-bg-surface-2 hover:text-text-primary"
              }`
            }
          >
            <Icon className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
            {!collapsed && <span className="flex-1 whitespace-nowrap">{t(`nav.${key}`)}</span>}
            {key === "followups" && followups > 0 && (
              // Count badge at the icon's top end corner, also on the collapsed rail (RTL notes «الشرائح والشارات»).
              <span
                className={`${collapsed ? "absolute start-1.5 top-1" : ""} inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-danger px-1.5 text-label font-semibold text-primary-text-on`}
              >
                {digits(String(followups))}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className={`flex flex-col gap-2 border-t border-border py-3 ${collapsed ? "px-2" : "px-3"}`}>
        <div className={`flex h-10 items-center gap-2.5 px-3 ${justify}`}>
          <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-primary-soft text-body font-semibold text-primary">
            {userName.trim().charAt(0)}
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="whitespace-nowrap text-body font-medium leading-5">{userName}</div>
              <div className="whitespace-nowrap text-label font-normal text-text-secondary">{roleName}</div>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onLogout}
          className={`flex h-9 items-center gap-3 rounded-control bg-transparent px-3 text-body font-medium text-text-secondary hover:bg-bg-surface-2 ${justify}`}
        >
          <LogOut className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
          {!collapsed && <span>{t("nav.logout")}</span>}
        </button>
      </div>
    </aside>
  );
}
