import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The SPA is served by Django from server/static_spa (spec §4); in development Vite proxies the API.
// SKYTOWERS_API points the proxy at another local server (e.g. a second checkout while the installed app holds 8471).
const api = process.env.SKYTOWERS_API ?? "http://127.0.0.1:8471";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@api": fileURLToPath(new URL("../api", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: { "/api": api },
  },
  preview: { port: 4173, proxy: { "/api": api } },
  build: { outDir: "dist", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
