/** Who is signed in (004 design 3.10). The cookie does the work; this module
 *  only asks the backend and remembers the answer in the query cache. */

import { queryOptions, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { redirect, useRouter } from "@tanstack/react-router";
import { useCallback } from "react";
import { resetLocale } from "./i18n";
import type { Locale } from "./locale";
import { ME_QUERY_KEY } from "./me-key";
import { ApiError, getJson, sendJson } from "./tutor/client";

export type Role = "student" | "parent" | "admin";
export type User = { id: string; email: string; name: string; role: Role; locale: Locale };

export const ME_URL = "/api/auth/me";
export const LOGIN_URL = "/api/auth/login";
export const REGISTER_URL = "/api/auth/register";
export const LOGOUT_URL = "/api/auth/logout";
export const AUTH_CONFIG_URL = "/api/auth/config";
export const SETUP_URL = "/api/setup";
export const PASSWORD_URL = "/api/auth/password";

/** Who may create an account (spec 012): anyone, nobody, or anyone but an admin enables the
 *  account before its first sign-in. */
export type RegistrationMode = "open" | "closed" | "verification";

/** Where a user lands: the administrator's dashboard, or the student's courses. */
export const homePath = (user: Pick<User, "role">): "/admin" | "/courses" =>
  user.role === "admin" ? "/admin" : "/courses";

export const isAdminPath = (pathname: string): boolean =>
  pathname === "/admin" || pathname.startsWith("/admin/");

export { ApiError as AuthError };

/** `null` means "nobody": a 401 is an answer, not a failure. */
export async function fetchMe(): Promise<User | null> {
  try {
    return (await getJson<{ user: User }>(ME_URL)).user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export const meQuery = queryOptions({
  queryKey: ME_QUERY_KEY,
  queryFn: fetchMe,
  staleTime: Infinity,
  retry: false,
});

async function signedIn(response: Response): Promise<User> {
  return ((await response.json()) as { user: User }).user;
}

export async function login(email: string, password: string): Promise<User> {
  return signedIn(await sendJson(LOGIN_URL, { email, password }));
}

/** `signed_in`: the account is open and so is the session. `pending`: the account exists but an
 *  administrator has to enable it (verification mode); there is no session. */
export type Registered = { status: "signed_in" | "pending"; user: User };

export async function register(email: string, password: string, name: string): Promise<Registered> {
  const response = await sendJson(REGISTER_URL, { email, password, name });
  return {
    status: response.status === 202 ? "pending" : "signed_in",
    user: await signedIn(response),
  };
}

/** What the signed-out pages need: whether to offer registration, and whether the instance still waits
 *  for its first administrator (spec 013), in which case they lead to `/setup`. */
export type AuthConfig = { registration: RegistrationMode; setupRequired: boolean };

/** Public: the sign-in, registration and setup pages ask what to offer. */
export const authConfigQuery = queryOptions({
  queryKey: ["auth-config"] as const,
  queryFn: async (): Promise<AuthConfig> => {
    const body = await getJson<{ registration: RegistrationMode; setup_required?: boolean }>(
      AUTH_CONFIG_URL,
    );
    return { registration: body.registration, setupRequired: body.setup_required === true };
  },
  staleTime: 60_000,
  retry: false,
});

/** The first administrator of a fresh instance, signed in by the answer. */
export async function setupAdmin(email: string, password: string, name: string): Promise<User> {
  return signedIn(await sendJson(SETUP_URL, { email, password, name }));
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await sendJson(PASSWORD_URL, { current_password: currentPassword, new_password: newPassword });
}

export async function logout(): Promise<void> {
  await sendJson(LOGOUT_URL);
}

/** Only same-site paths are followed after sign-in, never a foreign URL. */
export function safeRedirect(target: string | undefined): string {
  return target && target.startsWith("/") && !target.startsWith("//") ? target : "/courses";
}

export type RedirectSearch = { redirect?: string };

/** The `?redirect=` of the sign-in and registration pages. */
export function redirectSearch(search: Record<string, unknown>): RedirectSearch {
  return typeof search["redirect"] === "string" ? { redirect: search["redirect"] } : {};
}

/** The guard of the authenticated layout: the user, or a redirect to sign-in
 *  that remembers where she was going. */
export async function requireUser(queryClient: QueryClient, href: string): Promise<User> {
  const user = await queryClient.ensureQueryData(meQuery);
  if (!user) {
    // Nobody's stored language applies any more (a dead session lands here too).
    resetLocale();
    throw redirect({ to: "/login", search: { redirect: href } });
  }
  return user;
}

/** What both auth pages do once the server said yes. */
export function useAfterSignIn(redirectTo: string | undefined): (user: User) => void {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useCallback(
    (user: User) => {
      queryClient.setQueryData(meQuery.queryKey, user);
      router.history.push(safeRedirect(redirectTo));
    },
    [queryClient, redirectTo, router],
  );
}

/** Sign out, forget everything cached, land on sign-in. */
export function useSignOut(): () => Promise<void> {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useCallback(async () => {
    try {
      await logout();
    } finally {
      queryClient.clear();
      // Nobody's stored language applies any more: back to the browser's.
      resetLocale();
      await router.navigate({ to: "/login" });
    }
  }, [queryClient, router]);
}
