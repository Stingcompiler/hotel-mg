import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DatabaseBackup, HardDrive, ServerCrash, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { api, data } from "@/api/client";
import { keys, useSystemStatus } from "@/api/queries";
import { useRoomBoard } from "@/features/rooms/RoomBoardPage";
import { formatWhen } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { t } from "@/i18n/t";

type Bar = { key: string; tone: "solid" | "danger" | "warning"; icon: ReactNode; text: ReactNode; action?: ReactNode };
// «الحد الأقصى ثلاثة أشرطة؛ الرابع يُطوى في الجرس» (6.14 B).
const MAX_BARS = 3;
// Calm rows (owner request 2026-10-18, decision 226): white row, a thin coloured start stripe and icon; only the
// server-down bar stays a solid red alert.
const TONE = {
  solid: { row: "bg-danger text-primary-text-on", stripe: "", icon: "" },
  danger: { row: "bg-bg-surface text-text-primary", stripe: "bg-danger", icon: "text-danger" },
  warning: { row: "bg-bg-surface text-text-primary", stripe: "bg-warning", icon: "text-warning" },
};

/**
 * 6.14 B system bars under the top bar, stacked by priority: server down (solid red) › backup late › disk space ›
 * overdue stays. They cannot be dismissed; each disappears when its cause does. Write buttons in the screens are
 * disabled while the server-down bar shows.
 */
export function SystemBars({ reception = true }: { reception?: boolean }) {
  const status = useSystemStatus();
  const queryClient = useQueryClient();
  const overdue = useRoomBoard(reception && !status.isError).data?.summary.overdue ?? 0;
  const backup = useMutation({
    mutationFn: () => data(api.POST("/api/v1/backup/run")),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: keys.systemStatus }),
  });

  const s = status.data;
  const bars: Bar[] = [];
  const icon = (Icon: typeof ServerCrash) => <Icon className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />;
  const link = "font-sans text-body font-semibold underline underline-offset-2";

  if (status.isError) {
    bars.push({
      key: "server",
      tone: "solid",
      icon: icon(ServerCrash),
      text: t("system.serverDown"),
      action: (
        <button
          type="button"
          onClick={() => void queryClient.refetchQueries()}
          className="h-7 rounded-control border border-primary-text-on bg-transparent px-3 font-sans text-label text-primary-text-on"
        >
          {t("system.retry")}
        </button>
      ),
    });
  }
  if (reception && s?.backup_stale_hours != null) {
    bars.push({
      key: "backup",
      tone: "danger",
      icon: icon(DatabaseBackup),
      text: (
        <>
          {t("system.backupLate", { hours: digits(String(s.backup_stale_hours)) })}
          {s.last_backup && ` — ${t("system.lastBackup", { when: formatWhen(s.last_backup) })}`}
        </>
      ),
      action: (
        <button type="button" disabled={backup.isPending} onClick={() => backup.mutate()} className={`${link} border-0 bg-transparent p-0 text-primary`}>
          {backup.isPending ? t("backup.running") : t("backup.now")}
        </button>
      ),
    });
  }
  // BAK-1 (review 2026-09-28): until an owner or a manager replaces the default password, backups carry no key slot
  // and open on no other PC — losing this PC would lose the hotel. Said plainly to everyone at reception.
  if (reception && s?.backup_opens_elsewhere === false) {
    bars.push({
      key: "backupLocal",
      tone: "warning",
      icon: icon(DatabaseBackup),
      text: t("system.backupLocalOnly"),
      action: (
        <Link to="/settings/users" className={`${link} text-primary`}>
          {t("system.changePassword")}
        </Link>
      ),
    });
  }
  if (s?.disk_low) {
    bars.push({
      key: "disk",
      tone: "warning",
      icon: icon(HardDrive),
      text: t("system.diskLow"),
      action: reception && (
        <Link to="/settings/backup" className={`${link} text-primary`}>
          {t("system.backupSettings")}
        </Link>
      ),
    });
  }
  if (reception && overdue > 0) {
    bars.push({
      key: "overdue",
      tone: "danger",
      icon: icon(TriangleAlert),
      text: overdue === 1 ? t("board.overdueBannerOne") : t("board.overdueBanner", { n: digits(String(overdue)) }),
      action: (
        <Link to="/?filter=overdue" className={`${link} text-primary`}>
          {t("system.view")}
        </Link>
      ),
    });
  }

  if (bars.length === 0) return null;
  return (
    <div className="flex flex-none flex-col">
      {bars.slice(0, MAX_BARS).map((bar) => (
        <div
          key={bar.key}
          role={bar.tone === "solid" ? "alert" : "status"}
          className={`bar-in relative flex h-10 items-center gap-3 border-b border-border px-6 text-body font-medium ${TONE[bar.tone].row}`}
        >
          {TONE[bar.tone].stripe && <span className={`absolute inset-y-0 start-0 w-1 ${TONE[bar.tone].stripe} ${bar.tone === "danger" ? "attention" : ""}`} aria-hidden />}
          <span className={`flex ${TONE[bar.tone].icon}`}>{bar.icon}</span>
          <span className="min-w-0 flex-1 truncate">{bar.text}</span>
          {bar.action}
        </div>
      ))}
    </div>
  );
}
