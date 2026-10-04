/**
 * Mounting file routes under jsdom. The generated route tree renders a full HTML
 * document, which jsdom cannot mount inside a container, so tests rebuild a small
 * tree with the real guard, loaders and components, and a scripted `fetch`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  type AnyRoute,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import { LocaleBoundary } from "@/components/celestin/locale-boundary";
import type { User } from "@/lib/auth";
import { bindLocaleToQueryClient } from "@/lib/i18n";
import { Route as AuthFile } from "@/routes/_auth";

export const USER: User = {
  id: "u1",
  email: "lea@example.be",
  name: "Léa",
  role: "student",
  locale: "fr",
};

export type Reply = { status?: number; body: unknown };
export type Handler = (method: string, path: string, body: unknown) => Reply | undefined;

/** A `fetch` that answers `/api/auth/me` and whatever `handler` knows; records every call.
 *  `user` overrides fields of the signed-in user (its language, say), or is `null` for nobody; a
 *  `PATCH` of `/api/auth/me` answers with the user changed, unless `handler` says otherwise. */
export function mockApi(handler: Handler, user: Partial<User> | null = {}) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  let me: User = { ...USER, ...user };
  const signedOut = user === null;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = String(url);
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body; // FormData as is
    calls.push({ method, path, body });
    let reply: Reply | undefined;
    if (path.endsWith("/api/auth/me") && method === "PATCH") {
      reply = handler(method, path, body);
      if (!reply) {
        me = { ...me, ...(body as Partial<User>) };
        reply = { body: { user: me } };
      }
    } else if (path.endsWith("/api/auth/me")) {
      reply = signedOut
        ? {
            status: 401,
            body: { code: "not_authenticated", message: "Connecte-toi pour continuer." },
          }
        : { body: { user: me } };
    } else {
      reply = handler(method, path, body);
    }
    const status = reply?.status ?? (reply ? 200 : 404);
    return {
      ok: status < 400,
      status,
      json: async () => reply?.body ?? { code: "not_found", message: "Cette page n'existe pas." },
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

type FileRoute = { options: { loader?: unknown; component?: unknown } };

export function mountRoutes(routes: { path: string; file: FileRoute }[], initial: string) {
  const rootRoute = createRootRouteWithContext<{ queryClient: QueryClient }>()({
    component: () => (
      <LocaleBoundary>
        <Outlet />
      </LocaleBoundary>
    ),
  });
  const authRoute = createRoute({
    getParentRoute: () => rootRoute,
    id: "_auth",
    beforeLoad: AuthFile.options.beforeLoad as never,
    component: AuthFile.options.component as never,
  }) as unknown as AnyRoute;
  const loginRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/login",
    validateSearch: (s: Record<string, unknown>) => s,
    component: () => <p>login</p>,
  });
  const children = routes.map(({ path, file }) =>
    createRoute({
      getParentRoute: () => authRoute,
      path,
      loader: file.options.loader as never,
      component: file.options.component as never,
    }),
  );
  const extras = [
    "/courses/$courseId/chapters/$chapterId/",
    "/courses/$courseId/chapters/$chapterId/content",
  ]
    .filter((path) => !routes.some((r) => r.path === path))
    .map((path) =>
      createRoute({ getParentRoute: () => authRoute, path, component: () => <p>{path}</p> }),
    );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const unbind = bindLocaleToQueryClient(queryClient);
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      loginRoute as never,
      authRoute.addChildren([...children, ...extras] as never) as never,
    ]),
    context: { queryClient },
    history: createMemoryHistory({ initialEntries: [initial] }),
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  );
  return { router, queryClient, unbind };
}
