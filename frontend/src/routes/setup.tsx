import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useState } from "react";
import { SetupForm } from "@/components/celestin/auth-forms";
import { authConfigQuery, useAfterSignIn, type User } from "@/lib/auth";
import { invalidateHealth } from "@/lib/tutor/health";
import { m } from "@/paraglide/messages";
import { AuthShell } from "./login";

/** The first run (spec 013): a fresh instance has no account, and its first visitor creates the
 *  administrator. Public and server-rendered like `/register`; once an account exists there is
 *  nothing to do here and the page leads to sign-in. */
export const Route = createFileRoute("/setup")({
  head: () => ({ meta: [{ title: m.setup_head_title() }] }),
  component: SetupPage,
});

function SetupPage() {
  const queryClient = useQueryClient();
  const signedIn = useAfterSignIn("/admin");
  const config = useQuery(authConfigQuery);
  // Once the administrator exists the config says « nothing to set up » too: that must not send the
  // new administrator to sign-in on the way to the dashboard.
  const [done, setDone] = useState(false);

  // Nothing to set up (or the server says so): sign in. A failed lookup still shows the form, as the
  // registration page does: the server decides, and refuses with `setup_done` if it is too late.
  if (!done && config.data && !config.data.setupRequired) return <Navigate to="/login" replace />;

  const onSuccess = (user: User) => {
    setDone(true);
    // The instance no longer waits (no refetch needed to know it), and has no key yet: the dashboard's
    // banner reads the health.
    queryClient.setQueryData(authConfigQuery.queryKey, (config) =>
      config ? { ...config, setupRequired: false } : config,
    );
    void invalidateHealth(queryClient);
    signedIn(user); // caches the user and goes to the dashboard
  };

  return (
    <AuthShell title={m.setup_title()} subtitle={m.setup_subtitle()}>
      {config.isPending ? null : <SetupForm onSuccess={onSuccess} />}
    </AuthShell>
  );
}
