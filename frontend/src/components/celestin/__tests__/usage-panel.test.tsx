// @vitest-environment jsdom
/** Spec 015 R6: the administrator's usage screen. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UsagePanel } from "@/components/celestin/admin/usage-panel";
import {
  DEFAULT_SEARCH,
  type UsageCall,
  type UsageSearch,
  type UsageSummary,
  type UserUsage,
} from "@/lib/admin-usage";
import { withLocale } from "@/test/locale";
import { mockApi } from "@/test/route-harness";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const totals = (over: Partial<UserUsage> = {}) => ({
  calls: 3,
  input_tokens: 1500,
  cached_tokens: 400,
  output_tokens: 200,
  reasoning_tokens: 50,
  cost_usd: null,
  costed_calls: 0,
  ...over,
});
const user = (over: Partial<UserUsage> = {}): UserUsage => ({
  user_id: "u1",
  name: "Ana",
  email: "ana@x.be",
  enabled: true,
  ...totals(),
  ...over,
});
const SUMMARY: UsageSummary = { totals: totals({ calls: 5 }), models: ["m1", "m2"] };
const call = (over: Partial<UsageCall> = {}): UsageCall => ({
  id: 1,
  created_at: "2026-03-01T12:00:00Z",
  user_id: "u1",
  user_name: "Ana",
  user_email: "ana@x.be",
  course_id: "c1",
  chapter_id: "ch1",
  course_subject: "mathematics",
  course_language: "fr",
  correlation_id: "turn1",
  role: "tutor",
  feature: "tutor_turn",
  model: "m1",
  provider: "api.test",
  status: "ok",
  error_code: null,
  latency_ms: 1200,
  ttft_ms: 300,
  input_tokens: 100,
  cached_tokens: 40,
  output_tokens: 10,
  reasoning_tokens: 2,
  input_audio_tokens: null,
  output_audio_tokens: null,
  audio_seconds: null,
  cost_usd: null,
  ...over,
});

type Handler = Parameters<typeof mockApi>[0];

/** The panel with the state the route keeps in the address, kept here in a hook. */
function Harness({ initial = DEFAULT_SEARCH }: { initial?: UsageSearch | undefined }) {
  const [search, setSearch] = useState(initial);
  return (
    <UsagePanel search={search} onChange={(patch) => setSearch((s) => ({ ...s, ...patch }))} />
  );
}

function mount(handler: Handler, initial?: UsageSearch) {
  const calls = mockApi(handler);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Harness initial={initial} />
    </QueryClientProvider>,
  );
  return calls;
}

const is = (path: string, prefix: string) => path.startsWith(`/api/admin/usage/${prefix}`);
const query = (path: string) => new URL(path, "http://x").searchParams;

const base =
  (
    over: {
      users?: UserUsage[];
      total?: number;
      summary?: UsageSummary;
      calls?: UsageCall[];
      more?: boolean;
    } = {},
  ): Handler =>
  (method, path) => {
    if (method !== "GET") return undefined;
    if (is(path, "summary")) return { body: over.summary ?? SUMMARY };
    if (is(path, "users?")) {
      const users = over.users ?? [user()];
      return { body: { users, total: over.total ?? users.length } };
    }
    if (is(path, "calls"))
      return { body: { calls: over.calls ?? [call()], has_more: over.more ?? false } };
    return undefined;
  };

describe("the summary", () => {
  it("shows the totals of the period and says how many calls reported a cost", async () => {
    mount(
      base({
        summary: { totals: totals({ calls: 5, cost_usd: 1.5, costed_calls: 2 }), models: [] },
      }),
    );
    expect(
      await screen.findByText("Appels avec un coût communiqué par le fournisseur : 2 sur 5."),
    ).toBeTruthy();
    expect(screen.getAllByText(/1,5000/).length).toBeGreaterThan(0);
  });

  it("says the provider reports no cost, and never writes a zero for it", async () => {
    mount(base());
    expect(await screen.findByText("Le fournisseur ne communique pas de coût.")).toBeTruthy();
    expect(screen.queryByText(/0,0000/)).toBeNull();
    const cost = screen.getByText("Coût communiqué").closest("div")!;
    expect(cost.textContent).toContain("—");
  });

  it("says nothing about cost when there are no calls", async () => {
    mount(
      base({ summary: { totals: totals({ calls: 0, input_tokens: 0 }), models: [] }, users: [] }),
    );
    await screen.findByText("Aucun appel sur cette période.");
    expect(screen.queryByText("Le fournisseur ne communique pas de coût.")).toBeNull();
  });

  it("is an error when it cannot be loaded", async () => {
    mount((method, path) =>
      is(path, "summary")
        ? { status: 500, body: { code: "x", message: "x" } }
        : base()(method, path, null),
    );
    expect((await screen.findAllByRole("alert"))[0]!.textContent).toContain(
      "Impossible de charger",
    );
  });
});

