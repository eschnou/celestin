import js from "@eslint/js";
import eslintPluginPrettier from "eslint-plugin-prettier/recommended";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import { FRENCH_ALLOWED, i18nPlugin, noFrenchLiteral } from "./eslint-rules/i18n.js";

// Not interface text: the generated catalog code, the stock shadcn parts, and the tests, which
// assert the French and the English they render.
const NOT_INTERFACE = [
  "src/components/ui/**",
  "src/paraglide/**",
  "src/test/**",
  "src/**/__tests__/**",
  "src/**/*.test.{ts,tsx}",
];

export default tseslint.config(
  { ignores: ["dist", ".output", ".amplify-hosting", ".vinxi", "src/paraglide"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "server-only",
              message:
                "TanStack Start does not use the Next.js `server-only` package. Rename the module to `*.server.ts` or mark it with `@tanstack/react-start/server-only`.",
            },
          ],
        },
      ],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
  {
    // Interface text goes through the catalog (spec 010 §5.7).
    files: ["src/**/*.{ts,tsx}"],
    ignores: [...NOT_INTERFACE, ...FRENCH_ALLOWED],
    rules: { "no-restricted-syntax": ["error", ...noFrenchLiteral] },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: NOT_INTERFACE,
    plugins: { i18n: i18nPlugin },
    rules: { "i18n/no-module-scope-message": "error" },
  },
  eslintPluginPrettier,
);
