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
const TONE = {
  solid: "bg-danger text-primary-text-on",
  danger: "bg-danger-soft text-danger-text",
  warning: "bg-warning-soft text-warning-text",
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
        <button type="button" disabled={backup.isPending} onClick={() => backup.mutate()} className={`${link} border-0 bg-transparent p-0 text-danger-text`}>
          {backup.isPending ? t("backup.running") : t("backup.now")}
        </button>
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
        <Link to="/settings/backup" className={`${link} text-warning-text`}>
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
        <Link to="/?filter=overdue" className={`${link} text-danger-text`}>
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
          className={`flex h-11 items-center gap-3 border-b border-bg-surface px-6 text-body font-medium ${TONE[bar.tone]}`}
        >
          {bar.icon}
          <span className="min-w-0 flex-1 truncate">{bar.text}</span>
          {bar.action}
        </div>
      ))}
    </div>
  );
}
