import { digits } from "./digits";
import { t } from "./t";

/** Arabic day counts: يوم / يومين / 3–10 أيام / 11+ يومًا. */
export function days(n: number): string {
  const abs = Math.abs(n);
  if (abs === 1) return t("count.day1");
  if (abs === 2) return t("count.day2");
  return t(abs >= 3 && abs <= 10 ? "count.daysFew" : "count.daysMany", { n: digits(String(abs)) });
}

/** "25 د" / "1 س 20 د" / multi-day spans in days — for «منذ …» since a status change. */
export function elapsed(fromIso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(fromIso).getTime()) / 60_000));
  if (minutes < 60) return t("count.minutes", { m: digits(String(minutes)) });
  if (minutes < 24 * 60) {
    return t("count.hoursMinutes", { h: digits(String(Math.floor(minutes / 60))), m: digits(String(minutes % 60)) });
  }
  return days(Math.floor(minutes / (24 * 60)));
}
