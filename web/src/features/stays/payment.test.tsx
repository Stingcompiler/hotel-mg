import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { session } from "@/api/session";

import { PaymentModal } from "./PaymentModal";

const posts: string[] = [];

beforeEach(() => {
  session.signIn("tok");
  posts.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (input.method === "POST") {
        posts.push(path);
        await new Promise((r) => setTimeout(r, 30)); // the server takes a moment
        return new Response(JSON.stringify({ id: "p1" }), { status: 201, headers: { "Content-Type": "application/json" } });
      }
      const body = path === "/api/v1/currencies/" ? [] : { auto_print_receipt: false };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("Enter twice records one payment (review 2026-09-28, UI-1)", async () => {
  const done = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PaymentModal folioId="f1" room="203" balance={1_000_000} onClose={() => undefined} onDone={done} />
    </QueryClientProvider>,
  );
  const amount = screen.getByRole("textbox");
  fireEvent.keyDown(amount, { key: "Enter" });
  fireEvent.keyDown(amount, { key: "Enter" });
  await waitFor(() => expect(done).toHaveBeenCalled());
  expect(posts).toEqual(["/api/v1/folios/f1/payments"]);
});
