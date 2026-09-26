import { useQueryClient } from "@tanstack/react-query";
import { ServerCrash } from "lucide-react";

import { useSystemStatus } from "@/api/queries";
import { t } from "@/i18n/t";

/**
 * 6.14 B system bars under the top bar, stacked by priority. The server-down bar is solid red and comes first;
 * write buttons in the screens are disabled while it shows.
 */
export function SystemBars() {
  const status = useSystemStatus();
  const queryClient = useQueryClient();
  if (!status.isError) return null;
  return (
    <div role="alert" className="flex h-11 flex-none items-center gap-3 bg-danger px-6 text-body font-medium text-primary-text-on">
      <ServerCrash className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
      <span className="flex-1">{t("system.serverDown")}</span>
      <button
        type="button"
        onClick={() => void queryClient.refetchQueries()}
        className="h-7 rounded-control border border-primary-text-on bg-transparent px-3 font-sans text-label text-primary-text-on"
      >
        {t("system.retry")}
      </button>
    </div>
  );
}
