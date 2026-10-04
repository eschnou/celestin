import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { meQuery } from "./lib/auth";
import { bindLocaleToQueryClient } from "./lib/i18n";
import { setUnauthorizedHandler } from "./lib/tutor/client";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  const queryClient = new QueryClient();
  // An expired session must not leave a stale user in the cache: the next guard
  // then redirects to sign-in instead of letting her into pages that only 401. The
  // language is left alone here: changing it would remount a lesson that is still on
  // screen; `requireUser` resets it when the redirect to sign-in happens.
  setUnauthorizedHandler(() => queryClient.setQueryData(meQuery.queryKey, null));

  // The language follows the signed-in user held in this cache (client only: the server
  // takes it from the request).
  if (typeof window !== "undefined") bindLocaleToQueryClient(queryClient);

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
