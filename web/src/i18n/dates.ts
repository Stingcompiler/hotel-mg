import { differenceInCalendarDays, format, parseISO } from "date-fns";
import { ar } from "date-fns/locale";

import { digits } from "./digits";
import { t } from "./t";

const asDate = (value: string | Date) => (typeof value === "string" ? parseISO(value) : value);

/** "26 سبتمبر 2026" — Gregorian with Levantine month names (RTL notes «التواريخ»). */
export function formatDate(value: string | Date): string {
  return digits(format(asDate(value), "d MMMM yyyy", { locale: ar }));
}

/** "14:00" — shown inside dir="ltr" by the caller. */
export function formatTime(value: string | Date): string {
  return digits(format(asDate(value), "HH:mm"));
}

/** "اليوم 14:00" / "أمس 22:15" / "24 سبتمبر 09:30". */
export function formatWhen(value: string | Date, now: Date = new Date()): string {
  const date = asDate(value);
  const days = differenceInCalendarDays(now, date);
  const day = days === 0 ? t("dates.today") : days === 1 ? t("dates.yesterday") : digits(format(date, "d MMMM", { locale: ar }));
  return t("dates.at", { day, time: formatTime(date) });
}

/** "السبت 26 سبتمبر 2026" — the day name before the date (RTL notes «التواريخ»). */
export function formatDayDate(value: string | Date): string {
  const date = asDate(value);
  return t("dates.weekdayDate", { weekday: format(date, "EEEE", { locale: ar }), date: formatDate(date) });
}
