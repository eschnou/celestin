// @vitest-environment jsdom
/** The pages around the application in both languages: 404, error, not-yet, the not-found
 *  card, the confirmation dialog (spec 010 R3). */
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "@/components/celestin/confirm-dialog";
import { NotFoundCard } from "@/components/celestin/not-found";
import { readError } from "@/lib/tutor/client";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes } from "@/test/route-harness";
import { Route as RootFile } from "../__root";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mountComponent(Component: ComponentType) {
  const root = createRootRoute({ component: Component as never });
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => null });
  const router = createRouter({
    routeTree: root.addChildren([index]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  render(<RouterProvider router={router as never} />);
  await screen.findByRole("link", { name: /cours|courses/i });
}

const NotFound = RootFile.options.notFoundComponent as ComponentType;
const Failed = RootFile.options.errorComponent as ComponentType<{
  error: Error;
  reset: () => void;
}>;

describe("the root 404 and error pages", () => {
  it("speaks French by default", async () => {
    await mountComponent(NotFound);
    expect(screen.getByRole("heading", { name: "Cette page n'existe pas" })).toBeTruthy();
    expect(screen.getByText("Elle a peut-être été déplacée. Retourne à tes cours.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Mes cours" })).toBeTruthy();
  });

  it("speaks English when the interface does", () =>
    withLocale("en", async () => {
      await mountComponent(NotFound);
      expect(screen.getByRole("heading", { name: "This page doesn't exist" })).toBeTruthy();
      expect(screen.getByRole("link", { name: "My courses" })).toBeTruthy();
    }));

  it("words the error boundary in both languages", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const boundary = () => <Failed error={new Error("boom")} reset={() => {}} />;
    await mountComponent(boundary);
    expect(screen.getByRole("heading", { name: "Cette page n'a pas pu s'afficher" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeTruthy();
    cleanup();
    await withLocale("en", async () => {
      await mountComponent(boundary);
      expect(screen.getByRole("heading", { name: "This page couldn't be displayed" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
      expect(screen.getByRole("link", { name: "My courses" })).toBeTruthy();
    });
    error.mockRestore();
  });
});

describe("the not-yet page", () => {
  const open = (locale: "fr" | "en") => {
    mockApi(() => undefined, { role: "parent", locale });
    mountRoutes(
      [{ path: "/courses", file: { options: { component: () => <p>courses</p> } } }],
      "/courses",
    );
  };

  it("names the role, in French", async () => {
    open("fr");
    expect(await screen.findByText("Cet espace n'est pas encore disponible")).toBeTruthy();
    expect(
      screen.getByText(
        "Ton compte a le rôle « parent ». Pour l'instant, seuls les élèves peuvent travailler avec Célestin.",
      ),
    ).toBeTruthy();
  });

  it("names the role, in English", () =>
    withLocale("en", async () => {
      open("en");
      expect(await screen.findByText("This space isn't available yet")).toBeTruthy();
      expect(
        screen.getByText(
          "Your account has the role “parent”. For now, only students can work with Célestin.",
        ),
      ).toBeTruthy();
    }));
});

describe("the not-found card", () => {
  it("words a 404 and another failure in both languages", () =>
    withLocale("en", async () => {
      await mountComponent(() => <NotFoundCard status={404} />);
      expect(screen.getByRole("heading", { name: "This page doesn't exist" })).toBeTruthy();
      expect(
        screen.getByText("This course or chapter doesn't exist, or it isn't yours."),
      ).toBeTruthy();
      cleanup();
      await mountComponent(() => <NotFoundCard status={500} />);
      expect(screen.getByRole("heading", { name: "This page couldn't be displayed" })).toBeTruthy();
      expect(screen.getByText("Try again in a moment.")).toBeTruthy();
    }));

  it("stays French by default", async () => {
    await mountComponent(() => <NotFoundCard status={404} />);
    expect(
      screen.getByText("Ce cours ou ce chapitre n'existe pas, ou n'est pas le tien."),
    ).toBeTruthy();
  });
});

describe("the confirmation dialog", () => {
  const open = () => {
    render(
      <ConfirmDialog
        trigger={<button>open</button>}
        title="t"
        description="d"
        confirm="ok"
        onConfirm={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "open" }));
  };

  it("offers « Annuler » in French", () => {
    open();
    expect(screen.getByRole("button", { name: "Annuler" })).toBeTruthy();
  });

  it("offers Cancel in English", () =>
    withLocale("en", () => {
      open();
      expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
    }));
});

describe("readError", () => {
  const response = (body: unknown) => ({ json: async () => body }) as unknown as Response;
  const rejected = () => ({ json: async () => Promise.reject(new Error("not json")) }) as never;

  it("replaces a framework 422 body with the catalog message, per language", async () => {
    const body = { detail: [{ msg: "field required" }] };
    expect((await readError(response(body))).message).toBe(
      "Célestin n'a pas pu traiter cette séance. Recharge la page pour en démarrer une neuve.",
    );
    await withLocale("en", async () => {
      const error = await readError(response(body));
      expect(error.code).toBe("invalid_request");
      expect(error.message).toBe(
        "Célestin couldn't handle this session. Reload the page to start a new one.",
      );
    });
  });

  it("uses the generic message when the body is not JSON, per language", async () => {
    expect((await readError(rejected())).message).toBe(
      "Célestin est injoignable pour le moment. Réessaie dans un instant.",
    );
    await withLocale("en", async () => {
      expect((await readError(rejected())).message).toBe(
        "Célestin can't be reached right now. Try again in a moment.",
      );
    });
  });

  it("passes the server's own message through verbatim under an English interface", () =>
    withLocale("en", async () => {
      const error = await readError(
        response({ code: "rate_limited", message: "Trop de demandes, patiente un peu." }),
      );
      expect(error).toEqual({
        code: "rate_limited",
        message: "Trop de demandes, patiente un peu.",
        issues: [],
      });
    }));
});
