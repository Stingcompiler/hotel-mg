import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";

import { RoomBoardPage } from "./RoomBoardPage";
import { type BoardRoom, cardActions, cardInfo, cardLines } from "./roomText";

const DATE = "2026-09-26";
const NOW = new Date("2026-09-26T12:00:00");

function room(over: Partial<BoardRoom>): BoardRoom {
  return {
    id: "r",
    number: "101",
    name: "",
    floor: 1,
    room_type: "t",
    room_type_name: "مفردة",
    status: "ready",
    display_status: "ready",
    status_changed_at: null,
    maintenance_reason: "",
    in_service: true,
    manual_targets: ["maintenance"],
    version: 1,
    stay: null,
    next_reservation: null,
    ...over,
  };
}

const stay = (days_left: number) => ({
  id: "s",
  reservation: "res",
  guest_name: "عبدالله حسن موسى",
  guest_phone: "",
  check_in_date: "2026-09-17",
  check_out_date: "2026-09-25",
  last_night: "2026-09-24",
  days_left,
  duration_kind: "weekly" as const,
  duration_label: "أسبوعي",
  balance: 4_200_000,
  invoice: null,
});

test.each([
  [room({}), "", ""],
  [room({ status: "occupied", display_status: "occupied", stay: stay(0) }), "عبدالله حسن موسى", "تنتهي اليوم"],
  [room({ status: "occupied", display_status: "occupied", stay: stay(1) }), "عبدالله حسن موسى", "تنتهي غدًا"],
  [room({ status: "occupied", display_status: "occupied", stay: stay(5) }), "عبدالله حسن موسى", "تنتهي بعد 5 أيام"],
  [room({ status: "occupied", display_status: "occupied", stay: stay(12) }), "عبدالله حسن موسى", "تنتهي بعد 12 يومًا"],
  [room({ status: "occupied", display_status: "overdue", stay: stay(-2) }), "عبدالله حسن موسى", "متجاوزة منذ يومين"],
  [room({ status: "cleaning", display_status: "cleaning", status_changed_at: "2026-09-26T10:40:00" }), "", "منذ 1 س 20 د"],
  [
    room({ status: "maintenance", display_status: "maintenance", maintenance_reason: "تسرب مياه", status_changed_at: "2026-09-23T12:00:00" }),
    "تسرب مياه",
    "منذ 3 أيام",
  ],
  [
    room({ next_reservation: { id: "n", guest_name: "خالد إبراهيم", check_in_date: "2026-09-27", duration_kind: "daily", duration_label: "يومي" } }),
    "حجز: خالد إبراهيم",
    "محجوزة غدًا",
  ],
])("card lines follow the artboard wording", (r, main, sub) => {
  const lines = cardLines(r, DATE, NOW);
  expect([lines.main, lines.sub]).toEqual([main, sub]);
});

const BOARD = {
  date: DATE,
  summary: { rooms: 3, occupied: 1, occupancy_percent: 33, arrivals_today: 0, departures_today: 0, overdue: 1, by_status: {} },
  rooms: [
    room({ id: "a", number: "101" }),
    room({ id: "b", number: "305", floor: 3, status: "occupied", display_status: "overdue", stay: stay(-2), manual_targets: [] }),
    room({ id: "c", number: "410", floor: 4, status: "maintenance", display_status: "maintenance", maintenance_reason: "تسرب" }),
    room({ id: "d", number: "412", floor: 4, status: "cleaning", display_status: "cleaning", manual_targets: ["ready", "maintenance"], version: 7 }),
  ],
};

let posts: { path: string; body: unknown }[] = [];

