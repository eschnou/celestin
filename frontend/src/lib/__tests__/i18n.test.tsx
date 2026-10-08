// @vitest-environment jsdom
import { QueryClient } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { m } from "@/paraglide/messages";
import { getLocale, setLocale } from "@/paraglide/runtime";
import { bindLocaleToQueryClient, resetLocale, useLocale } from "../i18n";
import { ME_QUERY_KEY } from "../me-key";

function Title() {
  const locale = useLocale();
  return <p>{`${locale}: ${m.meta_title()}`}</p>;
}

let client: QueryClient;
let unbind: () => void;

beforeEach(() => {
  document.documentElement.lang = "fr";
  client = new QueryClient();
  unbind = bindLocaleToQueryClient(client);
});

afterEach(() => {
  cleanup();
  unbind();
  document.documentElement.lang = "fr";
});

describe("the client strategy", () => {
  it("reads the page's language when nobody is signed in", () => {
    document.documentElement.lang = "en";
    expect(getLocale()).toBe("en");
    document.documentElement.lang = "fr";
    expect(getLocale()).toBe("fr");
  });

  it("prefers the signed-in user's language over the page's", () => {
    document.documentElement.lang = "fr";
    client.setQueryData(ME_QUERY_KEY, { id: "u", locale: "en" });
    expect(getLocale()).toBe("en");
  });

  it("ignores a stored language it does not support", () => {
    client.setQueryData(ME_QUERY_KEY, { id: "u", locale: "de" });
    expect(getLocale()).toBe("fr");
  });
});

describe("useLocale", () => {
  it("re-renders the message functions when setLocale is called without a reload", () => {
    render(<Title />);
    expect(screen.getByText("fr: Célestin — le prof particulier")).toBeTruthy();

    act(() => setLocale("en", { reload: false }));
    expect(screen.getByText("en: Célestin — your private tutor")).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");

    act(() => setLocale("fr", { reload: false }));
    expect(screen.getByText("fr: Célestin — le prof particulier")).toBeTruthy();
  });

  it("follows the signed-in user's language as it lands in the cache", () => {
    render(<Title />);
    act(() => {
      client.setQueryData(ME_QUERY_KEY, { id: "u", locale: "en" });
    });
    expect(screen.getByText("en: Célestin — your private tutor")).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
  });

  it("writes the language into the cached user", () => {
    client.setQueryData(ME_QUERY_KEY, { id: "u", locale: "fr" });
    act(() => setLocale("en", { reload: false }));
    expect(client.getQueryData(ME_QUERY_KEY)).toEqual({ id: "u", locale: "en" });
  });
});

describe("resetLocale", () => {
  const languages = (list: string[]) =>
    Object.defineProperty(window.navigator, "languages", { value: list, configurable: true });

  it("returns to the browser's language after a sign-out", () => {
    languages(["en-GB", "fr-BE"]);
    render(<Title />);
    client.setQueryData(ME_QUERY_KEY, { id: "u", locale: "fr" });
    act(() => {
      client.setQueryData(ME_QUERY_KEY, null);
      resetLocale();
    });
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByText("en: Célestin — your private tutor")).toBeTruthy();
  });

  it("falls back to French when the browser offers nothing supported", () => {
    languages(["de-DE"]);
    document.documentElement.lang = "en";
    act(() => resetLocale());
    expect(document.documentElement.lang).toBe("fr");
  });

  it("follows a Flemish browser to Dutch (spec 017)", () => {
    languages(["nl-BE", "fr-BE"]);
    document.documentElement.lang = "fr";
    act(() => resetLocale());
    expect(document.documentElement.lang).toBe("nl");
  });
});
