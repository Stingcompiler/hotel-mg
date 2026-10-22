import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { OwnerDashboardPage } from "./OwnerDashboardPage";

let role = "reception";
let requested: string[] = [];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  session.signIn("t");
  requested = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      requested.push(path);
      if (path === "/api/v1/auth/me") return json({ id: "u", username: "desk", display_name: "أحمد", role });
      if (path === "/api/v1/system/status") return json({ role: "reception", hotel_id: "h1", can_adopt: false });
      if (path === "/api/v1/reports/owner-dashboard") return json({ code: "forbidden", detail: "هذه الصفحة للمدير والمالك." }, 403);
      return json({ code: "not_found" }, 404);
    }),
  );
});

afterEach(() => {
  session.signOut();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<div>لوحة الغرف</div>} />
          <Route path="/owner" element={<OwnerDashboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("reception opening /owner by its address goes to the room board (QA ج-2)", async () => {
  renderAt("/owner");
  await screen.findByText("لوحة الغرف");
  expect(requested).not.toContain("/api/v1/reports/owner-dashboard");
});

test("a refused or failed dashboard says why and offers a retry instead of loading forever", async () => {
  role = "manager";
  renderAt("/owner");
  expect(await screen.findByRole("alert")).toHaveTextContent("هذه الصفحة للمدير والمالك.");
  expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeInTheDocument();
  role = "reception";
});
