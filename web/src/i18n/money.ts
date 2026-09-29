import { digits as applyDigits, type Digits, toWestern } from "./digits";

/** Minor units per currency unit (piasters). Money is never a float in the app (spec §5, §10.5). */
export const MINOR = 100;

type MoneyFormat = { digits?: Digits; decimals?: 0 | 2; currency?: boolean };

let defaultDecimals: 0 | 2 = 0;

export function setMoneyDecimals(value: number): void {
  defaultDecimals = value === 2 ? 2 : 0;
}

/** 1_500_000 → "15,000" (or "15,000.00"); thousands separator «,», currency «ج.س» after the number. */
export function formatMoney(minor: number, options: MoneyFormat = {}): string {
  if (!Number.isInteger(minor)) throw new TypeError(`money must be integer minor units, got ${minor}`);
  const decimals = options.decimals ?? defaultDecimals;
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / MINOR)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fraction = decimals === 2 ? `.${String(abs % MINOR).padStart(2, "0")}` : "";
  const text = applyDigits(`${sign}${whole}${fraction}`, options.digits);
  return options.currency ? `${text} ج.س` : text;
}

/** Cents of a foreign currency → base minor units at ``rate`` (base minor per whole unit), rounded half away from
 *  zero like the server (billing.rules.to_base): the one conversion of the app (review 2026-09-29, F-15). */
export function toBase(foreignMinor: number, rate: number): number {
  const numerator = foreignMinor * rate;
  const sign = numerator < 0 ? -1 : 1;
  const abs = Math.abs(numerator);
  return sign * (Math.floor(abs / MINOR) + (2 * (abs % MINOR) >= MINOR ? 1 : 0));
}

/** "15,000" / "١٥٬٠٠٠" / "15000.5" → 1_500_050. Returns null for anything that is not an amount. */
export function parseMoney(text: string): number | null {
  const clean = toWestern(text).replace(/[,٬\s]/g, "").replace("٫", ".").replace("ج.س", "");
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(clean);
  if (!match) return null;
  const [, sign, whole, fraction = ""] = match;
  const minor = Number(whole) * MINOR + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(minor)) return null;
  return sign ? -minor : minor;
}
