import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { LoginPage } from "./LoginPage";

const posts: unknown[] = [];
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  session.signOut();
  window.localStorage.clear();
  posts.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === "/api/v1/system/status") return json(200, { role: "reception", version: "1.0.0", device_name: "PC", imported_seq: null, needs_setup: true });
      if (path === "/api/v1/auth/users") return json(200, []);
      if (path === "/api/v1/auth/setup") {
        posts.push(await input.json());
        return json(200, { token: "t-new", user: { id: "u1", username: "boss", full_name: "مدير الفندق", role: "manager" } });
      }
      return json(404, { code: "not_found" });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("a new reception PC creates its manager on the login page, then signs in", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>لوحة الغرف</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("إعداد النظام لأول مرة")).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "إنشاء الحساب والدخول" });
  fireEvent.change(screen.getByLabelText("اسم المدير"), { target: { value: "مدير الفندق" } });
  fireEvent.change(screen.getByLabelText("اسم المستخدم"), { target: { value: "boss" } });
  fireEvent.change(screen.getByLabelText(/كلمة المرور \(6/), { target: { value: "secret-123" } });
  fireEvent.change(screen.getByLabelText("تأكيد كلمة المرور"), { target: { value: "secret-12" } });
  expect(screen.getByText("كلمتا المرور غير متطابقتين")).toBeInTheDocument();
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByLabelText("كلمتا المرور غير متطابقتين"), { target: { value: "secret-123" } });
  fireEvent.change(screen.getByLabelText(/الرمز السري/), { target: { value: "٢٤٦٨" } });
  fireEvent.click(submit);
  expect(await screen.findByText("لوحة الغرف")).toBeInTheDocument();
  expect(posts).toEqual([{ full_name: "مدير الفندق", username: "boss", password: "secret-123", pin: "2468" }]);
  await waitFor(() => expect(session.token).toBe("t-new"));
});
