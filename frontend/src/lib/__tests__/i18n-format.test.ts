// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { formatCount, formatMegabytes, INTL_TAG } from "../i18n-format";
import { withLocale } from "@/test/locale";

describe("interface numbers", () => {
  it("names one Intl tag per interface language", () => {
    expect(INTL_TAG).toEqual({ fr: "fr-BE", en: "en-GB" });
  });

  it("groups digits the French way by default", () => {
    expect(formatCount(1234567)).toBe((1234567).toLocaleString("fr-BE"));
    expect(formatCount(1234567)).not.toContain(",");
  });

  it("groups digits the English way under en", () =>
    withLocale("en", () => {
      expect(formatCount(1234567)).toBe("1,234,567");
    }));

  it("writes a size with a decimal comma and « Mo » in French", () => {
    expect(formatMegabytes(1.5 * 1024 * 1024)).toBe("1,5 Mo");
    expect(formatMegabytes(25 * 1024 * 1024)).toBe("25 Mo");
    expect(formatMegabytes(0)).toBe("0 Mo");
  });

  it("writes a size with a decimal point and MB in English", () =>
    withLocale("en", () => {
      expect(formatMegabytes(1.5 * 1024 * 1024)).toBe("1.5 MB");
      expect(formatMegabytes(25 * 1024 * 1024)).toBe("25 MB");
    }));
});
