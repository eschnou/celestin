import { paraglideVitePlugin } from "@inlang/paraglide-js";
import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { nitro } from "nitro/vite";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  plugins: [
    tailwindcss(),
    tanstackStart({
      // The browser bundle may not import server code.
      importProtection: {
        behavior: "error",
        client: { files: ["**/server/**"], specifiers: ["server-only"] },
      },
      // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR wrapper:
      // the language of the request, the failed-render page). nitro builds from this.
      server: { entry: "server" },
    }),
    // The deployable server, at build time only. AWS Amplify Hosting runs a Node.js compute
    // function from `.amplify-hosting/`; the Docker image builds with NITRO_PRESET=node-server
    // (a standalone server in `.output/`, static files included).
    ...(command === "build"
      ? [nitro({ preset: process.env["NITRO_PRESET"] ?? "aws_amplify" })]
      : []),
    viteReact(),
    paraglideVitePlugin({
      project: "./project.inlang",
      outdir: "./src/paraglide",
      // .d.ts next to the generated JS: tsc (no allowJs) needs them.
      emitTsDeclarations: true,
      // No locale in the URL and no cookie. "custom-account" and "custom-header" are
      // defined in src/lib/i18n.ts: the signed-in user's language on the client, the
      // request's Accept-Language on the server, then French.
      strategy: ["custom-account", "custom-header", "baseLocale"],
    }),
  ],
  css: { transformer: "lightningcss" },
  resolve: {
    // The `@/…` paths of tsconfig.json.
    tsconfigPaths: true,
    // One copy of each, whatever a dependency brings.
    dedupe: [
      "react",
      "react-dom",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "@tanstack/react-query",
      "@tanstack/query-core",
    ],
  },
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "react-dom/client",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
    ],
    ignoreOutdatedRequests: true,
  },
  server: {
    host: "::",
    port: 8080,
    // The Python backend runs on :8000 (BACKEND_URL to override). Proxying keeps the
    // browser on one origin, so CORS never enters the picture in development and the
    // session cookie is first-party.
    proxy: {
      "/api": {
        target: process.env["BACKEND_URL"] ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
}));
