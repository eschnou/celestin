// @vitest-environment jsdom
/** Spec 015: what the usage page's address says, the span it asks for, and the requests it makes. */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CALLS_PAGE_SIZE,
  DEFAULT_SEARCH,
  parseUsageSearch,
  periodRange,
  searchParams,
  usageCallsQuery,
  usageDetailQuery,
  usageSummaryQuery,
  usageUsersQuery,
  USERS_PAGE_SIZE,
} from "../admin-usage";

afterEach(() => vi.unstubAllGlobals());

describe("the address", () => {
  it("is the defaults when it says nothing", () => {
    expect(parseUsageSearch({})).toEqual(DEFAULT_SEARCH);
    expect(DEFAULT_SEARCH.period).toBe("30d");
    expect(DEFAULT_SEARCH.view).toBe("users");
  });

  it("takes what it understands and drops the rest", () => {
    const search = parseUsageSearch({
      view: "calls",
      period: "7d",
      order: "cost",
      desc: false,
      page: "3",
      user: "u1",
      uname: "Léa",
      role: "authoring",
      feature: "dictation",
      status: "failed",
      model: "m1",
      correlation: "turn1",
      from: "2026-03-01",
      to: "2026-03-09",
    });
    expect(search).toMatchObject({
      view: "calls",
      period: "7d",
      order: "cost",
      desc: false,
      page: 3,
      user: "u1",
      role: "authoring",
      feature: "dictation",
      status: "failed",
      correlation: "turn1",
      from: "2026-03-01",
      to: "2026-03-09",
    });
  });

  it.each([
    [{ view: "everything" }, "view"],
    [{ period: "yesterday" }, "period"],
    [{ order: "email" }, "order"],
    [{ role: "root" }, "role"],
    [{ feature: "x" }, "feature"],
    [{ status: "weird" }, "status"],
    [{ page: "-2" }, "page"],
    [{ page: "abc" }, "page"],
    [{ page: 1.5 }, "page"],
    [{ from: "yesterday" }, "from"],
    [{ from: "2026-13-45" }, "from"],
  ])("reads an unknown value (%j) as the default", (raw, key) => {
    expect(parseUsageSearch(raw as Record<string, unknown>)[key as "view"]).toBe(
      DEFAULT_SEARCH[key as "view"],
    );
  });

  it("bounds the text it keeps", () => {
    const search = parseUsageSearch({
      q: "x".repeat(300),
      model: "m".repeat(500),
      correlation: "c".repeat(99),
    });
    expect([search.q.length, search.model.length, search.correlation.length]).toEqual([
      100, 200, 32,
    ]);
    expect(parseUsageSearch({ q: 5, user: {} }).q).toBe("");
  });

  it("keeps only what differs from the defaults, and reads back the same", () => {
    const search = { ...DEFAULT_SEARCH, view: "calls" as const, user: "u1", page: 2 };
    expect(searchParams(search)).toEqual({ view: "calls", user: "u1", page: 2 });
    expect(parseUsageSearch(searchParams(search) as Record<string, unknown>)).toEqual(search);
    expect(searchParams(DEFAULT_SEARCH)).toEqual({});
  });
});

