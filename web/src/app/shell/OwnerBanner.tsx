import { Eye } from "lucide-react";

import { digits } from "@/i18n/digits";
import { formatDate, formatTime, formatWhen } from "@/i18n/dates";
import { t } from "@/i18n/t";

type Props = { dataAsOf: string | null; lastImport: { seq: number | null; at: string } | null };

/** Owner PC: the 56 px amber bar replaces the top bar (Owner Dashboard 6.12; tokens owner-banner-*). */
export function OwnerBanner({ dataAsOf, lastImport }: Props) {
  return (
    <div className="flex h-topbar flex-none items-center gap-3 border-b border-border bg-owner-banner-bg px-6 text-body font-semibold text-owner-banner-text">
      <Eye className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
      <span>
        {dataAsOf ? (
          <>
            {t("owner.dataUntil", { date: formatDate(dataAsOf) })} <span dir="ltr">{formatTime(dataAsOf)}</span>
            {" · "}
            {t("owner.readOnly")}
          </>
        ) : (
          t("owner.bannerNoData")
        )}
      </span>
      <div className="flex-1" />
      {lastImport && (
        <span className="font-medium">
          {t("owner.importedCopy", { seq: digits(String(lastImport.seq ?? "")), when: formatWhen(lastImport.at) })}
        </span>
      )}
    </div>
  );
}
