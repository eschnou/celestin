// @vitest-environment jsdom
/** A session that dies while a lesson is open must not change the language under it: that
 *  would remount the tree and lose the transcript (spec 010 §5.2). The language goes back to
 *  the browser's when the redirect to sign-in happens (`requireUser`). */
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRouter } from "@/router";
import { USER } from "@/test/route-harness";
import { meQuery, type User } from "../auth";
import { getJson } from "../tutor/client";

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.lang = "fr";
});

describe("the unauthorized handler", () => {
  it("drops the cached user and leaves the language where it is", async () => {
    Object.defineProperty(window.navigator, "languages", {
      value: ["fr-BE", "fr"],
      configurable: true,
    });
    const router = getRouter();
    const { queryClient } = router.options.context as {
      queryClient: import("@tanstack/react-query").QueryClient;
    };
    const account: User = { ...USER, locale: "en" };
    queryClient.setQueryData(meQuery.queryKey, account);
    expect(document.documentElement.lang).toBe("en");

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 401,
        json: async () => ({ code: "not_authenticated", message: "Sign in to continue." }),
      })),
    );
    await getJson("/api/anything").catch(() => undefined);

    expect(queryClient.getQueryData(meQuery.queryKey)).toBeNull();
    // The browser says French, the dead account said English: nothing moved.
    expect(document.documentElement.lang).toBe("en");
  });
});
