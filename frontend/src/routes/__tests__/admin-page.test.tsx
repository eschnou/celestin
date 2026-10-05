// @vitest-environment jsdom
/** Spec 012: the administrator's dashboard, and who may reach it. */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UsersPanel } from "@/components/celestin/admin/users-panel";
import type { AdminUser, UserList } from "@/lib/admin";
import type { User } from "@/lib/auth";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes, USER } from "@/test/route-harness";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Route as AdminFile } from "../_auth/admin/index";
import { Route as UsageFile } from "../_auth/admin/usage";

const ADMIN: User = { ...USER, id: "a1", email: "admin@x.be", name: "Admin", role: "admin" };

const row = (over: Partial<AdminUser>): AdminUser => ({
  id: "u1",
  email: "lea@x.be",
  name: "Léa",
  role: "student",
  locale: "fr",
  enabled: true,
  created_at: "2026-09-01T10:00:00Z",
  last_seen_at: null,
  ...over,
});

const WAITING = row({ id: "u2", email: "zoe@x.be", name: "Zoé", enabled: false });
const LIST: UserList = {
  users: [WAITING, row({}), row({ id: "a1", email: "admin@x.be", name: "Admin", role: "admin" })],
  total: 3,
  counts: { total: 3, enabled: 2, disabled: 1 },
  registration_mode: "verification",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mountPanel(handler: Parameters<typeof mockApi>[0]) {
  const calls = mockApi(handler);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <UsersPanel me={ADMIN} />
    </QueryClientProvider>,
  );
  return calls;
}

const users = (path: string) => path.startsWith("/api/admin/users?");

