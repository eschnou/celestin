import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { LoginForm } from "@/components/celestin/auth-forms";
import { authConfigQuery, redirectSearch, useAfterSignIn } from "@/lib/auth";
import celestinMark from "@/assets/celestin-mark.svg";
import { APP_NAME } from "@/lib/brand";
import { m } from "@/paraglide/messages";

export const Route = createFileRoute("/login")({
  validateSearch: redirectSearch,
  head: () => ({ meta: [{ title: m.auth_login_head_title() }] }),
  component: LoginPage,
});

function LoginPage() {
  const { redirect } = Route.useSearch();
  const onSuccess = useAfterSignIn(redirect);
  // In closed mode there is no way to register, so no link either (spec 012). Nothing is shown
  // until the server has answered, rather than a link that then disappears.
  const config = useQuery(authConfigQuery);
  // A fresh instance has no account to sign in with: its first visitor sets it up (spec 013).
  if (config.data?.setupRequired) return <Navigate to="/setup" replace />;
  // A failed lookup shows the link too, as the registration page shows its form: the server decides.
  return (
    <AuthShell title={m.auth_login_title()} subtitle={m.auth_login_subtitle()}>
      <LoginForm onSuccess={onSuccess} />
      {!config.isPending && config.data?.registration !== "closed" && (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          {m.auth_no_account()}{" "}
          <Link
            to="/register"
            search={redirect ? { redirect } : {}}
            className="font-semibold text-primary hover:underline"
          >
            {m.auth_create_account()}
          </Link>
        </p>
      )}
    </AuthShell>
  );
}

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4 py-8">
      <div className="w-full max-w-sm rounded-xl border border-border bg-background p-6 shadow-sheet">
        <div className="mb-6 flex items-center gap-3">
          <img src={celestinMark} alt="" className="size-11" />
          <span className="text-2xl font-bold tracking-tight">{APP_NAME}</span>
        </div>
        <h1 className="text-lg font-bold">{title}</h1>
        <p className="mb-6 text-sm text-muted-foreground">{subtitle}</p>
        {children}
      </div>
    </main>
  );
}
