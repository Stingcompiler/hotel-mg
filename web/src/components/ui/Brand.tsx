import { t } from "@/i18n/t";

/** «ST» mark + «Sky Towers / نظام إدارة الفندق» (Shell Sidebar, login 6.1). Latin brand text stays LTR. */
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        dir="ltr"
        className="flex h-8 w-8 flex-none items-center justify-center rounded-control bg-primary text-label font-bold text-primary-text-on"
      >
        {t("app.logo")}
      </div>
      {!compact && (
        <div className="min-w-0">
          <div dir="ltr" className="text-end text-section-title leading-5">
            {t("app.name")}
          </div>
          <div className="text-label font-normal text-text-secondary">{t("app.subtitle")}</div>
        </div>
      )}
    </div>
  );
}
