// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  formatCost,
  formatCount,
  formatDateTime,
  formatDurationMs,
  formatMegabytes,
  INTL_TAG,
} from "../i18n-format";
import { withLocale } from "@/test/locale";

describe("interface numbers", () => {
  it("names one Intl tag per interface language", () => {
    expect(INTL_TAG).toEqual({ fr: "fr-BE", en: "en-GB", nl: "nl-BE" });
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

describe("interface numbers in Dutch (spec 017)", () => {
  it("groups digits with a dot and writes a decimal comma, with MB", () =>
    withLocale("nl", () => {
      expect(formatCount(1234567)).toBe("1.234.567");
      expect(formatMegabytes(1.5 * 1024 * 1024)).toBe("1,5 MB");
      expect(formatMegabytes(25 * 1024 * 1024)).toBe("25 MB");
      expect(formatCost(0.0123).replace(/\s/g, " ")).toBe("US$ 0,0123");
    }));
});

describe("what the usage screen writes (spec 015)", () => {
  it("writes a cost in dollars with four decimals, in French", () => {
    expect(formatCost(0.0123)).toBe(
      (0.0123).toLocaleString("fr-BE", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 4,
        maximumFractionDigits: 4,
      }),
    );
    expect(formatCost(0.0123)).toContain("0,0123");
    expect(formatCost(1234.5)).toContain("234,5000");
  });

  it("writes a cost with a decimal point in English", () =>
    withLocale("en", () => {
      expect(formatCost(0.0123)).toBe("US$0.0123");
      expect(formatCost(1234.5)).toBe("US$1,234.5000");
    }));

  it("writes a zero cost as a cost, because the provider said it", () => {
    expect(formatCost(0)).toContain("0,0000");
  });

  it("writes a duration as short as it reads", () => {
    expect(formatDurationMs(420)).toBe("420 ms");
    expect(formatDurationMs(0)).toBe("0 ms");
    expect(formatDurationMs(1200)).toBe("1,2 s");
    expect(formatDurationMs(59_000)).toBe("59 s");
    expect(formatDurationMs(125_000)).toBe("2 min 5 s");
    expect(formatDurationMs(119_600)).toBe("2 min 0 s"); // not « 1 min 60 s »
    expect(formatDurationMs(59_600)).toBe("59,6 s");
  });

  it("writes a duration with a decimal point in English", () =>
    withLocale("en", () => {
      expect(formatDurationMs(1200)).toBe("1.2 s");
    }));

  it("writes a date and a time in the interface language", () => {
    const iso = "2026-10-02T14:03:07Z";
    expect(formatDateTime(iso)).toBe(
      new Date(iso).toLocaleString("fr-BE", { dateStyle: "medium", timeStyle: "medium" }),
    );
    return withLocale("en", () => {
      expect(formatDateTime(iso)).toBe(
        new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "medium" }),
      );
    });
  });
});
