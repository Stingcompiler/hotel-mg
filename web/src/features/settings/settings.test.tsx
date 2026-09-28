import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { SettingsPage } from "./SettingsPage";

const USERS = [
  { id: "u1", username: "manager", full_name: "المدير", role: "manager", is_active: true, last_login: null, locked_until: null, version: 1, created_at: "", updated_at: "" },
  { id: "u2", username: "salma.h", full_name: "سلمى حسن", role: "reception", is_active: true, last_login: null, locked_until: null, version: 4, created_at: "", updated_at: "" },
];
const calls: { method: string; path: string; body: unknown; confirm: string | null }[] = [];

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  window.localStorage.clear();
  session.signIn("tok");
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      const body = input.method === "GET" ? null : await input.json();
      calls.push({ method: input.method, path, body, confirm: input.headers.get("X-Confirm-Token") });
      if (path === "/api/v1/auth/me") return json(USERS[0]);
      if (path === "/api/v1/users/") return json(USERS);
      if (path === "/api/v1/auth/confirm") {
        return (body as { password: string }).password === "right"
          ? json({ confirm_token: "ct-1", expires_in: 300 })
          : json({ code: "authentication_failed", detail: "بيانات الدخول غير صحيحة." }, 401);
      }
      if (path === "/api/v1/users/u2") {
        return input.headers.get("X-Confirm-Token") === "ct-1"
          ? json({ ...USERS[1], role: "manager", version: 5 })
          : json({ code: "confirmation_required", detail: "أعد إدخال كلمة المرور لتأكيد هذا الإجراء." }, 403);
      }
      return json({});
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("a role change asks for the manager's password, keeps the session on a wrong one, then sends the token", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/settings/users"]}>
        <Routes>
          <Route path="/settings/:tab" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("salma.h")).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: "تعديل" })[1]);
  fireEvent.click(screen.getByRole("radio", { name: "مدير" }));
  fireEvent.click(screen.getByRole("button", { name: "حفظ" }));

  expect(await screen.findByText("إجراء حساس: تغيير دور «سلمى حسن» إلى مدير")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("كلمة مرور المدير"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: "تأكيد ومتابعة" }));
  expect(await screen.findByText("بيانات الدخول غير صحيحة.")).toBeInTheDocument();
  expect(session.token).toBe("tok");

  fireEvent.change(screen.getByLabelText("كلمة مرور المدير"), { target: { value: "right" } });
  fireEvent.click(screen.getByRole("button", { name: "تأكيد ومتابعة" }));
  await waitFor(() =>
    expect(calls.filter((c) => c.method === "PATCH")).toEqual([
      { method: "PATCH", path: "/api/v1/users/u2", body: { version: 4, role: "manager" }, confirm: null },
      { method: "PATCH", path: "/api/v1/users/u2", body: { version: 4, role: "manager" }, confirm: "ct-1" },
    ]),
  );
});

test("a new password is typed twice and a default PIN is flagged", async () => {
  USERS[1] = { ...USERS[1], default_pin: true } as (typeof USERS)[number];
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/settings/users"]}>
        <Routes>
          <Route path="/settings/:tab" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("افتراضي 123456")).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: "تعديل" })[1]);
  fireEvent.change(screen.getByLabelText(/كلمة مرور جديدة/), { target: { value: "secret-22" } });
  const save = screen.getByRole("button", { name: "حفظ" });
  expect(save).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/تأكيد كلمة المرور/), { target: { value: "secret-2" } });
  expect(screen.getByText("كلمتا المرور غير متطابقتين")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/تأكيد كلمة المرور/), { target: { value: "secret-22" } });
  expect(save).toBeEnabled();
});
