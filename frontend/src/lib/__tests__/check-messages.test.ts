import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const SCRIPT = join(process.cwd(), "scripts", "check-messages.mjs");
const dirs: string[] = [];

function check(files: Record<string, unknown>) {
  const dir = mkdtempSync(join(tmpdir(), "messages-"));
  dirs.push(dir);
  for (const [name, content] of Object.entries(files)) {
    writeFileSync(join(dir, `${name}.json`), JSON.stringify(content));
  }
  const settingsDir = mkdtempSync(join(tmpdir(), "settings-"));
  dirs.push(settingsDir);
  const settings = join(settingsDir, "settings.json");
  writeFileSync(settings, JSON.stringify({ baseLocale: "fr", locales: ["fr", "en"] }));
  return spawnSync("node", [SCRIPT, dir, settings], { encoding: "utf8" });
}

afterEach(() => {
  while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true });
});

describe("check-messages", () => {
  it("accepts two catalogs with the same keys and variables", () => {
    const result = check({
      fr: { a: "Salut {name}", b: "Oui" },
      en: { a: "Hi {name}", b: "Yes" },
    });
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("messages ok");
  });

  it("fails on a key missing from English", () => {
    const result = check({ fr: { a: "Oui", b: "Non" }, en: { a: "Yes" } });
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('en: missing "b"');
  });

  it("fails on an extra English key", () => {
    const result = check({ fr: { a: "Oui" }, en: { a: "Yes", z: "Extra" } });
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('en: extra "z"');
  });

  it("fails when the variables differ", () => {
    const result = check({ fr: { a: "Salut {name}" }, en: { a: "Hi {who}" } });
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('"a" variables differ');
  });

  it("fails on a locale file nobody declared", () => {
    const result = check({ fr: { a: "Oui" }, en: { a: "Yes" }, de: { a: "Ja" } });
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("unknown locale file de.json");
  });
});
