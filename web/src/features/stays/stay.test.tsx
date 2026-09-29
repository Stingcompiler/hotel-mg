import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { StayDetailPage } from "./StayDetailPage";

const STAY = {
  id: "s1",
  reservation: {
    id: "r1", guest: "g1", guest_name: "محمد عثمان الطيب", room_type: "t", room_type_name: "مزدوجة", room: "rm", room_number: "203",
    check_in_date: "2026-09-01", check_out_date: "2026-10-01", nights: 30, duration_kind: "monthly", duration_count: 1, status: "checked_in",
    total: 285_000_00, rate_snapshot: {}, notes: "", status_reason: "", folio: "f1", invoice: "INV-000318", balance: 1_500_000, version: 1, created_at: "2026-09-01T10:00:00Z",
  },
  checked_in_at: "2026-09-01T10:00:00Z", checked_out_at: null, last_night: "2026-09-30", segments: [], override_by_name: null, override_reason: "", version: 3,
  guest: { id: "g1", full_name: "محمد عثمان الطيب", phone: "+249912345678", nationality: "سوداني", id_type_label: "بطاقة وطنية", id_number: "••••9321", warning_note: "", companions: [] },
  room: { id: "rm", number: "203", floor: 2, room_type_name: "مزدوجة", status: "occupied", display_status: "occupied" },
  days_left: 3,
  log: [{ at: "2026-09-01T10:00:00Z", action: "stay.check_in", label: "تسكين", by: "أحمد علي" }],
};
const FOLIO = {
  id: "f1", invoice: "INV-000318", invoice_no: 318, reservation: "r1", guest_name: "محمد عثمان الطيب", room_number: "203", status: "open",
  totals: { charges: 30_000_000, discounts: -1_500_000, total: 28_500_000, paid: 27_000_000, balance: 1_500_000 },
  ledger: [
    { at: "2026-09-01T10:00:00Z", type: "line", id: "l1", kind: "room", text: "إقامة شهرية", debit: 30_000_000, credit: 0, balance: 30_000_000, reference: "", reason: "", reverses: null, by: "أحمد علي" },
    { at: "2026-09-10T10:00:00Z", type: "payment", id: "p1", kind: "payment", text: "دفعة — نقدي", debit: 0, credit: 5_000_000, balance: 25_000_000, reference: "", reason: "", reverses: null, by: "المدير" },
    { at: "2026-09-10T10:20:00Z", type: "payment", id: "p2", kind: "reversal", text: "عكس دفعة — خطأ إدخال", debit: 5_000_000, credit: 0, balance: 30_000_000, reference: "", reason: "خطأ", reverses: "p1", by: "المدير" },
  ],
};

let earlyQuote: object | null = null;

beforeEach(() => {
  earlyQuote = null;
  session.signIn("tok");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      const body =
        path === "/api/v1/stays/s1"
          ? STAY
          : path === "/api/v1/folios/f1"
            ? FOLIO
            : path === "/api/v1/stays/s1/checkout"
              ? { early_departure: earlyQuote }
              : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("header, reversal link, and the check-out rule for a debt", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/stays/s1"]}>
        <Routes>
          <Route path="/stays/:id" element={<StayDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("INV-000318")).toBeInTheDocument();
  expect(screen.getByText("تنتهي بعد 3 أيام")).toBeInTheDocument();
  expect(screen.getByText("القيد #2")).toBeInTheDocument(); // the reversal points at the payment it undoes
  fireEvent.click(screen.getByRole("tab", { name: /السجل/ }));
  expect(screen.getByText("تسكين")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "تسجيل خروج" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("لا يمكن تسجيل الخروج بدين")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "تسجيل الخروج" })).toBeDisabled();
  fireEvent.click(within(dialog).getByRole("button", { name: /تجاوز المدير/ }));
  fireEvent.change(within(dialog).getByLabelText("كلمة مرور المدير"), { target: { value: "pw" } });
  fireEvent.change(within(dialog).getByLabelText(/سبب الخروج بدين/), { target: { value: "يسدد غدًا" } });
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "تسجيل الخروج بدين" })).toBeEnabled());
});

