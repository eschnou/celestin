import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useState } from "react";
import { RegisterForm } from "@/components/celestin/auth-forms";
import { authConfigQuery, redirectSearch, useAfterSignIn } from "@/lib/auth";
import { m } from "@/paraglide/messages";
import { AuthShell } from "./login";

export const Route = createFileRoute("/register")({
  validateSearch: redirectSearch,
  head: () => ({ meta: [{ title: m.auth_register_head_title() }] }),
  component: RegisterPage,
});

function RegisterPage() {
  const { redirect } = Route.useSearch();
  const onSuccess = useAfterSignIn(redirect);
  const config = useQuery(authConfigQuery);
  const [pending, setPending] = useState(false);
  const signIn = (
    <Link
      to="/login"
      search={redirect ? { redirect } : {}}
      className="font-semibold text-primary hover:underline"
    >
      {m.auth_sign_in()}
    </Link>
  );

  // Nobody registers before the first administrator exists (spec 013): set the instance up first.
  if (config.data?.setupRequired) return <Navigate to="/setup" replace />;

  // Registration is closed: say so at the address too, not only by hiding the link.
  if (config.data?.registration === "closed") {
    return (
      <AuthShell
        title={m.auth_registration_closed_title()}
        subtitle={m.auth_registration_closed_body()}
      >
        <p className="text-center text-sm text-muted-foreground">{signIn}</p>
      </AuthShell>
    );
  }

  // Verification mode: the account exists, and nobody is signed in until an admin enables it.
  if (pending) {
    return (
      <AuthShell title={m.auth_pending_title()} subtitle={m.auth_pending_body()}>
        <p className="text-center text-sm">
          <Link to="/login" className="font-semibold text-primary hover:underline">
            {m.auth_back_to_sign_in()}
          </Link>
        </p>
      </AuthShell>
    );
  }

  // The form waits for the answer: a form that turns into "closed" a moment later is worse
  // than a moment of nothing. A failed lookup still shows it; the server decides.
  if (config.isPending) {
    return (
      <AuthShell title={m.auth_register_title()} subtitle={m.auth_register_subtitle()}>
        {null}
      </AuthShell>
    );
  }

  return (
    <AuthShell title={m.auth_register_title()} subtitle={m.auth_register_subtitle()}>
      {config.data?.registration === "verification" && (
        <p className="mb-4 rounded-md border-l-4 border-primary bg-primary/10 px-3 py-2 text-sm">
          {m.auth_register_verification_note()}
        </p>
      )}
      <RegisterForm onSuccess={onSuccess} onPending={() => setPending(true)} />
      <p className="mt-6 text-center text-sm text-muted-foreground">
        {m.auth_have_account()} {signIn}
      </p>
    </AuthShell>
  );
}
