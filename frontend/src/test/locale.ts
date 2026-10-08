// Run `fn` with the interface in `locale`, then put French back (the suite's default).
import type { Locale } from "@/lib/locale";
import { setLocale } from "@/paraglide/runtime";

export async function withLocale<T>(locale: Locale, fn: () => T | Promise<T>): Promise<T> {
  if (typeof document !== "undefined") document.documentElement.lang = locale;
  setLocale(locale, { reload: false });
  try {
    return await fn();
  } finally {
    if (typeof document !== "undefined") document.documentElement.lang = "fr";
    setLocale("fr", { reload: false });
  }
}