describe("the span of a period", () => {
  // A Wednesday afternoon, local time.
  const now = new Date(2026, 2, 11, 15, 30, 0);

  it("today starts at local midnight and has no end", () => {
    expect(periodRange("today", "", "", now)).toEqual({
      since: new Date(2026, 2, 11).toISOString(),
    });
  });

  it("the rolling periods count back from now", () => {
    expect(periodRange("7d", "", "", now).since).toBe(
      new Date(now.getTime() - 7 * 86_400_000).toISOString(),
    );
    expect(periodRange("30d", "", "", now).since).toBe(
      new Date(now.getTime() - 30 * 86_400_000).toISOString(),
    );
    expect(periodRange("7d", "", "", now).until).toBeUndefined();
  });

  it("all time has no ends", () => {
    expect(periodRange("all", "2026-01-01", "2026-02-01", now)).toEqual({});
  });

  it("a custom range includes both of its days, in local time", () => {
    expect(periodRange("custom", "2026-03-01", "2026-03-09", now)).toEqual({
      since: new Date(2026, 2, 1).toISOString(),
      until: new Date(2026, 2, 10).toISOString(),
    });
  });

  it("a custom range may be open at one end", () => {
    expect(periodRange("custom", "2026-03-01", "", now)).toEqual({
      since: new Date(2026, 2, 1).toISOString(),
    });
    expect(periodRange("custom", "", "2026-03-09", now)).toEqual({
      until: new Date(2026, 2, 10).toISOString(),
    });
    expect(periodRange("custom", "", "", now)).toEqual({});
  });

  it("a custom range that ends before it starts is not sent as an empty one", () => {
    const range = periodRange("custom", "2026-03-09", "2026-03-01", now);
    expect(range.since).toBeDefined();
    expect(range.until).toBeUndefined();
  });
});

describe("the requests", () => {
  function stubFetch() {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(String(url));
        return { ok: true, status: 200, json: async () => ({}) };
      }),
    );
    return urls;
  }
  const run = (options: { queryFn?: unknown }) => (options.queryFn as () => Promise<unknown>)();
  const range = { since: "2026-03-01T00:00:00.000Z", until: "2026-03-09T00:00:00.000Z" };

  it("the summary asks for the span", async () => {
    const urls = stubFetch();
    await run(usageSummaryQuery(range));
    await run(usageSummaryQuery({}));
    expect(urls[0]).toBe(
      "/api/admin/usage/summary?since=2026-03-01T00%3A00%3A00.000Z&until=2026-03-09T00%3A00%3A00.000Z",
    );
    expect(urls[1]).toBe("/api/admin/usage/summary");
  });

  it("the users ask for a sort, a search and a page", async () => {
    const urls = stubFetch();
    await run(usageUsersQuery({}, { q: " élo ", order: "cost", desc: false, page: 2 }));
    const query = new URL(urls[0]!, "http://x").searchParams;
    expect(query.get("q")).toBe("élo");
    expect([query.get("order"), query.get("direction")]).toEqual(["cost", "asc"]);
    expect([query.get("limit"), query.get("offset")]).toEqual([
      String(USERS_PAGE_SIZE),
      String(2 * USERS_PAGE_SIZE),
    ]);
  });

  it("an empty search is not sent", async () => {
    const urls = stubFetch();
    await run(usageUsersQuery({}, { q: "  ", order: "calls", desc: true, page: 0 }));
    expect(new URL(urls[0]!, "http://x").searchParams.has("q")).toBe(false);
  });

  it("the detail names the user, escaped", async () => {
    const urls = stubFetch();
    await run(usageDetailQuery("a/b", {}));
    expect(urls[0]).toBe("/api/admin/usage/users/a%2Fb");
  });

  it("the calls send only the filters that are set", async () => {
    const urls = stubFetch();
    await run(
      usageCallsQuery(range, {
        user: "u1",
        role: "",
        feature: "dictation",
        model: "",
        status: "failed",
        correlation: "t1",
        page: 1,
      }),
    );
    const query = new URL(urls[0]!, "http://x").searchParams;
    expect(Object.fromEntries(query)).toEqual({
      since: range.since,
      until: range.until,
      user_id: "u1",
      feature: "dictation",
      status: "failed",
      correlation_id: "t1",
      limit: String(CALLS_PAGE_SIZE),
      offset: String(CALLS_PAGE_SIZE),
    });
  });

  it("each filter has its own cache key", () => {
    const a = usageCallsQuery({}, { ...DEFAULT_SEARCH });
    const b = usageCallsQuery({}, { ...DEFAULT_SEARCH, status: "failed" });
    expect(a.queryKey).not.toEqual(b.queryKey);
    expect(usageSummaryQuery({}).queryKey).not.toEqual(usageSummaryQuery(range).queryKey);
  });
});
