/** The interface languages (spec 010). Pure on purpose: the error page, the server
 *  strategy and the tests use it without loading the generated Paraglide runtime.
 *  Its twin is `backend/app/domain/locale.py`; `__tests__/accept_language_cases.json`
 *  is the case table both read. */

export const LOCALES = ["fr", "en", "nl"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "fr";

/** Each language in its own words: the settings list is not translated. */
export const AUTONYM: Record<Locale, string> = { fr: "Français", en: "English", nl: "Nederlands" };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** The first supported language of an `Accept-Language` header, by quality order
 *  and then by position, matched on the primary subtag (`fr-BE` is `fr`). An
 *  unsupported or malformed entry is skipped, never an error; no match is French. */
export function parseAcceptLanguage(header: string | null | undefined): Locale {
  if (!header) return DEFAULT_LOCALE;
  const ranked: { locale: Locale; q: number; position: number }[] = [];
  header.split(",").forEach((entry, position) => {
    const [rawTag = "", ...params] = entry.split(";");
    const tag = rawTag.trim().toLowerCase();
    if (!tag || tag === "*") return;
    let q = 1;
    for (const param of params) {
      const [key = "", value = ""] = param.split("=");
      if (key.trim().toLowerCase() !== "q") continue;
      const text = value.trim();
      const parsed = /^\d+(\.\d+)?$/.test(text) ? Number(text) : Number.NaN;
      if (Number.isNaN(parsed) || parsed > 1) return;
      q = parsed;
    }
    if (q === 0) return;
    const primary = tag.split("-")[0];
    if (isLocale(primary)) ranked.push({ locale: primary, q, position });
  });
  ranked.sort((a, b) => b.q - a.q || a.position - b.position);
  return ranked[0]?.locale ?? DEFAULT_LOCALE;
}

/** The same rule over `navigator.languages`, which is already in preference order. */
export function matchLocale(tags: readonly string[]): Locale {
  return parseAcceptLanguage(tags.join(","));
}
