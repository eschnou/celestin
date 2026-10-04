/**
 * The authenticated layout (004 design 3.10). Rendered client-side only, so the
 * guard runs where the cookie is and the SSR shell needs no cookie forwarding.
 */

import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { useEffect } from "react";
import { AuthPage } from "@/components/celestin/app-bar";
import { homePath, isAdminPath, requireUser } from "@/lib/auth";
import { m } from "@/paraglide/messages";

export const Route = createFileRoute("/_auth")({
  ssr: false,
  beforeLoad: async ({ context, location }) => {
    const user = await requireUser(context.queryClient, location.href);
    // An administrator works in the dashboard and the settings; the student's pages are not
    // theirs (the backend refuses them too), and the dashboard is not a student's.
    const settings = location.pathname === "/settings";
    if (user.role === "admin" && !isAdminPath(location.pathname) && !settings) {
      throw redirect({ to: homePath(user) });
    }
    if (user.role !== "admin" && isAdminPath(location.pathname)) {
      throw redirect({ to: homePath(user) });
    }
    return { user };
  },
  component: AuthLayout,
});

/** Progress used to live in the browser (002). One sweep on first visit. */
function forgetLocalProgress(): void {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("celestin.progress.")) localStorage.removeItem(key);
    }
  } catch {
    // storage blocked: nothing to forget
  }
}

function AuthLayout() {
  const { user } = Route.useRouteContext();
  useEffect(forgetLocalProgress, []);
  if (user.role !== "student" && user.role !== "admin") return <NotYetPage />;
  return <Outlet />;
}

function NotYetPage() {
  const { user } = Route.useRouteContext();
  return (
    <AuthPage user={user}>
      <div className="mx-auto max-w-md pt-10 text-center">
        <h1 className="text-xl font-bold">{m.error_not_yet_title()}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {m.error_not_yet_body({ role: user.role })}
        </p>
      </div>
    </AuthPage>
  );
}
