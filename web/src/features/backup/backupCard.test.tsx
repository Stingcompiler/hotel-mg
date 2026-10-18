import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";

import { BackupCard } from "./BackupCard";

let canAdopt = true;
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  canAdopt = true;
  session.signIn("t");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === "/api/v1/system/status") return json({ role: "reception", hotel_id: "h1", can_adopt: canAdopt });
      if (path === "/api/v1/auth/me") return json({ id: "u", username: "manager", display_name: "المدير", role: "manager" });
      if (path === "/api/v1/backup/runs") return json({ results: [] });
      if (path === "/api/v1/backup/drive/status") return json({ configured: false, linked: false });
      return new Response(JSON.stringify({ code: "not_found" }), { status: 404, headers: { "Content-Type": "application/json" } });
    }),
  );
});

afterEach(() => {
  session.signOut();
  vi.unstubAllGlobals();
});

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BackupCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("a reception PC with no hotel records lets a manager open a backup (decision 230)", async () => {
  renderCard();
  await screen.findByText("لا توجد بيانات فندق على هذا الجهاز بعد: افتح بيانات فندقك من نسخة احتياطية");
  expect(screen.getByRole("button", { name: "استيراد نسخة" })).toBeEnabled();
});

test("a reception PC with data offers a confirmed restore instead (decision 231)", async () => {
  canAdopt = false;
  renderCard();
  await screen.findByText("يستبدل بيانات هذا الجهاز بنسخة احتياطية؛ تُحفظ البيانات الحالية جانبًا");
  fireEvent.click(screen.getByRole("button", { name: "استيراد نسخة" }));
  await screen.findByText("استعادة هذا الجهاز من نسخة احتياطية");
  expect(screen.queryByText("3. كيف ستستخدم هذا الجهاز؟")).toBeNull(); // a restore is always «للعمل عليه»
  const restore = screen.getByRole("button", { name: "استعادة الجهاز" });
  expect(restore).toBeDisabled();
  fireEvent.click(screen.getByLabelText("أفهم أن بيانات هذا الجهاز الحالية ستُستبدل بالنسخة"));
  expect(restore).toBeDisabled(); // still needs the file and the login
});
