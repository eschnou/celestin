// @vitest-environment jsdom
/** Spec 013 R1, R2: the first-run setup page. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
  type AnyRoute,
} from "@tanstack/react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { withLocale } from "@/test/locale";
import { frenchOutsideCourseText } from "@/test/english-sweep";
import { mockApi, type Handler } from "@/test/route-harness";
import { Route as LoginFile } from "../login";
import { Route as SetupFile } from "../setup";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ADMIN = { id: "u1", email: "ada@example.be", name: "Ada", role: "admin", locale: "fr" };

function mount(handler: Handler, setupRequired = true, guardMs = 0) {
  // The instance stops waiting the moment the administrator is created, as the real server does.
  let waiting = setupRequired;
  const calls = mockApi((method, url, body) => {
    if (url === "/api/auth/config")
      return { body: { registration: "open", setup_required: waiting } };
    const reply = handler(method, url, body);
    if (method === "POST" && url === "/api/setup" && (reply?.status ?? 200) < 400) waiting = false;
    return reply;
  }, null);
  const root = createRootRoute();
  const page = (path: string, component: unknown, beforeLoad?: () => Promise<void>) =>
    createRoute({
      getParentRoute: () => root as never,
      path,
      validateSearch: (search: Record<string, unknown>) => search,
      ...(beforeLoad ? { beforeLoad } : {}),
      component: component as never,
    }) as unknown as AnyRoute;
  const router = createRouter({
    routeTree: root.addChildren([
      page("/setup", SetupFile.options.component),
      page("/login", LoginFile.options.component),
      // The real guard is asynchronous: for a moment the page is still /setup, whose config has changed.
      page(
        "/admin",
        () => <p>the dashboard</p>,
        () => new Promise((resolve) => setTimeout(resolve, guardMs)),
      ),
    ] as never),
    history: createMemoryHistory({ initialEntries: ["/setup"] }),
  } as never);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  );
  return { calls, queryClient };
}

const fill = (name: string, email: string, password: string) => {
  fireEvent.input(screen.getByLabelText("Prénom"), { target: { value: name } });
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.input(screen.getByLabelText("Mot de passe"), { target: { value: password } });
};

describe("the setup page", () => {
  it("waits for the answer, then shows the form with the product's name", async () => {
    mount(() => undefined);
    expect(await screen.findByRole("form", { name: "Installation" })).toBeTruthy();
    expect(screen.getByText("Célestin")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Bienvenue sur Célestin" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Créer l'administrateur" })).toBeTruthy();
  });

  it("validates before calling the API", async () => {
    const { calls } = mount(() => undefined);
    await screen.findByRole("form", { name: "Installation" });
    fireEvent.click(screen.getByRole("button", { name: "Créer l'administrateur" }));
    await screen.findByText("Indique ton prénom.");
    expect(calls.some((c) => c.path === "/api/setup")).toBe(false);
  });

  it("applies the password rule of registration", async () => {
    mount(() => undefined);
    await screen.findByRole("form", { name: "Installation" });
    fill("Ada", "ada@example.be", "court");
    fireEvent.click(screen.getByRole("button", { name: "Créer l'administrateur" }));
    expect(await screen.findByText(/au moins 12 caractères|au moins \d+ caractères/)).toBeTruthy();
  });

  it("creates the administrator, caches them and lands on the dashboard", async () => {
    const { calls, queryClient } = mount((method, url) =>
      method === "POST" && url === "/api/setup"
        ? { status: 201, body: { user: ADMIN } }
        : undefined,
    );
    await screen.findByRole("form", { name: "Installation" });
    fill("Ada", "ada@example.be", "mot-de-passe-solide");
    fireEvent.click(screen.getByRole("button", { name: "Créer l'administrateur" }));
    expect(await screen.findByText("the dashboard")).toBeTruthy();
    const call = calls.find((c) => c.path === "/api/setup");
    expect(call?.body).toEqual({
      email: "ada@example.be",
      password: "mot-de-passe-solide",
      name: "Ada",
    });
    expect(queryClient.getQueryData(["me"])).toEqual(ADMIN);
  });

  it("does not send the new administrator to sign-in when the config stops asking for setup", async () => {
    mount(
      (method, url) =>
        method === "POST" && url === "/api/setup"
          ? { status: 201, body: { user: ADMIN } }
          : undefined,
      true,
      60,
    );
    await screen.findByRole("form", { name: "Installation" });
    fill("Ada", "ada@example.be", "mot-de-passe-solide");
    fireEvent.click(screen.getByRole("button", { name: "Créer l'administrateur" }));
    expect(await screen.findByText("the dashboard", {}, { timeout: 2000 })).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 50)); // the refetched config arrives
    expect(screen.getByText("the dashboard")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Connexion" })).toBeNull();
  });

  it("knows the instance no longer waits, and reads the health again for the key", async () => {
    const { queryClient } = mount((method, url) =>
      method === "POST" && url === "/api/setup"
        ? { status: 201, body: { user: ADMIN } }
        : undefined,
    );
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await screen.findByRole("form", { name: "Installation" });
    fill("Ada", "ada@example.be", "mot-de-passe-solide");
    fireEvent.click(screen.getByRole("button", { name: "Créer l'administrateur" }));
    await screen.findByText("the dashboard");
    expect(queryClient.getQueryData(["auth-config"])).toMatchObject({ setupRequired: false });
    expect(invalidate.mock.calls.map((c) => c[0]?.queryKey)).toEqual([["health"]]);
  });

  it("shows the server's refusal under the form", async () => {
    mount((method, url) =>
      method === "POST" && url === "/api/setup"
        ? {
            status: 409,
            body: {
              code: "setup_done",
              message: "L'installation est déjà terminée. Connecte-toi.",
            },
          }
        : undefined,
    );
    await screen.findByRole("form", { name: "Installation" });
    fill("Ada", "ada@example.be", "mot-de-passe-solide");
    fireEvent.click(screen.getByRole("button", { name: "Créer l'administrateur" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("L'installation est déjà terminée");
    expect(screen.queryByText("the dashboard")).toBeNull();
  });

  it("leads to sign-in when there is nothing to set up", async () => {
    mount(() => undefined, false);
    expect(await screen.findByRole("form", { name: "Connexion" })).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Installation" })).toBeNull();
  });

  it("still shows the form when the config cannot be read: the server decides", async () => {
    mockApi(
      (_method, url) =>
        url === "/api/auth/config"
          ? { status: 502, body: { code: "internal", message: "x" } }
          : undefined,
      null,
    );
    const root = createRootRoute();
    const route = createRoute({
      getParentRoute: () => root as never,
      path: "/setup",
      component: SetupFile.options.component as never,
    }) as unknown as AnyRoute;
    const router = createRouter({
      routeTree: root.addChildren([route] as never),
      history: createMemoryHistory({ initialEntries: ["/setup"] }),
    } as never);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <RouterProvider router={router as never} />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("form", { name: "Installation" })).toBeTruthy();
  });

  it("is in English, with no French left behind, for an English visitor", () =>
    withLocale("en", async () => {
      mount(() => undefined);
      expect(await screen.findByRole("form", { name: "Setup" })).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Welcome to Célestin" })).toBeTruthy();
      await waitFor(() => expect(frenchOutsideCourseText()).toEqual([]));
    }));
});
