import { createFileRoute, getRouteApi, Link } from "@tanstack/react-router";
import { AuthPage } from "@/components/celestin/app-bar";
import { AiBanner } from "@/components/celestin/admin/ai-banner";
import { UsersPanel } from "@/components/celestin/admin/users-panel";
import { muted } from "@/components/celestin/styles";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/admin/")({
  head: () => ({ meta: [{ title: m.admin_head_title() }] }),
  component: AdminPage,
});

function AdminPage() {
  const { user } = authRoute.useRouteContext();
  return (
    <AuthPage user={user} wide>
      <h1 className="text-xl font-bold">{m.admin_title()}</h1>
      <p className={muted}>{m.admin_subtitle()}</p>
      <AiBanner />
      <p className="mt-4">
        <Link to="/admin/usage" className="font-semibold text-primary hover:underline">
          {m.usage_link()}
        </Link>
        <span className={muted}> — {m.usage_link_help()}</span>
      </p>
      <UsersPanel me={user} />
    </AuthPage>
  );
}