beforeEach(() => {
  session.signIn("tok");
  posts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (input.method === "POST") posts.push({ path, body: await input.json() });
      const body =
        path === "/api/v1/rooms/board"
          ? BOARD
          : path.endsWith("/history")
            ? { count: 0, next: null, previous: null, results: [] }
            : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

function renderBoard(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <RoomBoardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("overdue link, filters and the drawer", async () => {
  renderBoard("/?filter=overdue"); // «عرض» on the overdue system bar
  await screen.findByText("عبدالله حسن موسى");
  expect(screen.getAllByRole("button", { name: /^(101|305|410)/ })).toHaveLength(1);

  fireEvent.click(screen.getByRole("radio", { name: /صيانة/ }));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
  expect(screen.getByText("لا توجد غرف في الصيانة في الطابق 1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "إظهار كل الغرف" }));

  fireEvent.click(screen.getByRole("button", { name: /^305/ }));
  const drawer = screen.getByRole("dialog");
  expect(within(drawer).getByText("انتهت الإقامة بنهاية يوم 24 سبتمبر — متجاوزة منذ يومين")).toBeInTheDocument();
  expect(within(drawer).getByText("تسجيل الخروج بدين يتطلب موافقة المدير.")).toBeInTheDocument();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
});

test.each([
  [room({ status: "occupied", display_status: "occupied", stay: stay(3) }), "عبدالله حسن موسى", [["بعد 3 أيام", "نهاية الإقامة"], ["42,000 ج.س", "المتبقي"]]],
  [room({ status: "occupied", display_status: "overdue", stay: { ...stay(-1), balance: 0 } }), "عبدالله حسن موسى", [["متجاوزة منذ يوم", "نهاية الإقامة"], ["مسدَّد", "المتبقي"]]],
  [room({ status: "occupied", display_status: "occupied", stay: { ...stay(0), balance: null } }), "عبدالله حسن موسى", [["اليوم", "نهاية الإقامة"], ["—", "المتبقي"]]],
  [room({ status: "cleaning", display_status: "cleaning", status_changed_at: "2026-09-26T10:40:00" }), "", [["1 س 20 د", "بانتظار التنظيف"]]],
  [room({ status: "maintenance", display_status: "maintenance", maintenance_reason: "تسرب مياه" }), "تسرب مياه", [["—", "في الصيانة"]]],
  [room({}), "", [["لا حجز قادم", "الحجز القادم"]]],
  [
    room({ next_reservation: { id: "n", guest_name: "خالد إبراهيم", check_in_date: "2026-09-26", duration_kind: "daily", duration_label: "يومي" } }),
    "حجز: خالد إبراهيم",
    [["اليوم", "وصول الحجز"]],
  ],
])("the detailed card puts each fact in its fixed place (decision 235)", (r, main, cells) => {
  const info = cardInfo(r, DATE, NOW);
  expect(info.main).toBe(main);
  expect(info.cells.map((c) => [c.value, c.caption])).toEqual(cells);
});

test("one action per state, the rest in the menu, and only the moves the server allows", () => {
  expect(cardActions(room({ status: "occupied", display_status: "occupied", stay: stay(2) }), DATE)).toEqual({ primary: "openStay", more: ["extend", "checkout"] });
  expect(cardActions(room({}), DATE)).toEqual({ primary: "checkIn", more: ["startMaintenance"] });
  const today = { id: "n", guest_name: "خالد", check_in_date: DATE, duration_kind: "daily" as const, duration_label: "يومي" };
  expect(cardActions(room({ next_reservation: today, manual_targets: [] }), DATE)).toEqual({ primary: "checkInBooking", more: [] });
  expect(cardActions(room({ status: "cleaning", manual_targets: ["ready", "maintenance"] }), DATE)).toEqual({ primary: "cleaned", more: ["startMaintenance"] });
  expect(cardActions(room({ status: "cleaning", manual_targets: [] }), DATE)).toEqual({ primary: "openRoom", more: [] });
  expect(cardActions(room({ status: "maintenance", manual_targets: ["ready", "cleaning"] }), DATE)).toEqual({ primary: "openRoom", more: [] });
});

test("the card's own buttons: confirm cleaning, and the «…» menu opens the drawer on the maintenance form", async () => {
  renderBoard();
  await screen.findByText("عبدالله حسن موسى");

  fireEvent.click(screen.getByRole("button", { name: "تأكيد التنظيف" }));
  await vi.waitFor(() => expect(posts).toEqual([{ path: "/api/v1/rooms/d/set-status", body: { status: "ready", reason: "", version: 7 } }]));
  expect(screen.queryByRole("dialog")).toBeNull(); // the action does not open the card
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "تأكيد التنظيف" })).toBeEnabled());

  const more = screen.getByRole("button", { name: "إجراءات الغرفة 101" });
  fireEvent.click(more);
  const menu = screen.getByRole("menu");
  fireEvent.keyDown(menu, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(more).toHaveFocus();

  fireEvent.click(more);
  fireEvent.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: "بدء صيانة" }));
  const drawer = screen.getByRole("dialog");
  expect(within(drawer).getByRole("textbox", { name: "سبب الصيانة" })).toBeInTheDocument();
});