describe("the users panel", () => {
  it("lists the accounts and the registration mode", async () => {
    mountPanel((method, path) => (method === "GET" && users(path) ? { body: LIST } : undefined));
    expect(await screen.findByText("Zoé")).toBeTruthy();
    expect(screen.getByText(/Sur validation/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tous (3)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Désactivés (1)" })).toBeTruthy();
    expect(screen.getAllByText("Jamais", { selector: "td" }).length).toBeGreaterThan(0);
  });

  it("offers no button on the administrator's own row", async () => {
    mountPanel((method, path) => (method === "GET" && users(path) ? { body: LIST } : undefined));
    const own = (await screen.findByText("Admin", { selector: "td" })).closest("tr")!;
    expect(within(own).queryAllByRole("button")).toHaveLength(0);
    expect(within(own).getByText("(toi)")).toBeTruthy();
  });

  it("enables a waiting account and refreshes the list", async () => {
    let enabled = false;
    const calls = mountPanel((method, path) => {
      if (method === "PATCH" && path === "/api/admin/users/u2") {
        enabled = true;
        return { body: { user: { ...WAITING, enabled: true } } };
      }
      if (method === "GET" && users(path)) {
        const rows = enabled ? [{ ...WAITING, enabled: true }, ...LIST.users.slice(1)] : LIST.users;
        return {
          body: {
            ...LIST,
            users: rows,
            counts: { total: 3, enabled: enabled ? 3 : 2, disabled: enabled ? 0 : 1 },
          },
        };
      }
      return undefined;
    });
    fireEvent.click(await screen.findByRole("button", { name: "Activer le compte de Zoé" }));
    await screen.findByRole("button", { name: "Désactivés (0)" });
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ enabled: true });
  });

  it("asks before disabling, and only then sends it", async () => {
    const calls = mountPanel((method, path) => {
      if (method === "PATCH") return { body: { user: row({ enabled: false }) } };
      if (method === "GET" && users(path)) return { body: LIST };
      return undefined;
    });
    fireEvent.click(await screen.findByRole("button", { name: "Désactiver le compte de Léa" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/déconnecté partout/)).toBeTruthy();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    fireEvent.click(within(dialog).getByRole("button", { name: "Désactiver" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")).toMatchObject({
        path: "/api/admin/users/u1",
        body: { enabled: false },
      }),
    );
  });

  it("shows a reset password once, in a dialog", async () => {
    mountPanel((method, path) => {
      if (method === "POST" && path === "/api/admin/users/u1/reset-password")
        return { body: { user: row({}), password: "Zx9-temporaire-ok" } };
      if (method === "GET" && users(path)) return { body: LIST };
      return undefined;
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Réinitialiser le mot de passe de Léa" }),
    );
    fireEvent.click(
      await within(await screen.findByRole("alertdialog")).findByRole("button", {
        name: "Réinitialiser",
      }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Zx9-temporaire-ok")).toBeTruthy();
    expect(within(dialog).getByText("Nouveau mot de passe de Léa")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.queryByText("Zx9-temporaire-ok")).toBeNull());
  });

  it("filters by status and searches by name", async () => {
    const calls = mountPanel((method, path) =>
      method === "GET" && users(path) ? { body: LIST } : undefined,
    );
    await screen.findByText("Zoé");
    fireEvent.click(screen.getByRole("button", { name: "Désactivés (1)" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("status=disabled"))).toBe(true));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zo" } });
    await waitFor(() => expect(calls.some((c) => c.path.includes("q=zo"))).toBe(true));
  });

  it("shows the server's reason when an action is refused", async () => {
    mountPanel((method, path) => {
      if (method === "PATCH")
        return {
          status: 409,
          body: {
            code: "own_account",
            message: "Tu ne peux pas faire cela sur ton propre compte.",
          },
        };
      if (method === "GET" && users(path)) return { body: LIST };
      return undefined;
    });
    fireEvent.click(await screen.findByRole("button", { name: "Activer le compte de Zoé" }));
    expect((await screen.findByRole("alert")).textContent).toContain("propre compte");
  });

  it("steps back a page when enabling the last row of the last page empties it", async () => {
    const many = (n: number, start: number): AdminUser[] =>
      Array.from({ length: n }, (_, i) =>
        row({
          id: `p${start + i}`,
          email: `p${start + i}@x.be`,
          name: `P${start + i}`,
          enabled: false,
        }),
      );
    let enabledOne = false;
    const calls = mountPanel((method, path) => {
      if (method === "PATCH") {
        enabledOne = true;
        return { body: { user: row({ id: "p25", enabled: true }) } };
      }
      if (method !== "GET" || !users(path)) return undefined;
      const offset = Number(new URL(path, "http://x").searchParams.get("offset"));
      // 26 waiting accounts before; after the one on page two is enabled, 25.
      const total = enabledOne ? 25 : 26;
      const rows = offset === 0 ? many(25, 0) : enabledOne ? [] : many(1, 25);
      return {
        body: { ...LIST, users: rows, total, counts: { total, enabled: 0, disabled: total } },
      };
    });
    fireEvent.click(await screen.findByRole("button", { name: "Suivant" }, { timeout: 4000 }));
    await screen.findByText("P25", {}, { timeout: 4000 });
    fireEvent.click(
      await screen.findByRole("button", { name: "Activer le compte de P25" }, { timeout: 4000 }),
    );
    await screen.findByText("P0", {}, { timeout: 4000 });
    expect(calls.filter((c) => c.path.includes("offset=0")).length).toBeGreaterThan(1);
  });

  it("is in English with an English interface", () =>
    withLocale("en", async () => {
      mountPanel((method, path) => (method === "GET" && users(path) ? { body: LIST } : undefined));
      expect(
        await screen.findByRole("button", { name: "Disable the account of Léa" }),
      ).toBeTruthy();
      expect(screen.getByRole("button", { name: "Disabled (1)" })).toBeTruthy();
      expect(screen.getByText(/On approval/)).toBeTruthy();
    }));
});

describe("who reaches the dashboard", () => {
  const handler: Parameters<typeof mockApi>[0] = (method, path) =>
    method === "GET" && users(path) ? { body: LIST } : undefined;

  it("an administrator lands on it", async () => {
    mockApi(handler, ADMIN);
    const { router } = mountRoutes([{ path: "/admin/", file: AdminFile }], "/admin");
    expect(await screen.findByRole("heading", { name: "Administration", level: 1 })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/admin");
  });

  it("an administrator sent to a student's page is sent to the dashboard", async () => {
    mockApi(handler, ADMIN);
    const { router } = mountRoutes(
      [
        { path: "/admin/", file: AdminFile },
        { path: "/courses/", file: { options: { component: () => <p>courses</p> } } },
      ],
      "/courses",
    );
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin"));
    expect(screen.queryByText("courses")).toBeNull();
  });

  it("a student sent to the dashboard is sent to their courses", async () => {
    mockApi(handler, {});
    const { router } = mountRoutes(
      [
        { path: "/admin/", file: AdminFile },
        { path: "/courses/", file: { options: { component: () => <p>courses</p> } } },
      ],
      "/admin",
    );
    await waitFor(() => expect(router.state.location.pathname).toBe("/courses"));
    expect(await screen.findByText("courses")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Administration" })).toBeNull();
  });
});

describe("the usage screen (spec 015 R6.1)", () => {
  const handler: Parameters<typeof mockApi>[0] = (method, path) => {
    if (method !== "GET") return undefined;
    if (users(path)) return { body: LIST };
    if (path.startsWith("/api/admin/usage/summary")) {
      return {
        body: {
          totals: {
            calls: 0,
            input_tokens: 0,
            cached_tokens: 0,
            output_tokens: 0,
            reasoning_tokens: 0,
            cost_usd: null,
            costed_calls: 0,
          },
          models: [],
        },
      };
    }
    if (path.startsWith("/api/admin/usage/users?")) return { body: { users: [], total: 0 } };
    return undefined;
  };

  it("the dashboard links to it", async () => {
    mockApi(handler, ADMIN);
    mountRoutes(
      [
        { path: "/admin/", file: AdminFile },
        { path: "/admin/usage", file: UsageFile },
      ],
      "/admin",
    );
    const link = await screen.findByRole("link", { name: "Consommation de l'IA" });
    expect(link.getAttribute("href")).toBe("/admin/usage");
  });

  it("an administrator reaches it, with its filters read from the address", async () => {
    mockApi(handler, ADMIN);
    const { router } = mountRoutes(
      [
        { path: "/admin/", file: AdminFile },
        { path: "/admin/usage", file: UsageFile },
      ],
      "/admin/usage?period=7d&view=users",
    );
    expect(await screen.findByRole("heading", { name: "Consommation", level: 1 })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/admin/usage");
    expect(
      screen.getByRole("button", { name: "7 derniers jours" }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("a click on a period is written in the address", async () => {
    mockApi(handler, ADMIN);
    const { router } = mountRoutes(
      [
        { path: "/admin/", file: AdminFile },
        { path: "/admin/usage", file: UsageFile },
      ],
      "/admin/usage",
    );
    fireEvent.click(await screen.findByRole("button", { name: "Tout" }));
    await waitFor(() => expect(router.state.location.search).toMatchObject({ period: "all" }));
  });

  it("a student sent to it is sent to their courses", async () => {
    mockApi(handler, {});
    const { router } = mountRoutes(
      [
        { path: "/admin/usage", file: UsageFile },
        { path: "/courses/", file: { options: { component: () => <p>courses</p> } } },
      ],
      "/admin/usage",
    );
    await waitFor(() => expect(router.state.location.pathname).toBe("/courses"));
    expect(screen.queryByRole("heading", { name: "Consommation" })).toBeNull();
  });
});

describe("the missing-key banner (spec 013 R7.5)", () => {
  const withHealth =
    (configured: () => boolean): Parameters<typeof mockApi>[0] =>
    (method, path) => {
      if (method === "GET" && users(path)) return { body: LIST };
      if (method === "GET" && path === "/api/health")
        return { body: { status: "ok", ai_configured: configured(), voice: configured() } };
      return undefined;
    };

  it("tells the administrator, with a link to the settings, while there is no AI provider", async () => {
    mockApi(
      withHealth(() => false),
      ADMIN,
    );
    mountRoutes([{ path: "/admin/", file: AdminFile }], "/admin");
    const banner = await screen.findByText(/pas encore de fournisseur d'IA/);
    const link = within(banner.closest("p")!).getByRole("link", {
      name: "Choisir le fournisseur dans les Paramètres",
    });
    expect(link.getAttribute("href")).toBe("/settings");
  });

  it("says nothing when a provider is configured", async () => {
    mockApi(
      withHealth(() => true),
      ADMIN,
    );
    mountRoutes([{ path: "/admin/", file: AdminFile }], "/admin");
    await screen.findByRole("heading", { name: "Administration", level: 1 });
    await screen.findByText("Zoé");
    expect(screen.queryByText(/pas encore de fournisseur d'IA/)).toBeNull();
  });

  it("goes away when the health is read again after a provider was saved", async () => {
    let configured = false;
    mockApi(
      withHealth(() => configured),
      ADMIN,
    );
    const { queryClient } = mountRoutes([{ path: "/admin/", file: AdminFile }], "/admin");
    await screen.findByText(/pas encore de fournisseur d'IA/);
    configured = true;
    await queryClient.invalidateQueries({ queryKey: ["health"] });
    await waitFor(() => expect(screen.queryByText(/pas encore de fournisseur d'IA/)).toBeNull());
  });

  it("is in English for an English administrator", () =>
    withLocale("en", async () => {
      mockApi(
        withHealth(() => false),
        { ...ADMIN, locale: "en" },
      );
      mountRoutes([{ path: "/admin/", file: AdminFile }], "/admin");
      expect(await screen.findByText(/no AI provider yet/)).toBeTruthy();
      expect(screen.getByRole("link", { name: "Choose the provider in Settings" })).toBeTruthy();
    }));
});
