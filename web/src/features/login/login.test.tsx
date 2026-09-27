import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { session } from "@/api/session";

import { LoginPage } from "./LoginPage";

const USERS = [
  { id: "u1", full_name: "أحمد علي", role: "reception" },
  { id: "u2", full_name: "المدير", role: "manager" },
];
const STATUS: Record<string, unknown> = { role: "reception", version: "1.0.0", device_name: "RECEPTION-PC", imported_seq: null };
const DEFAULT_LOGIN = { username: "admin", password: "123456", pin: "123456" };

type Reply = { status: number; body: unknown };
let pinReplies: Reply[] = [];
let passwordReply: Reply = { status: 200, body: { token: "tok", user: { id: "o1", role: "owner" } } };
let status: Record<string, unknown> = STATUS;
const pinCalls: unknown[] = [];
const passwordCalls: unknown[] = [];

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  session.signOut();
  window.localStorage.clear();
  pinCalls.length = 0;
  passwordCalls.length = 0;
  passwordReply = { status: 200, body: { token: "tok", user: { id: "o1", role: "owner" } } };
  pinReplies = [];
  status = STATUS;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      if (url.pathname === "/api/v1/auth/users") return json(200, USERS);
      if (url.pathname === "/api/v1/system/status") return json(200, status);
      if (url.pathname === "/api/v1/auth/password") {
        passwordCalls.push(await input.json());
        return json(passwordReply.status, passwordReply.body);
      }
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

function renderLogin(mode: "password" | "pin" = "pin") {
  if (mode === "pin") window.localStorage.setItem("skytowers.loginMode", "pin"); // «دخول سريع» remembered on this PC
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>board</div>} />
          <Route path="/owner" element={<div>owner dashboard</div>} />
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

test("a server that does not answer is named, not «unexpected error»", async () => {
  pinReplies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      if (url.pathname === "/api/v1/auth/users") return json(200, USERS);
      if (url.pathname === "/api/v1/system/status") return json(200, STATUS);
      if (url.pathname === "/api/v1/auth/pin") return new Response("", { status: 500 }); // Vite proxy: ECONNREFUSED
      throw new TypeError("Failed to fetch");
    }),
  );
  renderLogin();
  await screen.findByText("مرحبًا، أحمد");
  typePin("123456");
  expect(await screen.findByRole("alert")).toHaveTextContent("تعذّر الاتصال بالخادم المحلي");
});

test("a new install opens on the username and password form with the default owner account to fill", async () => {
  status = { ...STATUS, default_login: DEFAULT_LOGIN };
  renderLogin("password");
  expect(await screen.findByRole("heading", { name: "تسجيل الدخول" })).toBeInTheDocument();
  expect(await screen.findByText("أول دخول؟ استخدم حساب المالك الجاهز")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "تعبئة الحقول" }));
  fireEvent.click(screen.getByRole("button", { name: "دخول" }));
  expect(await screen.findByText("owner dashboard")).toBeInTheDocument();
  expect(passwordCalls).toEqual([{ username: "admin", password: "123456" }]);
});

test("the account decides where the app opens: staff go to the board", async () => {
  passwordReply = { status: 200, body: { token: "tok", user: { id: "u1", role: "reception" } } };
  renderLogin("password");
  fireEvent.change(await screen.findByLabelText("اسم المستخدم"), { target: { value: " ahmed.ali " } });
  fireEvent.change(screen.getByLabelText("كلمة المرور"), { target: { value: "secret-1" } });
  fireEvent.click(screen.getByRole("button", { name: "دخول" }));
  expect(await screen.findByText("board")).toBeInTheDocument();
  expect(passwordCalls).toEqual([{ username: "ahmed.ali", password: "secret-1" }]);
  expect(screen.queryByText("أول دخول؟ استخدم حساب المالك الجاهز")).not.toBeInTheDocument();
});

test("«دخول سريع» switches to the PIN pad and back", async () => {
  renderLogin("password");
  fireEvent.click(await screen.findByRole("button", { name: "دخول سريع بالرمز السري" }));
  expect(await screen.findByText("مرحبًا، أحمد")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "الدخول باسم المستخدم وكلمة المرور" }));
  expect(await screen.findByRole("heading", { name: "تسجيل الدخول" })).toBeInTheDocument();
});
test("an owner PC with no accounts still opens on the login fields, never a setup screen", async () => {
  status = { ...STATUS, role: "owner", owner_public_key: "age1xyz", needs_setup: false };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      if (url.pathname === "/api/v1/auth/users") return json(200, []);
      if (url.pathname === "/api/v1/system/status") return json(200, status);
      return json(404, { code: "not_found" });
    }),
  );
  renderLogin("password");
  expect(await screen.findByRole("heading", { name: "تسجيل الدخول" })).toBeInTheDocument();
  expect(screen.getByLabelText("اسم المستخدم")).toBeInTheDocument();
  expect(screen.queryByText("إعداد جهاز المالك")).not.toBeInTheDocument();
});
