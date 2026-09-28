import { emptyForm, errorSummary, type Form, guestReady, validate } from "./model";

const base = (): Form => ({ ...emptyForm("2026-09-26"), guestMode: "picked", picked: {} as Form["picked"], room_type: "rt" });

test("a new guest needs a two-part name before the stay section opens", () => {
  const f = { ...emptyForm("2026-09-26"), guestMode: "new" as const };
  expect(guestReady(f)).toBe(false);
  expect(guestReady({ ...f, guest: { ...f.guest, full_name: "عثمان محمد" } })).toBe(true);
});

test("discount, reference, price edit and check-in rules (6.4 B)", () => {
  const f = { ...base(), discount: "15,000", deposit: "50,000", deposit_method: "transfer" as const };
  const errors = validate(f, false);
  expect(Object.keys(errors)).toEqual(["discount_reason", "deposit_reference"]);
  expect(errorSummary(errors)).toBe("يتعذر الحفظ — حقلان يحتاجان تصحيحًا: سبب الخصم، المرجع.");
  expect(validate({ ...base(), price: "105,000" }, false)).toEqual({ override_reason: "سبب تعديل السعر مطلوب" });
  expect(validate(base(), true)).toEqual({ room: "اختر غرفة للتسكين الآن" });
  expect(validate({ ...base(), deposit: "abc" }, false)).toEqual({ deposit: "مبلغ غير صحيح" });
  expect(validate({ ...base(), room: "r1", discount: "5,000", discount_reason: "عرض" }, true)).toEqual({});
});

test("booking review: a zero price, a discount above the price, a walk-in into a room not ready", () => {
  expect(validate({ ...base(), price: "0", override_reason: "اتفاق" }, false)).toEqual({ price: "مبلغ غير صحيح" });
  expect(validate({ ...base(), discount: "150,000", discount_reason: "عرض" }, false, 14_000_000)).toEqual({ discount: "الخصم أكبر من السعر" });
  expect(validate({ ...base(), room: "r1" }, true, 14_000_000, false)).toEqual({ room: "الغرفة لم تُجهَّز بعد — اختر غرفة جاهزة أو احفظ كحجز" });
  expect(validate({ ...base(), room: "r1" }, false, 14_000_000, false)).toEqual({}); // a booking may take a room being cleaned
});
