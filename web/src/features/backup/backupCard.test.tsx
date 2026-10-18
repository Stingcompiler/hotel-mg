import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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

test("once the PC holds hotel records, import stays on the owner PC", async () => {
  canAdopt = false;
  renderCard();
  await waitFor(() => expect(screen.getByText("متاح على جهاز المالك، أو على جهاز استقبال لم تُسجَّل فيه بيانات فندق بعد")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "استيراد نسخة" })).toBeDisabled();
});
