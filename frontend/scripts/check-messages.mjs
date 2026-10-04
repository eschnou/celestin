// Paraglide silently falls back to the base locale for a key missing from another
// locale: the compile succeeds and tsc is green. This is the missing gate (spec 010
// R3.7): every locale must have exactly the base locale's keys and the same
// {variables}. Usage: node scripts/check-messages.mjs [messagesDir] [settingsFile]
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

const dir = resolve(process.argv[2] ?? new URL("../messages", import.meta.url).pathname);
const settingsFile = resolve(
  process.argv[3] ?? new URL("../project.inlang/settings.json", import.meta.url).pathname,
);
const settings = JSON.parse(readFileSync(settingsFile, "utf8"));

const load = (locale) => JSON.parse(readFileSync(resolve(dir, `${locale}.json`), "utf8"));
const variables = (value) =>
  [...new Set(JSON.stringify(value).match(/\{(\w+)\}/g) ?? [])].sort().join(",");
const keys = (messages) => Object.keys(messages).filter((key) => key !== "$schema");

const base = load(settings.baseLocale);
let problems = 0;
const report = (text) => {
  problems += 1;
  console.error(text);
};

for (const locale of settings.locales.filter((candidate) => candidate !== settings.baseLocale)) {
  const other = load(locale);
  for (const key of keys(base)) {
    if (!(key in other)) report(`${locale}: missing "${key}"`);
    else if (variables(base[key]) !== variables(other[key]))
      report(
        `${locale}: "${key}" variables differ (${variables(base[key])} vs ${variables(other[key])})`,
      );
  }
  for (const key of keys(other)) if (!(key in base)) report(`${locale}: extra "${key}"`);
}
for (const file of readdirSync(dir).filter((name) => name.endsWith(".json"))) {
  if (!settings.locales.includes(file.replace(".json", ""))) report(`unknown locale file ${file}`);
}

if (problems) process.exit(1);
console.log(`messages ok (${settings.locales.join(", ")})`);
