import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";

import { RoomBoardPage } from "./RoomBoardPage";
import { type BoardRoom, cardLines } from "./roomText";

const DATE = "2026-09-26";
const NOW = new Date("2026-09-26T12:00:00");

function room(over: Partial<BoardRoom>): BoardRoom {
  return {
    id: "r",
    number: "101",
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
  [room({}), "", "متاحة"],
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
  ],
};

beforeEach(() => {
  session.signIn("tok");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
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
