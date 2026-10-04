// Global test setup. Pins the interface language to French the way the app resolves it
// on a client: through the custom strategy of src/lib/i18n.ts, which reads <html lang>.
// Without a document (node environment) Paraglide falls back to the base locale, fr.
import { afterEach } from "vitest";
import { unbindLocale } from "@/lib/i18n";

if (typeof document !== "undefined") document.documentElement.lang = "fr";

// A test that switches the language must not leave it switched for the next one.
afterEach(() => {
  unbindLocale();
  if (typeof document !== "undefined") document.documentElement.lang = "fr";
});
