/** Numbers and sizes the interface writes, in the interface language (spec 010 R3.5).
 *
 *  Not for the board: what a chart, a figure or a plot draws follows the course's notation
 *  (`components/celestin/charts/format.ts`, always fr-BE), whatever language the interface is in. */

import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import type { Locale } from "./locale";

/** The Intl tag of each interface language. */
export const INTL_TAG: Record<Locale, string> = { fr: "fr-BE", en: "en-GB" };

const tag = (): string => INTL_TAG[getLocale()];

/** A whole number with the interface language's digit grouping: « 12 000 » / "12,000". */
export function formatCount(n: number): string {
  return n.toLocaleString(tag());
}

/** A size in megabytes, one decimal at most, with the unit word: « 1,5 Mo » / "1.5 MB". */
export function formatMegabytes(bytes: number): string {
  const value = (bytes / 1024 / 1024).toLocaleString(tag(), { maximumFractionDigits: 1 });
  return m.format_megabytes({ value });
}

/** A calendar date from an ISO timestamp, in the interface language: « 2 oct. 2026 » / "2 Oct 2026". */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(tag(), { dateStyle: "medium" });
}
