import { Bell, ChevronDown, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

type Props = {
  userName: string;
  /** `null` when no shift is open on this device. */
  shift: { userName: string; since: string } | null;
  backup: { kind: "ok"; when: string } | { kind: "stale"; hours: number } | { kind: "never" };
  alerts: number;
};

/** «Shell TopBar»: 56 px; search, shift chip, backup chip, alerts, user. */
export function TopBar({ userName, shift, backup, alerts }: Props) {
  const backupChip =
    backup.kind === "stale"
      ? { text: t("topbar.backupStale", { hours: digits(String(backup.hours)) }), tone: "bg-danger-soft text-danger-text" }
      : backup.kind === "ok"
        ? { text: t("topbar.backupAt", { when: backup.when }), tone: "bg-success-soft text-success-text" }
        : { text: t("topbar.backupNever"), tone: "bg-danger-soft text-danger-text" };

  return (
    <header className="flex h-topbar flex-none items-center gap-3 border-b border-border bg-bg-surface px-6">
      <div className="flex h-9 w-[360px] items-center gap-2 rounded-control border border-border-strong bg-bg-surface px-3 text-body text-text-disabled">
        <Search className="h-icon w-icon flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
        <span className="truncate">{t("topbar.search")}</span>
      </div>

      <span
        className={`inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-control px-2.5 text-label ${
          shift ? "bg-success-soft text-success-text" : "bg-bg-surface-2 text-text-secondary"
        }`}
      >
        <span className={`h-2 w-2 rounded-full ${shift ? "bg-success" : "bg-text-disabled"}`} />
        {shift
          ? t("topbar.shiftOpen", { name: shift.userName.split(" ")[0], time: shift.since })
          : t("topbar.shiftNone")}
      </span>

      <div className="flex-1" />

      <span className={`inline-flex h-7 items-center whitespace-nowrap rounded-control px-2.5 text-label ${backupChip.tone}`}>
        {backupChip.text}
      </span>

      <Link
        to="/followups"
        aria-label={t("topbar.alerts")}
        className="relative flex h-9 w-9 items-center justify-center rounded-control border border-transparent text-text-primary hover:bg-bg-surface-2 hover:text-text-primary"
      >
        <Bell className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
        {alerts > 0 && (
          <span className="absolute start-0 top-0 box-content inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full border-2 border-bg-surface bg-danger px-[5px] text-[11px] font-semibold text-primary-text-on">
            {digits(String(alerts))}
          </span>
        )}
      </Link>

      <button
        type="button"
        className="flex h-9 items-center gap-2 rounded-control border border-transparent bg-transparent pe-2 ps-3 text-body text-text-primary hover:bg-bg-surface-2"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-soft text-label font-semibold text-primary">
          {userName.trim().charAt(0)}
        </span>
        <span>{userName}</span>
        <ChevronDown className="h-icon-inline w-icon-inline text-text-secondary" strokeWidth={1.75} aria-hidden />
      </button>
    </header>
  );
}
