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
