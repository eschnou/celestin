/** The interface language at runtime (spec 010 §5.1). No locale in the URL and no
 *  cookie: the server takes it from `Accept-Language`; the client from the signed-in
 *  user's stored language (in the `me` query cache), else from the `<html lang>` the
 *  server rendered, which is what keeps hydration identical.
 *
 *  Message functions (`m.some_key()`) read the locale when called, so a component
 *  shows a new language only when it renders again: `useLocale()` at the root keys
 *  the route tree on it. Never call `m.*()` at module scope. */

import type { QueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import {
  defineCustomClientStrategy,
  defineCustomServerStrategy,
  getLocale,
} from "@/paraglide/runtime";
import { isLocale, matchLocale, parseAcceptLanguage, type Locale } from "./locale";
import { ME_QUERY_KEY } from "./me-key";

const ACCOUNT_STRATEGY = "custom-account";
const HEADER_STRATEGY = "custom-header";

let queryClient: QueryClient | undefined;
const listeners = new Set<() => void>();

function notify(): void {
  if (typeof document !== "undefined") {
    const locale = getLocale();
    if (document.documentElement.lang !== locale) document.documentElement.lang = locale;
  }
  listeners.forEach((listener) => listener());
}

type CachedUser = { locale?: unknown } | null | undefined;

function accountLocale(): Locale | undefined {
  const user = queryClient?.getQueryData<CachedUser>(ME_QUERY_KEY);
  return isLocale(user?.locale) ? user.locale : undefined;
}

function documentLocale(): Locale | undefined {
  if (typeof document === "undefined") return undefined;
  const lang = document.documentElement.lang;
  return isLocale(lang) ? lang : undefined;
}

let registered = false;

/** Teach Paraglide where the language comes from. `server.ts` calls this by name, before the
 *  first request: a bare `import "./lib/i18n"` there is dropped by the bundler (the package is
 *  `sideEffects: false`), the strategies are then defined only when a route chunk first loads, and
 *  the first visitor of a fresh server gets French whatever their browser says. */
export function registerLocaleStrategies(): void {
  if (registered) return;
  registered = true;

  // Server: the request's Accept-Language. The shared parser keeps the SSR page and
  // the API's own reading of the same header identical (spec 010 §7.4).
  defineCustomServerStrategy(HEADER_STRATEGY, {
    getLocale: (request) => parseAcceptLanguage(request?.headers.get("accept-language")),
  });

  // Client: the signed-in user's language, else what the server rendered.
  defineCustomClientStrategy(ACCOUNT_STRATEGY, {
    getLocale: () => accountLocale() ?? documentLocale(),
    // `setLocale(locale, { reload: false })` lands here: write the cache, React follows.
    setLocale: (locale) => {
      const user = queryClient?.getQueryData<CachedUser>(ME_QUERY_KEY);
      if (user && user.locale !== locale) {
        queryClient?.setQueryData(ME_QUERY_KEY, { ...user, locale });
      }
      if (typeof document !== "undefined" && document.documentElement.lang !== locale) {
        document.documentElement.lang = locale;
        notify();
      }
    },
  });
}

// Any module that uses the language gets the strategies; `server.ts` also asks by name.
registerLocaleStrategies();

/** Call once per QueryClient, on the client: a change to the `me` cache is a change
 *  of language. Returns the unsubscribe function. */
export function bindLocaleToQueryClient(client: QueryClient): () => void {
  queryClient = client;
  return client.getQueryCache().subscribe((event) => {
    if (event.query.queryKey[0] === ME_QUERY_KEY[0]) notify();
  });
}

/** Forget the bound client. The app binds one for its lifetime; tests bind one per mounted
 *  screen and call this between tests, or the last one's signed-in user outvotes `<html lang>`. */
export function unbindLocale(): void {
  queryClient = undefined;
}

/** Back to the browser's language: after a sign-out or a dead session, nobody's
 *  stored preference applies any more. Call it *after* the `me` cache is cleared: while a
 *  user is cached, the account's language wins over `<html lang>`. */
export function resetLocale(): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = matchLocale(
    typeof navigator === "undefined" ? [] : (navigator.languages ?? []),
  );
  notify();
}

/** Re-renders the caller when the language changes. */
export function useLocale(): Locale {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => getLocale(),
    () => getLocale(),
  );
}
