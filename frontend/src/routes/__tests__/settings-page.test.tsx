// @vitest-environment jsdom
/** The settings screen and the user menu (spec 010 R1, R2). */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { stubLayoutApis } from "@/test/jsdom-stubs";
import { AppBar } from "@/components/celestin/app-bar";
import { ChapterBar } from "@/components/celestin/chapter-bar";
import { LoginForm, RegisterForm } from "@/components/celestin/auth-forms";
import { SettingsPage } from "@/components/celestin/settings/settings-page";
import type { SettingsSection } from "@/components/celestin/settings/sections";
import { frenchOutsideCourseText } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes, USER } from "@/test/route-harness";
import { Route as SettingsFile } from "../_auth/settings";

function mount(user: Parameters<typeof mockApi>[1] = {}, reply?: Parameters<typeof mockApi>[0]) {
  const calls = mockApi(reply ?? (() => undefined), user);
  const { router, queryClient } = mountRoutes(
    [{ path: "/settings", file: SettingsFile }],
    "/settings",
  );
  return { calls, router, queryClient };
}

const openMenu = (name: string) => {
  fireEvent.keyDown(screen.getByRole("button", { name }), { key: "Enter" });
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the settings screen", () => {
  it("shows the language and the password sections and no other", async () => {
    mount();
    expect(await screen.findByRole("heading", { name: "Paramètres", level: 1 })).toBeTruthy();
    const section = screen.getByRole("region", { name: "Langue" });
    const group = within(section).getByRole("radiogroup", { name: "Langue" });
    expect(
      within(group).getByRole("radio", { name: "Français" }).getAttribute("aria-checked"),
    ).toBe("true");
    expect(within(group).getByRole("radio", { name: "English" }).getAttribute("aria-checked")).toBe(
      "false",
    );
    // The password section (spec 012) is the only one with fields; no name or email field.
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.getAllByRole("region").map((r) => r.getAttribute("aria-labelledby"))).toEqual([
      "settings-language",
      "settings-password",
    ]);
  });

  it("marks English when the account is English", async () => {
    document.documentElement.lang = "en";
    mount({ locale: "en" });
    const english = await screen.findByRole("radio", { name: "English" });
    expect(english.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("heading", { name: "Settings", level: 1 })).toBeTruthy();
  });

  it("saves the choice to the account and re-words the page", async () => {
    const { calls } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: "English" }));
    expect(await screen.findByRole("heading", { name: "Settings", level: 1 })).toBeTruthy();
    expect(calls.filter((c) => c.method === "PATCH")).toEqual([
      { method: "PATCH", path: "/api/auth/me", body: { locale: "en" } },
    ]);
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByRole("radio", { name: "English" }).getAttribute("aria-checked")).toBe(
      "true",
    );
    // And back.
    fireEvent.click(screen.getByRole("radio", { name: "Français" }));
    expect(await screen.findByRole("heading", { name: "Paramètres", level: 1 })).toBeTruthy();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("keeps the previous language when saving fails, and says so", async () => {
    mount({}, (method, path) =>
      method === "PATCH" && path.endsWith("/api/auth/me")
        ? { status: 500, body: { code: "internal", message: "Erreur." } }
        : undefined,
    );
    fireEvent.click(await screen.findByRole("radio", { name: "English" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "La langue n'a pas pu être enregistrée",
    );
    expect(document.documentElement.lang).toBe("fr");
    expect(screen.getByRole("radio", { name: "Français" }).getAttribute("aria-checked")).toBe(
      "true",
    );
  });

  it("is not reachable signed out", async () => {
    const { router } = mount(null);
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(screen.queryByRole("radiogroup")).toBeNull();
  });

  it("sends a signed-out visitor to sign-in in the browser's language", async () => {
    Object.defineProperty(window.navigator, "languages", {
      value: ["en-GB", "fr-BE"],
      configurable: true,
    });
    document.documentElement.lang = "fr";
    const { router } = mount(null);
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(document.documentElement.lang).toBe("en");
  });

  it("marks what the server wrote in the old language as stale, and leaves the account alone", async () => {
    const { queryClient } = mount();
    queryClient.setQueryData(["subjects"], {
      subjects: [{ id: "sciences", label: "Physique", languages: ["fr"] }],
    });
    queryClient.setQueryData(["courses"], { courses: [] });
    fireEvent.click(await screen.findByRole("radio", { name: "English" }));
    await screen.findByRole("heading", { name: "Settings", level: 1 });
    expect(queryClient.getQueryState(["subjects"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["courses"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["me"])?.isInvalidated).toBe(false);
  });

  it("goes back to the page it came from, or to the courses when there is none", async () => {
    const other = { options: { component: () => <p>the page before</p> } };
    mockApi(() => undefined);
    const { router } = mountRoutes(
      [
        { path: "/other", file: other as never },
        { path: "/settings", file: SettingsFile },
      ],
      "/other",
    );
    await screen.findByText("the page before");
    await router.navigate({ to: "/settings" } as never);
    fireEvent.click(await screen.findByRole("button", { name: "Retour" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/other"));
    cleanup();

    mount();
    const link = await screen.findByRole("link", { name: "Retour" });
    expect(link.getAttribute("href")).toBe("/courses");
  });

  it("renders every registered section without knowing what it holds", () => {
    const sections: SettingsSection[] = [
      { id: "demo", title: () => "Démo", Component: () => <p>contenu de la démo</p> },
    ];
    const root = createRootRoute({
      component: () => <SettingsPage user={USER} sections={sections} />,
    });
    const router = createRouter({
      routeTree: root,
      history: createMemoryHistory({ initialEntries: ["/"] }),
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router as never} />
      </QueryClientProvider>,
    );
    return screen.findByRole("region", { name: "Démo" }).then((region) => {
      expect(within(region).getByText("contenu de la démo")).toBeTruthy();
    });
  });
});

describe("no language control outside the settings (R1.4)", () => {
  it("is not on the sign-in or registration forms", () => {
    render(<LoginForm onSuccess={() => undefined} />);
    expect(screen.queryByRole("radiogroup")).toBeNull();
    cleanup();
    render(<RegisterForm onSuccess={() => undefined} />);
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByText("English")).toBeNull();
  });
});

describe("the user menu", () => {
  function inRouter(element: React.ReactNode) {
    const root = createRootRoute({ component: () => element });
    const settings = createRoute({
      getParentRoute: () => root,
      path: "/settings",
      component: () => <p>réglages</p>,
    });
    const login = createRoute({
      getParentRoute: () => root,
      path: "/login",
      validateSearch: (s: Record<string, unknown>) => s,
      component: () => <p>connexion</p>,
    });
    const router = createRouter({
      routeTree: root.addChildren([settings, login]),
      history: createMemoryHistory({ initialEntries: ["/"] }),
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router as never} />
      </QueryClientProvider>,
    );
    return router;
  }

  it("offers the settings and sign-out in the courses bar", async () => {
    const router = inRouter(<AppBar user={USER} />);
    await screen.findByRole("button", { name: "Léa" });
    openMenu("Léa");
    const settings = await screen.findByRole("menuitem", { name: "Paramètres" });
    fireEvent.click(settings);
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings"));
  });

  it("is the same menu in the chapter bar", async () => {
    inRouter(
      <ChapterBar
        chapter={{ id: "h1", course_id: "c1", course_name: "Maths", title: "Suites" } as never}
        user={USER}
        mode="parcours"
      />,
    );
    await screen.findByRole("button", { name: "Léa" });
    openMenu("Léa");
    expect(await screen.findByRole("menuitem", { name: "Paramètres" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Se déconnecter" })).toBeTruthy();
  });

  it("is a « ⋯ » button on a phone, with the chapter's content above the account's entries", async () => {
    stubLayoutApis();
    inRouter(
      <ChapterBar
        chapter={{ id: "h1", course_id: "c1", course_name: "Maths", title: "Suites" } as never}
        user={USER}
        mode="parcours"
      />,
    );
    // The way back names the course; the two modes share the bar.
    await screen.findByRole("link", { name: "Maths" });
    expect(screen.getByRole("button", { name: "Parcours" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Discussion" })).toBeTruthy();
    openMenu("Menu");
    expect(await screen.findByText("Léa")).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Contenu du chapitre" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Paramètres" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Se déconnecter" })).toBeTruthy();
  });

  it("speaks English with an English account", async () => {
    document.documentElement.lang = "en";
    inRouter(<AppBar user={{ ...USER, locale: "en" }} />);
    await screen.findByRole("button", { name: "Léa" });
    openMenu("Léa");
    expect(await screen.findByRole("menuitem", { name: "Settings" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeTruthy();
  });

  it("signs out and returns the page to the browser's language", async () => {
    const calls = mockApi(() => ({ status: 204, body: null }));
    Object.defineProperty(window.navigator, "languages", {
      value: ["en-GB", "fr-BE"],
      configurable: true,
    });
    document.documentElement.lang = "fr";
    const router = inRouter(<AppBar user={USER} />);
    await screen.findByRole("button", { name: "Léa" });
    openMenu("Léa");
    fireEvent.click(await screen.findByRole("menuitem", { name: "Se déconnecter" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(calls.some((c) => c.path.endsWith("/api/auth/logout"))).toBe(true);
    expect(document.documentElement.lang).toBe("en");
  });
});

describe("the settings registry", () => {
  it("is the one place a section is added", async () => {
    const { SECTIONS, languageSection, passwordSection, aiSection } =
      await import("@/components/celestin/settings/sections");
    expect(SECTIONS).toEqual([languageSection, passwordSection, aiSection]);
    expect(aiSection.roles).toEqual(["admin"]);
  });
});

describe("the password section (spec 012)", () => {
  async function open() {
    const handler: Parameters<typeof mockApi>[0] = (method, path) =>
      method === "POST" && path === "/api/auth/password" ? { status: 204, body: null } : undefined;
    const calls = mockApi(handler);
    mountRoutes([{ path: "/settings", file: SettingsFile }], "/settings");
    await screen.findByRole("heading", { name: "Paramètres", level: 1 });
    return calls;
  }
  const fill = (current: string, next: string) => {
    fireEvent.input(screen.getByLabelText("Mot de passe actuel"), { target: { value: current } });
    fireEvent.input(screen.getByLabelText("Nouveau mot de passe"), { target: { value: next } });
    fireEvent.click(screen.getByRole("button", { name: "Changer le mot de passe" }));
  };

  it("checks the new password's length before asking the server", async () => {
    const calls = await open();
    fill("mot-de-passe-solide", "court");
    await screen.findByText("Le mot de passe doit faire au moins 6 caractères.");
    expect(calls.some((c) => c.path === "/api/auth/password")).toBe(false);
  });

  it("sends both passwords and says it worked", async () => {
    const calls = await open();
    fill("mot-de-passe-solide", "un-autre-mot-de-passe");
    expect(await screen.findByText("Ton mot de passe a été changé.")).toBeTruthy();
    expect(calls.find((c) => c.path === "/api/auth/password")).toEqual({
      method: "POST",
      path: "/api/auth/password",
      body: { current_password: "mot-de-passe-solide", new_password: "un-autre-mot-de-passe" },
    });
  });

  it("shows the server's refusal and keeps the fields", async () => {
    mockApi((method, path) =>
      method === "POST" && path === "/api/auth/password"
        ? {
            status: 422,
            body: { code: "wrong_password", message: "Le mot de passe actuel est incorrect." },
          }
        : undefined,
    );
    mountRoutes([{ path: "/settings", file: SettingsFile }], "/settings");
    await screen.findByRole("heading", { name: "Paramètres", level: 1 });
    fill("pas-le-bon-mot-de-passe", "un-autre-mot-de-passe");
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Le mot de passe actuel est incorrect.",
    );
  });
});
