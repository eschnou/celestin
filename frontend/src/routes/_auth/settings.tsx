import { createFileRoute, getRouteApi } from "@tanstack/react-router";
import { SettingsPage } from "@/components/celestin/settings/settings-page";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/settings")({
  head: () => ({ meta: [{ title: m.settings_head_title() }] }),
  component: SettingsRoute,
});

function SettingsRoute() {
  const { user } = authRoute.useRouteContext();
  return <SettingsPage user={user} />;
}
