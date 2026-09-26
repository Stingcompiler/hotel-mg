import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { LoginPage } from "./LoginPage";

const USERS = [
  { id: "u1", full_name: "أحمد علي", role: "reception" },
  { id: "u2", full_name: "المدير", role: "manager" },
];
const STATUS = { role: "reception", version: "1.0.0", device_name: "RECEPTION-PC", imported_seq: null };

type Reply = { status: number; body: unknown };
let pinReplies: Reply[] = [];
const pinCalls: unknown[] = [];

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  session.signOut();
  pinCalls.length = 0;
  pinReplies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      if (url.pathname === "/api/v1/auth/users") return json(200, USERS);
      if (url.pathname === "/api/v1/system/status") return json(200, STATUS);
      if (url.pathname === "/api/v1/auth/pin") {
        pinCalls.push(await input.json());
        const reply = pinReplies.shift()!;
        return json(reply.status, reply.body);
      }
      return json(404, { code: "not_found" });
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>board</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const typePin = (pin: string) => [...pin].forEach((d) => fireEvent.click(screen.getByRole("button", { name: d })));

test("greets the selected user and shows this PC", async () => {
  renderLogin();
  expect(await screen.findByText("مرحبًا، أحمد")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /أحمد علي/ })).toHaveAttribute("aria-checked", "true");
  expect(await screen.findByText("RECEPTION-PC")).toBeInTheDocument();
  expect(screen.getByText("الخادم المحلي متصل")).toBeInTheDocument();
});

test("six digits sign in once and open the board", async () => {
  pinReplies = [{ status: 200, body: { token: "tok", user: { id: "u1" } } }];
  renderLogin();
  await screen.findByText("مرحبًا، أحمد");
  typePin("123456");
  expect(await screen.findByText("board")).toBeInTheDocument();
  expect(pinCalls).toEqual([{ user_id: "u1", pin: "123456" }]);
  expect(session.token).toBe("tok");
});

test("wrong PIN says how many attempts are left and clears the dots", async () => {
  pinReplies = [{ status: 401, body: { code: "authentication_failed", detail: "x", attempts_left: 3 } }];
  renderLogin();
  await screen.findByText("مرحبًا، أحمد");
  typePin("999999");
  expect(await screen.findByRole("alert")).toHaveTextContent("الرمز غير صحيح — بقيت 3 محاولات قبل القفل");
  expect(screen.getByRole("status")).toHaveAttribute("aria-label", "الأرقام المُدخلة: 0 من 6");
});

test("locked account disables the keypad and counts down", async () => {
  const until = new Date(Date.now() + 278_000).toISOString();
  pinReplies = [{ status: 423, body: { code: "account_locked", detail: "x", locked_until: until } }];
  renderLogin();
  await screen.findByText("مرحبًا، أحمد");
  typePin("111111");
  expect(await screen.findByText("الدخول مقفل مؤقتًا")).toBeInTheDocument();
  expect(screen.getByText(/حاول مجددًا بعد 4:3\d أو اطلب من المدير فتح القفل/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "5" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "طلب المدير" })).toBeInTheDocument();
});

test("the keyboard types digits (Arabic-Indic too) and Enter submits a 4-digit PIN", async () => {
  pinReplies = [{ status: 200, body: { token: "tok", user: { id: "u2" } } }];
  renderLogin();
  await screen.findByText("مرحبًا، أحمد");
  fireEvent.click(screen.getByRole("radio", { name: /المدير/ }));
  for (const key of ["١", "2", "٣", "4"]) fireEvent.keyDown(window, { key });
  fireEvent.keyDown(window, { key: "Enter" });
  await waitFor(() => expect(pinCalls).toEqual([{ user_id: "u2", pin: "1234" }]));
});
