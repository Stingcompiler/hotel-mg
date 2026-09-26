import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, ApiError, data } from "@/api/client";
import { keys } from "@/api/queries";
import { t } from "@/i18n/t";
import { notify, onTrayBackup } from "@/lib/desktop";

/** Desktop shell glue (spec §11): the tray's «نسخة احتياطية الآن» runs here, with the signed-in session. */
export function DesktopBridge() {
  const queryClient = useQueryClient();
  useEffect(
    () =>
      onTrayBackup(async () => {
        try {
          const run = await data(api.POST("/api/v1/backup/run"));
          await notify(t("backup.title"), run.status === "ok" ? t("desktop.backupDone") : run.message);
        } catch (e) {
          await notify(t("backup.title"), e instanceof ApiError ? e.message : t("errors.error"));
        } finally {
          void queryClient.invalidateQueries({ queryKey: keys.systemStatus });
          void queryClient.invalidateQueries({ queryKey: ["backup"] });
        }
      }),
    [queryClient],
  );
  return null;
}
