/** The two guards of eslint.config.js (spec 010 §5.7), pinned: what they flag and what they let by. */
import tseslint from "typescript-eslint";
import { Linter } from "eslint";
import { describe, expect, it } from "vitest";
import { FRENCH_ALLOWED, i18nPlugin, noFrenchLiteral } from "../../../eslint-rules/i18n.js";

const linter = new Linter();

function lint(code: string, filename: string, rules: Record<string, unknown>) {
  return linter.verify(
    code,
    [
      {
        files: ["**/*.{ts,tsx}"],
        languageOptions: {
          parser: tseslint.parser,
          parserOptions: { ecmaFeatures: { jsx: true } },
        },
        plugins: { i18n: i18nPlugin },
        rules,
      },
    ] as never,
    { filename },
  );
}

const french = { "no-restricted-syntax": ["error", ...noFrenchLiteral] };
const moduleScope = { "i18n/no-module-scope-message": "error" };

describe("no French literal in interface code", () => {
  it("flags a string, a template and JSX text", () => {
    expect(lint(`const a = "Les élèves";`, "src/x.ts", french)).toHaveLength(1);
    expect(lint("const a = `Chapitre ${n} : élève`;", "src/x.ts", french)).toHaveLength(1);
    expect(lint(`const a = <p>Réessayer</p>;`, "src/x.tsx", french)).toHaveLength(1);
    expect(lint(`const a = <p title="Retour à l'accueil" />;`, "src/x.tsx", french)).toHaveLength(
      1,
    );
    expect(lint(`const a = "« guillemets »";`, "src/x.ts", french)).toHaveLength(1);
  });

  it("lets English, code and the catalog through", () => {
    expect(
      lint(`const a = "pending"; const b = <p>{m.nav_settings()}</p>;`, "src/x.tsx", french),
    ).toEqual([]);
    expect(lint(`// un commentaire en français\nconst a = 1;`, "src/x.ts", french)).toEqual([]);
  });

  it("cannot see unaccented French: that is what the English sweep test is for", () => {
    expect(lint(`const a = "Mes cours";`, "src/x.ts", french)).toEqual([]);
  });

  it("names the files whose French is not interface text", () => {
    expect(FRENCH_ALLOWED).toEqual([
      "src/lib/tutor/prompts.ts",
      "src/lib/locale.ts",
      "src/lib/brand.ts",
      "src/lib/error-page.ts",
      "src/components/celestin/charts/format.ts",
    ]);
  });
});

describe("no message call at module scope", () => {
  it("flags a call made when the module loads", () => {
    expect(lint(`const TITLE = m.meta_title();`, "src/x.ts", moduleScope)).toHaveLength(1);
    expect(lint(`export const A = [m.a(), m.b()];`, "src/x.ts", moduleScope)).toHaveLength(2);
    expect(lint(`class K { static t = m.a(); }`, "src/x.ts", moduleScope)).toHaveLength(1);
  });

  it("lets calls inside any function through, and tables of message functions", () => {
    expect(lint(`function f() { return m.a(); }`, "src/x.ts", moduleScope)).toEqual([]);
    expect(lint(`const f = () => m.a();`, "src/x.ts", moduleScope)).toEqual([]);
    expect(
      lint(`const T = { done: m.state_done, active: m.state_active };`, "src/x.ts", moduleScope),
    ).toEqual([]);
    expect(lint(`const T = { done: () => m.state_done() };`, "src/x.ts", moduleScope)).toEqual([]);
    expect(lint(`class K { t() { return m.a(); } }`, "src/x.ts", moduleScope)).toEqual([]);
  });

  it("leaves other objects called m alone only when they are not member calls on m", () => {
    expect(lint(`const x = other.a();`, "src/x.ts", moduleScope)).toEqual([]);
  });
});
