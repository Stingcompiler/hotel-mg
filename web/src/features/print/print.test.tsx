import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { PrintPage } from "./PrintPage";

const HOTEL = { name_ar: "فندق سكاي تاورز", name_latin: "Sky Towers Hotel", address: "الخرطوم", phone: "+249", digits: "western", money_decimals: 0 };
const RECEIPT = {
  hotel: HOTEL,
  receipt: "RCP-000014",
  kind: "دفعة",
  at: "2026-09-26T12:40:00Z",
  room: "203",
  guest: "محمد عثمان الطيب",
  invoice: "INV-000318",
  amount: 1_500_000,
  amount_in_words: "خمسة عشر ألف جنيه",
  method: "نقدي",
  reference: "",
  stay_total: 28_500_000,
  paid_to_date: 28_500_000,
  balance: 0,
  by: "أحمد علي",
  shift: "26/09 · صباحية",
};

beforeEach(() => {
  session.signIn("tok");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      const body = path === "/api/v1/payments/p1/receipt" ? RECEIPT : path === "/api/v1/system/status" ? { version: "1.0.0", role: "reception" } : {};
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  Object.defineProperty(document, "fonts", { value: { ready: Promise.resolve() }, configurable: true });
  window.print = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("the 80 mm receipt shows the amount in figures and words, then prints itself", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/print/receipt/p1"]}>
        <Routes>
          <Route path="/print/:kind/:id" element={<PrintPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("إيصال دفعة")).toBeInTheDocument();
  expect(screen.getByText("15,000")).toBeInTheDocument();
  expect(screen.getByText("خمسة عشر ألف جنيه")).toBeInTheDocument();
  await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1), { timeout: 2000 });
});