test("leaving early shows the nights used at the price paid and the refund", async () => {
  earlyQuote = {
    nights_used: 12, nights_booked: 30, room_charges: 28_500_000, new_room_charges: 11_400_000, services: 0,
    paid: 27_000_000, refund: 15_600_000, balance_after: 0,
  };
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/stays/s1"]}>
        <Routes>
          <Route path="/stays/:id" element={<StayDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "تسجيل خروج" }));
  const dialog = screen.getByRole("dialog");
  expect(await within(dialog).findByText(/مغادرة مبكرة — 12 ليلة من 30 ليلة/)).toBeInTheDocument();
  expect(within(dialog).getByText("156,000 ج.س")).toBeInTheDocument(); // refunded
  expect(within(dialog).queryByText("لا يمكن تسجيل الخروج بدين")).toBeNull(); // settled: nothing owed
  expect(within(dialog).getByRole("button", { name: "تسجيل الخروج" })).toBeEnabled();
});

test("«عكس» a room charge asks for the manager when the server requires it", async () => {
  const bodies: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === "/api/v1/folios/f1/lines/l1/reverse") {
        bodies.push(await input.clone().json());
        const first = bodies.length === 1;
        return new Response(JSON.stringify(first ? { code: "override_required", detail: "يحتاج موافقة المدير." } : FOLIO), {
          status: first ? 403 : 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      const body = path === "/api/v1/stays/s1" ? STAY : path === "/api/v1/folios/f1" ? FOLIO : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/stays/s1"]}>
        <Routes>
          <Route path="/stays/:id" element={<StayDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText("INV-000318");
  expect(screen.getByText("معكوس")).toBeInTheDocument(); // the reversed payment
  const reverse = screen.getAllByRole("button", { name: "عكس" });
  expect(reverse).toHaveLength(1); // only the room charge: reversals and reversed entries have none
  fireEvent.click(reverse[0]);
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText(/سبب العكس/), { target: { value: "خطأ في السعر" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "عكس" }));
  const password = await within(dialog).findByLabelText(/كلمة مرور المدير/);
  expect(within(dialog).getByRole("button", { name: "عكس" })).toBeDisabled();
  fireEvent.change(password, { target: { value: "pw" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "عكس" }));
  await vi.waitFor(() => expect(bodies).toHaveLength(2));
  expect(bodies).toEqual([
    { reason: "خطأ في السعر", manager_password: "" },
    { reason: "خطأ في السعر", manager_password: "pw" },
  ]);
  await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull()); // closed after the reversal
});

test("«ردّ مبلغ» appears only when the guest has credit", async () => {
  const credit = { ...FOLIO, totals: { ...FOLIO.totals, paid: 30_000_000, balance: -1_500_000 } };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      const body = path === "/api/v1/stays/s1" ? STAY : path === "/api/v1/folios/f1" ? credit : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/stays/s1"]}>
        <Routes>
          <Route path="/stays/:id" element={<StayDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText("INV-000318");
  fireEvent.click(screen.getByRole("button", { name: "ردّ مبلغ" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("رصيد النزيل: 15,000 ج.س")).toBeInTheDocument();
  const save = within(dialog).getByRole("button", { name: "تسجيل الردّ" });
  expect(save).toBeDisabled(); // a reason is required
  fireEvent.change(within(dialog).getByLabelText(/سبب الردّ/), { target: { value: "مغادرة مبكرة" } });
  expect(save).toBeEnabled();
});

test("a payment in dollars is typed in dollars and shows its pounds before saving", async () => {
  const bodies: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === "/api/v1/currencies/") {
        const usd = { id: "c1", code: "USD", name: "دولار", symbol: "$", rate: 250_000, is_active: true, version: 1, updated_at: "" };
        return new Response(JSON.stringify([usd]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path === "/api/v1/folios/f1/payments") {
        bodies.push(await input.clone().json());
        return new Response(JSON.stringify({ id: "p9" }), { status: 201, headers: { "Content-Type": "application/json" } });
      }
      const body = path === "/api/v1/stays/s1" ? STAY : path === "/api/v1/folios/f1" ? FOLIO : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/stays/s1"]}>
        <Routes>
          <Route path="/stays/:id" element={<StayDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText("INV-000318");
  fireEvent.click(screen.getByRole("button", { name: "إضافة دفعة" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.click(await within(dialog).findByRole("radio", { name: "$" }));
  fireEvent.change(within(dialog).getByLabelText(/المبلغ/), { target: { value: "150" } });
  expect(within(dialog).getByText("يعادل 375,000 ج.س (بسعر 1 $ = 2,500)")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "تسجيل الدفعة" }));
  await vi.waitFor(() => expect(bodies).toEqual([{ method: "cash", reference: "", currency: "USD", foreign_amount: 15_000 }]));
});
