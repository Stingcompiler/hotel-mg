import { t } from "@/i18n/t";

/** Stand-in for screens ported in F2; keeps every §10.4 route reachable from the shell. */
export function Placeholder({ titleKey }: { titleKey: string }) {
  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="m-0 text-page-title">{t(titleKey)}</h1>
      <p className="m-0 text-text-secondary">{t("common.comingSoon")}</p>
    </div>
  );
}
