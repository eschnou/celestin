import { describe, expect, it } from "vitest";
import { languageHeaders } from "../html-headers";

const html = (init?: ResponseInit) =>
  new Response("<p>x</p>", { ...init, headers: { "content-type": "text/html; charset=utf-8" } });

describe("languageHeaders", () => {
  it("makes an HTML page vary on the language and private to the browser", () => {
    const response = languageHeaders(html());
    expect(response.headers.get("vary")).toContain("Accept-Language");
    expect(response.headers.get("cache-control")).toBe("private, no-cache");
  });

  it("keeps a Vary the page already had", () => {
    const response = languageHeaders(
      new Response("x", { headers: { "content-type": "text/html", vary: "Accept-Encoding" } }),
    );
    expect(response.headers.get("vary")).toBe("Accept-Encoding, Accept-Language");
  });

  it("leaves JSON and assets alone", () => {
    for (const type of ["application/json", "text/css", "image/png"]) {
      const response = languageHeaders(new Response("x", { headers: { "content-type": type } }));
      expect(response.headers.get("vary")).toBeNull();
      expect(response.headers.get("cache-control")).toBeNull();
    }
  });

  it("copes with immutable headers", async () => {
    // An HTML response whose headers refuse writes, as one that came from fetch does.
    const frozen = html();
    Object.defineProperty(frozen, "headers", {
      value: new Proxy(frozen.headers, {
        get(target, key) {
          if (key === "append" || key === "set") {
            return () => {
              throw new TypeError("immutable");
            };
          }
          const value = Reflect.get(target, key);
          return typeof value === "function" ? value.bind(target) : value;
        },
      }),
    });
    const response = languageHeaders(frozen);
    expect(response.headers.get("cache-control")).toBe("private, no-cache");
    expect(response.headers.get("vary")).toContain("Accept-Language");
    expect(await response.text()).toBe("<p>x</p>");
  });
});
