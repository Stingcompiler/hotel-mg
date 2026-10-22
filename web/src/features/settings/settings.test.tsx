import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { api, data } from "@/api/client";
import { session } from "@/api/session";

import { useConfirmGate } from "./confirm";
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
      const text = input.method === "GET" ? "" : await input.text();
      const body = text ? JSON.parse(text) : null;
      calls.push({ method: input.method, path, body, confirm: input.headers.get("X-Confirm-Token") });
      if (path === "/api/v1/auth/me") return json(USERS[0]);
      if (path === "/api/v1/users/") return json(USERS);
      if (path === "/api/v1/auth/confirm") {
        const b = body as { password?: string; pin?: string };
        if (b.password === "right") return json({ confirm_token: "ct-1", expires_in: 300, level: "password" });
        if (b.pin === "2468") return json({ confirm_token: "ct-pin", expires_in: 300, level: "pin" });
        return json({ code: "authentication_failed", detail: "بيانات الدخول غير صحيحة." }, 401);
      }
      if (path === "/api/v1/users/u2") {
        return input.headers.get("X-Confirm-Token") === "ct-1"
          ? json({ ...USERS[1], role: "manager", version: 5 })
          : json({ code: "password_confirmation_required", detail: "يتطلب كلمة المرور." }, 403);
      }
      // A day-to-day approval (decision 237): any fresh confirmation will do.
      if (path === "/api/v1/demo/approve") {
        // Only this test's PIN token: an earlier test's cached password token must not slip through.
        return input.headers.get("X-Confirm-Token") === "ct-pin" ? json({ ok: true }) : json({ code: "confirmation_required", detail: "تأكيد." }, 403);
      }
      return json({});
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("a role change asks for the manager's password only, keeps the session on a wrong one, then sends the token", async () => {
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
  // An account action: the password only, no choice of the PIN (decision 237).
  expect(screen.queryByRole("radio", { name: "رمز الدخول" })).toBeNull();
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
  expect(await screen.findByText("رمز افتراضي")).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: "تعديل" })[1]);
  fireEvent.change(screen.getByLabelText(/كلمة مرور جديدة/), { target: { value: "secret-22" } });
  const save = screen.getByRole("button", { name: "حفظ" });
  expect(save).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/تأكيد كلمة المرور/), { target: { value: "secret-2" } });
  expect(screen.getByText("كلمتا المرور غير متطابقتين")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/تأكيد كلمة المرور/), { target: { value: "secret-22" } });
  expect(save).toBeEnabled();
});

function GateProbe() {
  const { gate, modal } = useConfirmGate();
  const [done, setDone] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() =>
          void gate("اعتماد", (h) =>
            data(api.POST("/api/v1/demo/approve" as never, { headers: h } as never)).then(() => setDone(true)),
          ).catch(() => undefined)
        }
      >
        اعتماد
      </button>
      {done && <div>تم الاعتماد</div>}
      {modal}
    </>
  );
}

test("a day-to-day approval can be confirmed with the PIN (decision 237)", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <GateProbe />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "اعتماد" }));
  fireEvent.click(await screen.findByRole("radio", { name: "رمز الدخول" }));
  fireEvent.change(screen.getByLabelText("رمز الدخول"), { target: { value: "2468" } });
  fireEvent.click(screen.getByRole("button", { name: "تأكيد ومتابعة" }));
  expect(await screen.findByText("تم الاعتماد")).toBeInTheDocument();
  expect(calls.filter((c) => c.path === "/api/v1/auth/confirm").map((c) => c.body)).toEqual([{ pin: "2468" }]);
});
