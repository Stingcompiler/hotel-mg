export type Digits = "western" | "arabic";

const ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩";

let current: Digits = "western";

/** Set once from HotelSettings.digits; every formatter (screens and print templates) goes through `digits()`. */
export function setDigits(value: Digits): void {
  current = value;
}

export function digits(text: string, mode: Digits = current): string {
  return mode === "arabic" ? text.replace(/[0-9]/g, (d) => ARABIC_INDIC[Number(d)]) : text;
}

/** Accepts Western and Arabic-Indic digits (typed on either keyboard) and returns Western digits. */
export function toWestern(text: string): string {
  return text.replace(/[٠-٩]/g, (d) => String(ARABIC_INDIC.indexOf(d))).replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0));
}