describe("the period", () => {
  it("is the last 30 days at first, and the requests say so", async () => {
    const calls = mount(base());
    await screen.findByText("Ana");
    const since = query(calls.find((c) => is(c.path, "summary"))!.path).get("since");
    expect(Date.now() - Date.parse(since!)).toBeGreaterThan(29 * 86_400_000);
    expect(Date.now() - Date.parse(since!)).toBeLessThan(31 * 86_400_000);
    expect(
      screen.getByRole("button", { name: "30 derniers jours" }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("all time sends no span", async () => {
    const calls = mount(base());
    await screen.findByText("Ana");
    fireEvent.click(screen.getByRole("button", { name: "Tout" }));
    await waitFor(() => {
      const last = [...calls].reverse().find((c) => is(c.path, "summary"))!;
      expect(query(last.path).has("since")).toBe(false);
    });
  });

  it("a custom range shows two dates and sends them", async () => {
    const calls = mount(base());
    await screen.findByText("Ana");
    fireEvent.click(screen.getByRole("button", { name: "Personnalisée" }));
    fireEvent.change(screen.getByLabelText("Du"), { target: { value: "2026-03-01" } });
    fireEvent.change(screen.getByLabelText("Au"), { target: { value: "2026-03-09" } });
    await waitFor(() => {
      const last = [...calls].reverse().find((c) => is(c.path, "summary"))!;
      expect(query(last.path).get("since")).toBe(new Date(2026, 2, 1).toISOString());
      expect(query(last.path).get("until")).toBe(new Date(2026, 2, 10).toISOString());
    });
  });
});

describe("per user", () => {
  it("lists the users with their totals and a dash for a cost nobody reported", async () => {
    mount(
      base({
        users: [
          user(),
          user({ user_id: "u2", name: "Élodie", email: "e@x.be", cost_usd: 0.5, costed_calls: 1 }),
        ],
      }),
    );
    const row = (await screen.findByText("Ana")).closest("tr")!;
    expect(within(row).getByText("—")).toBeTruthy();
    expect(within(row).getByText("0/3").getAttribute("title")).toBe("Non communiqué");
    const other = screen.getByText("Élodie").closest("tr")!;
    expect(within(other).getByText(/0,5000/)).toBeTruthy();
    expect(within(other).getByText("1/3").getAttribute("title")).toBe(
      "Appels avec un coût communiqué par le fournisseur : 1 sur 3.",
    );
  });

  it("marks a disabled account", async () => {
    mount(base({ users: [user({ enabled: false })] }));
    expect(await screen.findByText("(désactivé)")).toBeTruthy();
  });

  it("sorts: a click on a column sorts by it, a second click reverses it", async () => {
    const calls = mount(base());
    await screen.findByText("Ana");
    const last = () => query([...calls].reverse().find((c) => is(c.path, "users?"))!.path);
    expect([last().get("order"), last().get("direction")]).toEqual(["calls", "desc"]);
    fireEvent.click(screen.getByRole("button", { name: "Trier par Coût" }));
    await waitFor(() =>
      expect([last().get("order"), last().get("direction")]).toEqual(["cost", "desc"]),
    );
    fireEvent.click(screen.getByRole("button", { name: "Trier par Coût" }));
    await waitFor(() => expect(last().get("direction")).toBe("asc"));
    fireEvent.click(screen.getByRole("button", { name: "Trier par Utilisateur" }));
    await waitFor(() =>
      expect([last().get("order"), last().get("direction")]).toEqual(["name", "asc"]),
    );
  });

  it("waits for a pause in the typing before it searches", async () => {
    const calls = mount(base());
    await screen.findByText("Ana");
    const box = screen.getByLabelText("Rechercher par nom ou email");
    fireEvent.change(box, { target: { value: "é" } });
    fireEvent.change(box, { target: { value: "él" } });
    expect(calls.some((c) => query(c.path).get("q") === "él")).toBe(false);
    await waitFor(() => expect(calls.some((c) => query(c.path).get("q") === "él")).toBe(true), {
      timeout: 3000,
    });
    expect(calls.some((c) => query(c.path).get("q") === "é")).toBe(false);
  });

  it("pages when there are more users than a page", async () => {
    const calls = mount(base({ total: 60 }));
    await screen.findByText("1–25 sur 60");
    expect((screen.getByRole("button", { name: "Précédent" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Suivant" }));
    await screen.findByText("26–50 sur 60");
    expect(calls.some((c) => is(c.path, "users?") && query(c.path).get("offset") === "25")).toBe(
      true,
    );
  });

  it("opens a user's by-role and by-model totals", async () => {
    mount((method, path, body) =>
      is(path, "users/u1")
        ? {
            body: {
              user: {},
              totals: totals(),
              by_role: [{ role: "tutor", ...totals({ calls: 2 }) }],
              by_model: [
                {
                  model: "m1",
                  provider: "api.test",
                  ...totals({ calls: 2, cost_usd: 0.25, costed_calls: 1 }),
                },
              ],
            },
          }
        : base()(method, path, body),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Détail de Ana" }));
    expect(await screen.findByText("Par rôle")).toBeTruthy();
    expect(screen.getByText(/Tuteur/)).toBeTruthy();
    expect(screen.getByText(/m1/)).toBeTruthy();
    expect(screen.getByText(/0,2500/)).toBeTruthy();
  });

  it("shows the detail's failure in the row", async () => {
    mount((method, path, body) =>
      is(path, "users/u1")
        ? { status: 500, body: { code: "x", message: "x" } }
        : base()(method, path, body),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Détail de Ana" }));
    expect(
      (await screen.findAllByRole("alert")).some((a) => a.textContent?.includes("détail")),
    ).toBe(true);
  });

  it("goes to a user's calls", async () => {
    const calls = mount(base());
    fireEvent.click(await screen.findByRole("button", { name: "Voir les appels de Ana" }));
    expect(await screen.findByText("Utilisateur : Ana")).toBeTruthy();
    await waitFor(() =>
      expect(calls.some((c) => is(c.path, "calls") && query(c.path).get("user_id") === "u1")).toBe(
        true,
      ),
    );
    expect(screen.getByRole("button", { name: "Appels" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("says when nobody called a model, and when it cannot load", async () => {
    mount(base({ users: [] }));
    expect(await screen.findByText("Aucun appel sur cette période.")).toBeTruthy();
  });

  it("is an error when the users cannot be loaded", async () => {
    mount((method, path, body) =>
      is(path, "users?")
        ? { status: 500, body: { code: "x", message: "x" } }
        : base()(method, path, body),
    );
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
  });
});

describe("the calls", () => {
  const calls = (over: Partial<UsageSearch> = {}): UsageSearch => ({
    ...DEFAULT_SEARCH,
    view: "calls" as const,
    ...over,
  });

  it("lists each call with its model, tokens, times and status, and a dash for what was not reported", async () => {
    mount(
      base({
        calls: [
          call(),
          call({
            id: 2,
            status: "failed",
            error_code: "provider_timeout",
            input_tokens: null,
            cached_tokens: null,
            output_tokens: null,
            reasoning_tokens: null,
            latency_ms: null,
            ttft_ms: null,
            cost_usd: 0.0123,
            correlation_id: null,
            feature: "dictation",
            role: "voice",
            audio_seconds: 4.2,
          }),
        ],
      }),
      calls(),
    );
    const first = (await screen.findAllByText("Ana"))[0]!.closest("tr")!;
    expect(within(first).getByText("Tour de leçon")).toBeTruthy();
    expect(within(first).getByText("m1")).toBeTruthy();
    expect(within(first).getByText("1,2 s")).toBeTruthy();
    expect(within(first).getByText("Réussi")).toBeTruthy();
    expect(within(first).getByTitle("Non communiqué").textContent).toBe("—"); // the unreported cost
    const second = screen.getAllByText("Ana")[1]!.closest("tr")!;
    expect(within(second).getByText("Échec")).toBeTruthy();
    expect(within(second).getByText("provider_timeout")).toBeTruthy();
    expect(within(second).getByText(/0,0123/)).toBeTruthy();
    expect(within(second).getByText("4 s")).toBeTruthy();
    expect(within(second).getAllByText("—").length).toBeGreaterThan(4);
  });

  it("filters by status and sends it", async () => {
    const seen = mount(base(), calls());
    await screen.findByText("turn1");
    fireEvent.change(screen.getByLabelText("Statut"), { target: { value: "failed" } });
    await waitFor(() =>
      expect(
        seen.some((c) => is(c.path, "calls") && query(c.path).get("status") === "failed"),
      ).toBe(true),
    );
    fireEvent.click(screen.getByRole("button", { name: "Effacer les filtres" }));
    await waitFor(() => {
      const last = [...seen].reverse().find((c) => is(c.path, "calls"))!;
      expect(query(last.path).has("status")).toBe(false);
    });
  });

  it("offers the models of the period for the model filter", async () => {
    mount(base(), calls());
    await screen.findByText("turn1");
    const select = screen.getByLabelText("Modèle") as HTMLSelectElement;
    await waitFor(() =>
      expect(Array.from(select.options).map((o) => o.value)).toEqual(["", "m1", "m2"]),
    );
  });

  it("a click on a group id shows the calls of that turn, run or session", async () => {
    const seen = mount(base(), calls());
    fireEvent.click(await screen.findByRole("button", { name: "turn1" }));
    await waitFor(() =>
      expect(
        seen.some((c) => is(c.path, "calls") && query(c.path).get("correlation_id") === "turn1"),
      ).toBe(true),
    );
    expect((screen.getByLabelText("Identifiant de groupe") as HTMLInputElement).value).toBe(
      "turn1",
    );
  });

  it("removes the user filter with its chip", async () => {
    const seen = mount(base(), calls({ user: "u1", uname: "Ana" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Retirer le filtre sur l'utilisateur" }),
    );
    await waitFor(() => {
      const last = [...seen].reverse().find((c) => is(c.path, "calls"))!;
      expect(query(last.path).has("user_id")).toBe(false);
    });
  });

  it("pages by « has more » and ends where it ends", async () => {
    const seen = mount(base({ more: true }), calls());
    await screen.findByText("Page 1");
    expect((screen.getByRole("button", { name: "Précédent" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Suivant" }));
    await screen.findByText("Page 2");
    expect(seen.some((c) => is(c.path, "calls") && query(c.path).get("offset") === "50")).toBe(
      true,
    );
  });

  it("has no pager when everything fits", async () => {
    mount(base(), calls());
    await screen.findByText("turn1");
    expect(screen.queryByRole("button", { name: "Suivant" })).toBeNull();
  });

  it("disables « next » on the last page", async () => {
    mount(base({ more: false }), calls({ page: 1 }));
    await screen.findByText("Page 2");
    expect((screen.getByRole("button", { name: "Suivant" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("says when no call matches, and when the calls cannot load", async () => {
    mount(base({ calls: [] }), calls());
    expect(await screen.findByText("Aucun appel ne correspond.")).toBeTruthy();
  });

  it("is an error when the calls cannot be loaded", async () => {
    mount(
      (method, path, body) =>
        is(path, "calls")
          ? { status: 500, body: { code: "x", message: "x" } }
          : base()(method, path, body),
      calls(),
    );
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
  });

  it("scrolls sideways on a narrow screen rather than breaking the page", async () => {
    mount(base(), calls());
    const table = (await screen.findByRole("table")).closest("div.overflow-x-auto");
    expect(table).toBeTruthy();
  });
});

describe("in English", () => {
  it("writes the labels, the cost sentence and the amounts in English", () =>
    withLocale("en", async () => {
      mount(
        base({
          summary: { totals: totals({ calls: 5, cost_usd: 1.5, costed_calls: 2 }), models: [] },
          users: [user({ cost_usd: 1.5, costed_calls: 2 })],
        }),
      );
      expect(
        await screen.findByText("Calls with a cost reported by the provider: 2 of 5."),
      ).toBeTruthy();
      expect(screen.getByRole("button", { name: "Last 30 days" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "By user" })).toBeTruthy();
      expect(screen.getAllByText("US$1.5000").length).toBeGreaterThan(0);
      fireEvent.click(screen.getByRole("button", { name: "Calls" }));
      expect(await screen.findByLabelText("Status")).toBeTruthy();
      expect(screen.getByText("Lesson turn")).toBeTruthy();
    }));
});

describe("what the screen does while it waits, and when the address moves under it", () => {
  it("says it is loading until the first answer, then shows the data", async () => {
    mount(base());
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Chargement…").length).toBeGreaterThan(0);
    expect(await screen.findByText("Ana")).toBeTruthy();
    await waitFor(() => expect(screen.queryAllByText("Chargement…")).toHaveLength(0));
  });

  it("says it is loading in the calls view too", async () => {
    mount(base(), { ...DEFAULT_SEARCH, view: "calls" });
    expect(screen.getAllByText("Chargement…").length).toBeGreaterThan(0);
    await screen.findByText("turn1");
  });

  it("says it is loading while a user's detail comes", async () => {
    mount((method, path, body) =>
      is(path, "users/u1")
        ? { body: { user: {}, totals: totals(), by_role: [], by_model: [] } }
        : base()(method, path, body),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Détail de Ana" }));
    expect(screen.getAllByText("Chargement…").length).toBeGreaterThan(0);
    await screen.findByText("Par rôle");
  });

  it("the search box follows the address when it changes under it (Back, a link)", async () => {
    function Moving() {
      const [search, setSearch] = useState(DEFAULT_SEARCH);
      return (
        <>
          <button type="button" onClick={() => setSearch((s) => ({ ...s, q: "zoé" }))}>
            go
          </button>
          <UsagePanel
            search={search}
            onChange={(patch) => setSearch((s) => ({ ...s, ...patch }))}
          />
        </>
      );
    }
    const calls = mockApi(base());
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Moving />
      </QueryClientProvider>,
    );
    const box = (await screen.findByLabelText("Rechercher par nom ou email")) as HTMLInputElement;
    fireEvent.change(box, { target: { value: "mar" } });
    fireEvent.click(screen.getByRole("button", { name: "go" })); // the address moves before the debounce fires
    await waitFor(() => expect(box.value).toBe("zoé"));
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(calls.some((c) => query(c.path).get("q") === "mar")).toBe(false); // the stale text is not re-applied
    expect(box.value).toBe("zoé");
  });

  it("choosing the period already chosen measures it again", async () => {
    const calls = mount(base());
    await screen.findByText("Ana");
    const sinces = () =>
      calls.filter((c) => is(c.path, "summary")).map((c) => query(c.path).get("since")!);
    const first = sinces()[0]!;
    await new Promise((resolve) => setTimeout(resolve, 15));
    fireEvent.click(screen.getByRole("button", { name: "30 derniers jours" }));
    await waitFor(() => expect(sinces().some((since) => since > first)).toBe(true));
  });

  it("warns when the custom range ends before it starts", async () => {
    mount(base(), { ...DEFAULT_SEARCH, period: "custom", from: "2026-03-09", to: "2026-03-01" });
    expect((await screen.findByRole("alert")).textContent).toContain("date de fin précède");
  });

  it("says nothing of it for a range in order", async () => {
    mount(base(), { ...DEFAULT_SEARCH, period: "custom", from: "2026-03-01", to: "2026-03-09" });
    await screen.findByText("Ana");
    expect(screen.queryByText(/date de fin précède/)).toBeNull();
  });
});
