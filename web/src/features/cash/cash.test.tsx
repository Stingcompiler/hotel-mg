import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";

import { CashPage } from "./CashPage";

const OPEN = {
  shift: { id: "s1", device: "PC", opened_at: "2026-09-26T06:00:00Z", opened_by: "أحمد علي", opening: 5_000_000, closed_at: null, closed_by_name: "", expected: null, counted: null, difference: null, difference_reason: "", version: 2 },
  totals: {
    opening: 5_000_000,
    receipts: { cash: 19_000_000, bankak: 12_000_000, transfer: 1_000_000, total: 32_000_000 },
    expenses: { cash: 1_250_000, bankak: 0, transfer: 0, total: 1_250_000 },
    expected: 22_750_000,
    foreign: [{ currency: "USD", symbol: "$", cash: 15_000, total: 15_000, base: 37_500_000 }],
  },
  movements: [{ at: "2026-09-26T07:00:00Z", kind: "in", text: "دفعة — غرفة 203", amount: 12_000_000, method: "bankak", reference: "BOK-1", by: "أحمد علي", ref_id: "p1" }],
  last_closed: null,
  suggested_opening: 5_000_000,
};
const posts: { path: string; body: unknown }[] = [];

beforeEach(() => {
  session.signIn("tok");
  posts.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (input.method === "POST") posts.push({ path, body: await input.json() });
      const body = path === "/api/v1/shifts/current" ? OPEN : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("expected cash, the difference preview and a reason before closing", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <CashPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("227,500")).toBeInTheDocument();
  expect(screen.getByText("بنكك", { selector: "div" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/^المعدود في الدرج/), { target: { value: "225,000" } });
  expect(screen.getByText("− 2,500")).toBeInTheDocument();
  expect(screen.getByText("نقدي بعملة $")).toBeInTheDocument(); // dollars listed apart from the pounds drawer
  fireEvent.click(screen.getByRole("button", { name: "إغلاق الوردية" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("سبب الفرق مطلوب عند وجود فرق");
  fireEvent.change(screen.getByLabelText(/سبب الفرق/), { target: { value: "أُعيد لنزيل" } });
  fireEvent.click(screen.getByRole("button", { name: "إغلاق الوردية" }));
  // Closing is irreversible: a confirmation repeats expected, counted and the difference, then posts.
  const dialog = await screen.findByRole("dialog", { name: "تأكيد إغلاق الوردية" });
  expect(dialog).toHaveTextContent("227,500");
  expect(dialog).toHaveTextContent("225,000");
  expect(dialog).toHaveTextContent("− 2,500");
  expect(posts).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "إغلاق الوردية الآن" }));
  await waitFor(() => expect(posts).toEqual([{ path: "/api/v1/shifts/close", body: { counted: 22_500_000, difference_reason: "أُعيد لنزيل", version: 2 } }]));
});
