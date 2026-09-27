import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { NewPcCard } from "./AdoptModal";

let canAdopt = true;
const sent: Record<string, string>[] = [];
// jsdom cannot read a multipart body back from a Request: record the fields as the dialog adds them.
let appended: Record<string, string> = {};

beforeEach(() => {
  canAdopt = true;
  sent.length = 0;
  appended = {};
  const append = FormData.prototype.append;
  vi.spyOn(FormData.prototype, "append").mockImplementation(function (this: FormData, ...args: unknown[]) {
    const [name, value] = args as [string, string | Blob];
    appended[name] = value instanceof File ? value.name : String(value);
    return (append as (...a: unknown[]) => void).apply(this, args); // same arity: a third undefined would be refused
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      if (url.pathname === "/api/v1/system/status") {
        return new Response(JSON.stringify({ role: "reception", hotel_id: "h1", can_adopt: canAdopt }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/v1/backup/adopt") {
        sent.push({ ...appended });
        return new Response(JSON.stringify({ mode: "view", restarting: true }), { status: 202, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ code: "not_found" }), { status: 404, headers: { "Content-Type": "application/json" } });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NewPcCard onSetup={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("a new PC offers to open the hotel from a backup: file, the owner's login, view only by default", async () => {
  renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "فتح من نسخة احتياطية" }));
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], "skytowers-5a7e0000-000003.age")] } });
  fireEvent.change(screen.getByLabelText("اسم المستخدم"), { target: { value: " manager " } });
  fireEvent.change(screen.getByLabelText("كلمة المرور"), { target: { value: "secret-1" } });
  expect(screen.getByRole("radio", { name: /للاطلاع فقط/ })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(screen.getByRole("button", { name: "فتح البيانات" }));
  await waitFor(() => expect(sent).toEqual([{ mode: "view", username: "manager", password: "secret-1", file: "skytowers-5a7e0000-000003.age" }]));
  expect(await screen.findByText("جارٍ فتح بيانات الفندق…")).toBeInTheDocument();
});

test("a PC that already holds a hotel shows nothing", async () => {
  canAdopt = false;
  const { container } = renderCard();
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});
