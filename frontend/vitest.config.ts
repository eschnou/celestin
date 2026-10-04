import { defineConfig } from "vitest/config";

// Standalone from vite.config.ts on purpose: the app config registers TanStack Start and
// the deploy server, a full SSR/nitro pipeline the unit tests do not need. Paraglide's output
// (src/paraglide) must exist: `npm test` generates it first (`pretest`).
export default defineConfig({
  resolve: { tsconfigPaths: true },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["src/test/setup.ts"],
  },
});
