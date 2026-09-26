import "@testing-library/jest-dom/vitest";

// jsdom has no matchMedia; the shells ask for the narrow (1366) layout.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList;
}
