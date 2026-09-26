import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { setDigits } from "@/i18n/digits";

import { OWNER_NAV, RECEPTION_NAV } from "../nav";
import { OwnerBanner } from "./OwnerBanner";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

afterEach(() => setDigits("western"));

const inRouter = (ui: React.ReactNode, path = "/") => render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);

test("reception sidebar: artboard order, active item, follow-up badge", () => {
  inRouter(
    <Sidebar items={RECEPTION_NAV} userName="أحمد علي" roleName="موظف استقبال" followups={5} onLogout={() => {}} />,
    "/cash",
  );
  const links = screen.getAllByRole("link").map((a) => a.textContent);
  expect(links).toEqual(["لوحة الغرف", "الحجوزات", "النزلاء", "المتابعة5", "الصندوق", "المصروفات", "التقارير", "الإعدادات"]);
  expect(screen.getByRole("link", { name: "الصندوق" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("أ")).toBeInTheDocument(); // avatar initial
  expect(screen.getByRole("button", { name: "تسجيل الخروج" })).toBeInTheDocument();
});

test("owner sidebar and collapsed rail keep the badge-less owner menu", () => {
  inRouter(<Sidebar items={OWNER_NAV} userName="المالك" roleName="مالك" collapsed onLogout={() => {}} />, "/owner");
  expect(screen.getAllByRole("link").map((a) => a.getAttribute("title"))).toEqual([
    "لوحة المالك",
    "التقارير",
    "النزلاء",
    "النسخ والاستيراد",
    "الإعدادات",
  ]);
  expect(screen.queryByText("Sky Towers")).toBeNull();
});

test("top bar chips: open shift, stale backup, alert count in the hotel's digits", () => {
  setDigits("arabic");
  inRouter(
    <TopBar userName="أحمد علي" shift={{ userName: "أحمد علي", since: "08:00" }} backup={{ kind: "stale", hours: 26 }} alerts={5} />,
  );
  expect(screen.getByText("وردية مفتوحة · أحمد · منذ 08:00")).toBeInTheDocument();
  expect(screen.getByText("لم تُنشأ نسخة منذ ٢٦ ساعة")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "التنبيهات" })).toHaveTextContent("٥");
});

test("top bar without a shift or backups", () => {
  inRouter(<TopBar userName="سلمى حسن" shift={null} backup={{ kind: "never" }} alerts={0} />);
  expect(screen.getByText("لا توجد وردية مفتوحة")).toBeInTheDocument();
  expect(screen.getByText("لم تُنشأ نسخة بعد")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "التنبيهات" })).toHaveTextContent("");
});

test("owner banner shows the data date and the imported copy", () => {
  render(<OwnerBanner dataAsOf="2026-09-25T22:10:00" lastImport={{ seq: 117, at: "2026-09-25T22:15:00" }} />);
  expect(screen.getByText(/بيانات حتى 25 سبتمبر 2026 –/)).toBeInTheDocument();
  expect(screen.getByText("22:10")).toHaveAttribute("dir", "ltr");
  expect(screen.getByText(/النسخة رقم 117 · استُوردت/)).toBeInTheDocument();
});
