import { describe, expect, it } from "vitest";
import { extractLocaleFromRequestAsync } from "@/paraglide/runtime";
import { registerLocaleStrategies } from "../i18n";

registerLocaleStrategies();

const request = (acceptLanguage?: string) =>
  new Request("http://localhost/login", {
    headers: acceptLanguage === undefined ? {} : { "accept-language": acceptLanguage },
  });

describe("the server strategy", () => {
  it.each([
    ["en-GB", "en"],
    ["fr-BE,fr;q=0.9", "fr"],
    ["de,en;q=0.5", "en"],
    ["de-DE", "fr"],
    ["en; q=0.8, fr", "fr"],
  ])("Accept-Language %s gives %s", async (header, expected) => {
    expect(await extractLocaleFromRequestAsync(request(header))).toBe(expected);
  });

  it("answers French with no header", async () => {
    expect(await extractLocaleFromRequestAsync(request())).toBe("fr");
  });
});
