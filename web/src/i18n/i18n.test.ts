import { formatDate, formatWhen } from "./dates";
import { digits, setDigits, toWestern } from "./digits";
import { formatMoney, parseMoney, toBase } from "./money";
import { errorMessage, t, tList } from "./t";

afterEach(() => setDigits("western"));

test("money formats minor units with separators, decimals and currency", () => {
  expect(formatMoney(1_500_000)).toBe("15,000");
  expect(formatMoney(4_200_050, { decimals: 2 })).toBe("42,000.50");
  expect(formatMoney(-1_500_000, { currency: true })).toBe("-15,000 ج.س");
  expect(formatMoney(1_500_000, { digits: "arabic" })).toBe("١٥,٠٠٠");
  expect(() => formatMoney(1.5)).toThrow(TypeError);
});

test("money parses what people type, on either keyboard", () => {
  expect(parseMoney("15,000")).toBe(1_500_000);
  expect(parseMoney("١٥٬٠٠٠")).toBe(1_500_000);
  expect(parseMoney("42000.5")).toBe(4_200_050);
  expect(parseMoney("-100 ج.س")).toBe(-10_000);
  expect(parseMoney("abc")).toBeNull();
  expect(parseMoney("1.234")).toBeNull();
});

test("digits follow the hotel setting everywhere", () => {
  expect(digits("08:00")).toBe("08:00");
  setDigits("arabic");
  expect(digits("08:00")).toBe("٠٨:٠٠");
  expect(toWestern("٠٨:٠٠ ۱۲")).toBe("08:00 12");
});

test("dates use Arabic month names", () => {
  expect(formatDate("2026-09-26")).toBe("26 سبتمبر 2026");
  const now = new Date(2026, 8, 26, 16, 0);
  expect(formatWhen(new Date(2026, 8, 26, 14, 0), now)).toBe("اليوم 14:00");
  expect(formatWhen(new Date(2026, 8, 25, 22, 15), now)).toBe("أمس 22:15");
  expect(formatWhen(new Date(2026, 8, 24, 9, 30), now)).toBe("24 سبتمبر 09:30");
});

test("strings come from ar.json with variables", () => {
  expect(t("topbar.shiftOpen", { name: "أحمد", time: "08:00" })).toBe("وردية مفتوحة · أحمد · منذ 08:00");
  expect(t("nope.missing")).toBe("nope.missing");
  expect(errorMessage("no_open_shift")).toBe("لا توجد وردية مفتوحة على هذا الجهاز — افتح وردية من «الصندوق» ثم أعد المحاولة.");
  expect(tList("lists.weekdays")).toHaveLength(7);
  expect(tList("nope")).toEqual([]);
  expect(errorMessage("weird_code")).toBe("حدث خطأ غير متوقع.");
  expect(errorMessage("x", "من الخادم")).toBe("من الخادم");
});

describe("toBase (review 2026-09-29, F-15)", () => {
  it("converts like the server: half away from zero", () => {
    expect(toBase(15_000, 250_000)).toBe(37_500_000); // 150.00 $ at 2,500
    expect(toBase(1, 150)).toBe(2); // 1.5 → 2
    expect(toBase(-1, 150)).toBe(-2); // a refund rounds away from zero too
    expect(toBase(1, 149)).toBe(1);
  });
});
