import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { session } from "@/api/session";

import { FollowupsPage } from "./FollowupsPage";

const row = (over: object) => ({
  id: "t1", stay: "s1", room: "207", room_state: "overdue", guest: "حسن آدم إسحق", kind: "يومي", last_night: "2026-09-25",
  when: "متجاوزة منذ يوم", rule: "قاعدة: يومي – يوم النهاية · 09:00", trigger_kind: "stay_ending", title: "", status: "open",
  due_at: "2026-09-25T07:00:00Z", snooze_count: 2, max_snoozes: 3, snooze_label: "تأجيل (2 من 3)", can_snooze: true, next_at: null,
  note: "", neglected_shift_user: null, version: 4, ...over,
});
const BOARD = {
  counts: { late: 2, today: 1, upcoming: 0, system: 0 },
  late: [row({}), row({ id: "t2", room: "305", guest: "عبدالله حسن موسى", status: "neglected", neglected_shift_user: "أحمد علي", can_snooze: false, snooze_label: "تأجيل (3 من 3)" })],
  today: [row({ id: "t3", room: "203", room_state: "occupied", guest: "محمد عثمان الطيب", kind: "شهري", when: "تنتهي بعد 3 أيام", status: "waiting", next_at: "2026-09-26T15:00:00Z", note: "قال سيؤكد التمديد" })],
  upcoming: [],
  system: [],
  last_action: null,
};
const posts: unknown[] = [];

beforeEach(() => {
  session.signIn("tok");
  posts.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (input.method === "POST") posts.push({ path, body: await input.json() });
      const body = path === "/api/v1/followups/board" ? BOARD : { role: "reception" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.signOut();
});

test("groups, neglected and waiting badges, snooze limit, snooze action", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <FollowupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("مُهمَلة — وردية: أحمد")).toBeInTheDocument();
  expect(screen.getByText(/بانتظار الرد · المتابعة/)).toBeInTheDocument();
  expect(screen.getByText(/«قال سيؤكد التمديد»/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "تأجيل (3 من 3)" })).toBeDisabled();

  fireEvent.click(screen.getAllByRole("button", { name: "تأجيل (2 من 3)" })[0]);
  expect(screen.getByText("تأجيل إلى — التأجيل 3 من 3")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /بعد ساعة/ }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0]).toMatchObject({ path: "/api/v1/followups/tasks/t1/actions", body: { action: "snooze", version: 4 } });
});
