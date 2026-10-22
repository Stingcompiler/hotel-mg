import { holdLightTheme, initTheme, resolvedTheme, setThemePref } from "./theme";

let systemDark = false;
const listeners: (() => void)[] = [];

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return query.includes("dark") && systemDark;
    },
    addEventListener: (_: string, fn: () => void) => listeners.push(fn),
  }));
  initTheme();
});

afterEach(() => {
  systemDark = false;
  setThemePref("system");
});

const htmlTheme = () => document.documentElement.dataset.theme;

test("a chosen theme is applied to <html> and remembered on this PC", () => {
  setThemePref("dark");
  expect(htmlTheme()).toBe("dark");
  expect(window.localStorage.getItem("skytowers.theme")).toBe("dark");
  setThemePref("light");
  expect(htmlTheme()).toBe("light");
});

test("«تلقائي» follows Windows, also when Windows switches while the app is open", () => {
  setThemePref("system");
  expect(window.localStorage.getItem("skytowers.theme")).toBeNull();
  expect(htmlTheme()).toBe("light");
  systemDark = true;
  listeners.forEach((fn) => fn());
  expect(htmlTheme()).toBe("dark");
});

test("print pages hold the light theme while open, then the screen theme comes back", () => {
  setThemePref("dark");
  const release = holdLightTheme();
  expect(resolvedTheme()).toBe("light");
  expect(htmlTheme()).toBe("light");
  release();
  expect(htmlTheme()).toBe("dark");
});
