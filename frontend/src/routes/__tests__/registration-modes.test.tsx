// @vitest-environment jsdom
/** Spec 012: the sign-in and registration pages follow the registration mode. */
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
import type { RegistrationMode } from "@/lib/auth";
import { mockApi } from "@/test/route-harness";
import { Route as LoginFile } from "../login";
import { Route as RegisterFile } from "../register";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(
  path: "/login" | "/register",
  mode: RegistrationMode,
  options: { configFails?: boolean; setupRequired?: boolean } = {},
) {
  const calls = mockApi((method, url) => {
    if (url === "/api/auth/config")
      return options.configFails
        ? { status: 502, body: { code: "internal", message: "x" } }
        : { body: { registration: mode, setup_required: options.setupRequired ?? false } };
    if (method === "POST" && url === "/api/auth/register")
      return {
        status: 202,
        body: {
          user: { id: "u2", email: "a@x.be", name: "Ana", role: "student", locale: "fr" },
          pending: true,
        },
      };
    return undefined;
  }, null);
  const root = createRootRoute();
  const page = (path: string, component: unknown) =>
    createRoute({
      getParentRoute: () => root as never,
      path,
      validateSearch: (search: Record<string, unknown>) => search,
      component: component as never,
    }) as unknown as AnyRoute;
  const routes = [
    page("/login", LoginFile.options.component),
    page("/register", RegisterFile.options.component),
    page("/setup", () => <p>the setup page</p>),
  ];
  const router = createRouter({
    routeTree: root.addChildren(routes as never),
    history: createMemoryHistory({ initialEntries: [path] }),
  } as never);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  );
  return calls;
}

describe("the sign-in page", () => {
  it.each(["open", "verification"] as const)("offers registration in %s mode", async (mode) => {
    mount("/login", mode);
    expect(await screen.findByRole("link", { name: "Créer mon compte" })).toBeTruthy();
  });

  it("still offers registration when the mode cannot be read", async () => {
    mount("/login", "open", { configFails: true });
    expect(await screen.findByRole("link", { name: "Créer mon compte" })).toBeTruthy();
  });

  it("has no link to registration when it is closed", async () => {
    const calls = mount("/login", "closed");
    await waitFor(() => expect(calls.some((c) => c.path === "/api/auth/config")).toBe(true));
    await screen.findByRole("form", { name: "Connexion" });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("link", { name: "Créer mon compte" })).toBeNull();
    expect(screen.queryByText("Pas encore de compte ?")).toBeNull();
  });
});

describe("the registration page", () => {
  it("shows the form when open, with no note", async () => {
    mount("/register", "open");
    expect(await screen.findByRole("form", { name: "Inscription" })).toBeTruthy();
    expect(screen.queryByText(/vérifiés par un administrateur/)).toBeNull();
  });

  it("says so, and shows no form, when closed", async () => {
    mount("/register", "closed");
    expect(
      await screen.findByRole("heading", { name: "Les inscriptions sont fermées" }),
    ).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Inscription" })).toBeNull();
    expect(screen.getByRole("link", { name: "Se connecter" })).toBeTruthy();
  });

  it("warns that an administrator checks new accounts, then waits for one", async () => {
    mount("/register", "verification");
    expect(await screen.findByText(/vérifiés par un administrateur/)).toBeTruthy();
    fireEvent.input(screen.getByLabelText("Prénom"), { target: { value: "Ana" } });
    fireEvent.input(screen.getByLabelText("Email"), { target: { value: "a@x.be" } });
    fireEvent.input(screen.getByLabelText("Mot de passe"), {
      target: { value: "mot-de-passe-solide" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Créer mon compte" }));
    expect(await screen.findByRole("heading", { name: "Compte créé" })).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Inscription" })).toBeNull();
    expect(screen.getByRole("link", { name: "Retour à la connexion" })).toBeTruthy();
  });
});

describe("a fresh instance waits for its first administrator (spec 013)", () => {
  it.each(["/login", "/register"] as const)("sends %s to /setup", async (path) => {
    mount(path, "open", { setupRequired: true });
    expect(await screen.findByText("the setup page")).toBeTruthy();
  });

  it("sends /register to /setup even when registration is closed", async () => {
    mount("/register", "closed", { setupRequired: true });
    expect(await screen.findByText("the setup page")).toBeTruthy();
  });

  it("leaves both pages alone once the instance has an account", async () => {
    mount("/login", "open", { setupRequired: false });
    expect(await screen.findByRole("form", { name: "Connexion" })).toBeTruthy();
    cleanup();
    mount("/register", "open", { setupRequired: false });
    expect(await screen.findByRole("form", { name: "Inscription" })).toBeTruthy();
  });
});
