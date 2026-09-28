import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";
import { playAlert, setSoundMuted, soundMuted } from "@/lib/alertSound";

import { Toasts } from "./Toasts";

vi.mock("@/lib/alertSound", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/alertSound")>()),
  playAlert: vi.fn(async () => undefined),
}));

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  session.signIn("tok");
  vi.mocked(playAlert).mockClear();
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("a batch of alerts plays the owner's sound once; the first answer (old alerts) plays nothing", async () => {
  let call = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === "/api/v1/system/settings") return json({ alert_sound: { name: "bell.mp3", updated_at: "2026-09-28T10:00:00Z" } });
      call += 1;
      if (call === 1) return json({ cursor: 5, toasts: [] }); // opening the app: only the cursor
      return json({
        cursor: 7,
        toasts: [
          { seq: 6, title: "تنتهي غدًا — 203", body: "", level: "info" },
          { seq: 7, title: "تنتهي اليوم — 305", body: "", level: "info" },
        ],
      });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Toasts />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await vi.waitFor(() => expect(call).toBe(1));
  await client.refetchQueries({ queryKey: ["system", "settings"] });
  await client.refetchQueries({ queryKey: ["followups", "toasts"] });
  expect(await screen.findByText("تنتهي اليوم — 305")).toBeInTheDocument();
  expect(playAlert).toHaveBeenCalledTimes(1);
  expect(playAlert).toHaveBeenCalledWith("2026-09-28T10:00:00Z");
});

test("each PC may switch the sound off for itself", () => {
  setSoundMuted(true);
  expect(soundMuted()).toBe(true);
  setSoundMuted(false);
  expect(soundMuted()).toBe(false);
});
