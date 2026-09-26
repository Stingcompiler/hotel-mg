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

function plural(n: number, one: string, two: string, few: string, many: string): string {
  if (n === 1) return t(one);
  if (n === 2) return t(two);
  return t(n >= 3 && n <= 10 ? few : many, { n: digits(String(n)) });
}

/** ليلة واحدة / ليلتان / 3–10 ليالٍ / 11+ ليلة. */
export const nights = (n: number) => plural(n, "count.night1", "count.night2", "count.nightsFew", "count.nightsMany");
export const fieldsToFix = (n: number) => plural(n, "count.fields1", "count.fields2", "count.fieldsFew", "count.fieldsMany");
export const roomsAvailable = (n: number) => plural(n, "count.rooms1", "count.rooms2", "count.roomsFew", "count.roomsMany");
export const previousStays = (n: number) =>
  n === 0 ? t("count.stays0") : plural(n, "count.stays1", "count.stays2", "count.staysFew", "count.staysMany");
export const staysCount = (n: number) =>
  n === 0 ? t("count.staysN0") : plural(n, "count.staysN1", "count.staysN2", "count.staysNFew", "count.staysNMany");
