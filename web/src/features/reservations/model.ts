import type { components } from "@api/schema";

import { fieldsToFix } from "@/i18n/counts";
import { parseMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

export type GuestRow = components["schemas"]["GuestListItem"];
export type Quote = components["schemas"]["Quote"];
export type Kind = components["schemas"]["BookingDurationKindEnum"];
export type Method = components["schemas"]["PaymentMethodEnum"];
export type IdType = components["schemas"]["IdTypeEnum"];

export type NewGuest = {
  full_name: string;
  phone: string;
  nationality: string;
  id_type: IdType | "";
  id_number: string;
  companions: { name: string; relation: string }[];
  photo: File | null;
};

export type Form = {
  guestMode: "search" | "new" | "picked";
  picked: GuestRow | null;
  guest: NewGuest;
  room_type: string;
  room: string | null;
  check_in_date: string;
  duration_kind: Kind;
  count: number;
  option_key: string | null;
  price: string | null; // null = price from the rate plan
  override_reason: string;
  discount: string;
  discount_reason: string;
  deposit: string;
  deposit_method: Method;
  deposit_reference: string;
  deposit_currency: string; // "" = the hotel's currency
  manager_password: string;
  manager_reason: string;
  needManager: boolean;
};

export function emptyForm(today: string): Form {
  return {
    guestMode: "search",
    picked: null,
    guest: { full_name: "", phone: "", nationality: t("newRes.nationalityDefault"), id_type: "", id_number: "", companions: [], photo: null },
    room_type: "",
    room: null,
    check_in_date: today,
    duration_kind: "daily",
    count: 1,
    option_key: null,
    price: null,
    override_reason: "",
    discount: "",
    discount_reason: "",
    deposit: "",
    deposit_method: "cash",
    deposit_reference: "",
    deposit_currency: "",
    manager_password: "",
    manager_reason: "",
    needManager: false,
  };
}

/** Amount field → minor units: blank is 0, anything unparseable is null (shown as an error). */
export const amount = (text: string): number | null => (text.trim() === "" ? 0 : parseMoney(text));

export function guestReady(form: Form): boolean {
  return form.guestMode === "picked" || (form.guestMode === "new" && form.guest.full_name.trim().split(/\s+/).length >= 2);
}

export type Errors = Partial<Record<
  "full_name" | "room_type" | "room" | "price" | "override_reason" | "discount" | "discount_reason" | "deposit" | "deposit_reference" | "manager",
  string
>>;

const FIELD_NAMES: Record<keyof Errors, string> = {
  full_name: "newRes.fullName",
  room_type: "newRes.roomType",
  room: "newRes.room",
  price: "newRes.price",
  override_reason: "newRes.overrideReason",
  discount: "newRes.discount",
  discount_reason: "newRes.discountReason",
  deposit: "newRes.deposit",
  deposit_reference: "newRes.reference",
  manager: "newRes.managerPassword",
};

/** Required-field checks before sending (the server validates again and has the final word). */
export function validate(form: Form, checkInNow: boolean, price: number | null = null, roomReady = true): Errors {
  const e: Errors = {};
  if (form.guestMode === "new" && !guestReady(form)) e.full_name = t("newRes.errFullName");
  if (!form.room_type) e.room_type = t("newRes.errRoomType");
  if (checkInNow && !form.room) e.room = t("newRes.errRoom");
  // Walk-in into a room still being cleaned: the server refuses it; say so before sending.
  else if (checkInNow && !roomReady) e.room = t("newRes.errRoomNotReady");
  if (form.price !== null) {
    const edited = amount(form.price);
    if (edited === null || edited <= 0) e.price = t("newRes.errAmount");
    if (!form.override_reason.trim()) e.override_reason = t("newRes.errOverrideReason");
  }
  const discount = amount(form.discount);
  if (discount === null) e.discount = t("newRes.errAmount");
  else if (price !== null && discount > price) e.discount = t("newRes.errDiscountTooBig");
  else if (discount > 0 && !form.discount_reason.trim()) e.discount_reason = t("newRes.errDiscountReason");
  const deposit = amount(form.deposit);
  if (deposit === null) e.deposit = t("newRes.errAmount");
  else if (deposit > 0 && form.deposit_method !== "cash" && !form.deposit_reference.trim())
    e.deposit_reference = t("newRes.errReference");
  if (form.needManager && (!form.manager_password || !form.manager_reason.trim())) e.manager = t("newRes.errManager");
  return e;
}

export function errorSummary(errors: Errors): string {
  const keys = Object.keys(errors) as (keyof Errors)[];
  return t("newRes.cannotSave", { count: fieldsToFix(keys.length), fields: keys.map((k) => t(FIELD_NAMES[k])).join("، ") });
}
