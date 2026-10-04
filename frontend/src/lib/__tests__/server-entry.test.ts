import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { extractLocaleFromRequestAsync } from "@/paraglide/runtime";
import { registerLocaleStrategies } from "../i18n";

const SERVER = readFileSync(new URL("../../server.ts", import.meta.url), "utf8");

describe("the server entry", () => {
  it("registers the language strategies by name, before any request", () => {
    // `sideEffects: false` lets the bundler drop `import "./lib/i18n"`; the first visitor of a
    // fresh server would then get French whatever their browser says (seen on the built server).
    expect(SERVER).not.toMatch(/^import\s+["']\.\/lib\/i18n["']/m);
    expect(SERVER).toMatch(/import \{[^}]*registerLocaleStrategies[^}]*\} from "\.\/lib\/i18n"/);
    expect(SERVER).toMatch(/^registerLocaleStrategies\(\);/m);
    expect(SERVER.indexOf("registerLocaleStrategies();")).toBeLessThan(
      SERVER.indexOf("export default"),
    );
  });

  it("can be asked twice without defining the strategies twice", async () => {
    registerLocaleStrategies();
    registerLocaleStrategies();
    const request = new Request("http://localhost/login", {
      headers: { "accept-language": "en-GB" },
    });
    expect(await extractLocaleFromRequestAsync(request)).toBe("en");
  });
});
