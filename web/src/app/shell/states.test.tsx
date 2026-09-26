import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";

import { ClockGuard } from "./ClockGuard";
import { SessionLock } from "./SessionLock";
import { SystemBars } from "./SystemBars";

const STATUS = {
  role: "reception",
  hotel_id: "h",
  last_backup: "2026-09-25T10:00:00Z",
  backup_stale_hours: 26,
  data_as_of: null,
  imported_seq: null,
  device_name: "PC",
  clock_blocked: true,
  clock_last_seen_at: "2026-09-26T12:32:00Z",
  disk_free_bytes: 1_000_000_000,
  disk_low: true,
  version: "1.0.0",
  schema_version: 1,
};
const ME = { id: "u1", username: "ahmed.ali", full_name: "أحمد علي", role: "reception" };
const BOARD = { rooms: [], summary: { rooms: 30, occupied: 18, occupancy_percent: 60, arrivals_today: 0, departures_today: 2, overdue: 2, by_status: {} } };

function answer(path: string) {
  if (path === "/api/v1/system/status") return STATUS;
  if (path === "/api/v1/auth/me") return ME;
  if (path === "/api/v1/rooms/board") return BOARD;
  if (path === "/api/v1/system/settings") return { session_lock_minutes: 15, digits: "western", money_decimals: 0 };
  if (path === "/api/v1/shifts/current") return { shift: { id: "s1", opened_by: "أحمد علي" } };
  return {};
}

beforeEach(() => {
  window.localStorage.clear();
  session.signIn("tok");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => new Response(JSON.stringify(answer(new URL(input.url).pathname)), { status: 200, headers: { "Content-Type": "application/json" } })),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  session.signOut();
});

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );

test("system bars stack by priority and stop at three", async () => {
  wrap(<SystemBars />);
  expect(await screen.findByText(/لم تُنشأ نسخة احتياطية منذ 26 ساعة/)).toBeInTheDocument();
  expect(screen.getByText("مساحة القرص أقل من 2 GB — النسخ الاحتياطية قد تفشل")).toBeInTheDocument();
  expect(await screen.findByText("2 إقامات انتهت دون إجراء")).toBeInTheDocument();
  const bars = screen.getAllByRole("status");
  expect(bars.map((b) => b.textContent?.slice(0, 12))).toEqual(["لم تُنشأ نسخ", "مساحة القرص ", "2 إقامات انت"]);
  expect(screen.getByRole("link", { name: "عرض" })).toHaveAttribute("href", "/?filter=overdue");
});

test("clock guard blocks with no close button; reception staff are sent to the manager sign-in", async () => {
  wrap(<ClockGuard />);
  const dialog = await screen.findByRole("alertdialog", { name: "ساعة الجهاز غير صحيحة" });
  expect(dialog).toHaveTextContent("آخر عملية مسجَّلة");
  expect(screen.queryByRole("button", { name: "إغلاق" })).toBeNull();
  expect(screen.getByRole("button", { name: "إعادة الفحص" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /تسجيل دخول المدير/ })).toBeInTheDocument();
});

test("the session locks after the hotel's idle minutes and keeps the page underneath", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  wrap(
    <>
      <input aria-label="مسودة" defaultValue="نص غير محفوظ" />
      <SessionLock />
    </>,
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.queryByRole("dialog")).toBeNull();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15 * 60_000);
  });
  expect(screen.getByRole("dialog", { name: "قُفلت الجلسة بعد 15 دقيقة خمول" })).toBeInTheDocument();
  expect(screen.getByLabelText("مسودة")).toHaveValue("نص غير محفوظ");
});
