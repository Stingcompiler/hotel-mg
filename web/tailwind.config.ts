import type { Config } from "tailwindcss";

import preset from "./tailwind.preset";

// Colours, type roles, radii and sizes come only from the design tokens (spec §10.2).
export default {
  presets: [preset as Config],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // Tailwind's own palette is removed: only token colours exist (the preset adds them under `extend`).
  theme: { colors: { transparent: "transparent", current: "currentColor", inherit: "inherit" } },
  corePlugins: { float: false, clear: false },
} satisfies Config;
