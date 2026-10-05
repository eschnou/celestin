import { createFileRoute, getRouteApi, Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback, useMemo } from "react";
import { UsagePanel } from "@/components/celestin/admin/usage-panel";
import { AuthPage } from "@/components/celestin/app-bar";
import { muted } from "@/components/celestin/styles";
import { parseUsageSearch, searchParams, type UsageSearch } from "@/lib/admin-usage";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/admin/usage")({
  head: () => ({ meta: [{ title: m.usage_head_title() }] }),
  // The page's state is its address, and only what differs from the defaults is in it: a link to the page needs
  // no search, and an unknown value is the default.
  validateSearch: (raw: Record<string, unknown>): Partial<UsageSearch> =>
    searchParams(parseUsageSearch(raw)),
  component: UsagePage,
});

function UsagePage() {
  const { user } = authRoute.useRouteContext();
  const navigate = useNavigate();
  const raw = useSearch({ strict: false }) as Record<string, unknown>;
  const search: UsageSearch = useMemo(() => parseUsageSearch(raw), [raw]);
  const change = useCallback(
    (patch: Partial<UsageSearch>) =>
      void navigate({
        to: "/admin/usage",
        search: searchParams({ ...search, ...patch }),
        // Typing in a search box is not a place to come back to.
        replace: patch.q !== undefined,
      }),
    [navigate, search],
  );
  return (
    <AuthPage user={user} wide>
      <Link to="/admin" className="text-sm font-semibold text-primary hover:underline">
        ← {m.usage_back()}
      </Link>
      <h1 className="mt-2 text-xl font-bold">{m.usage_title()}</h1>
      <p className={muted}>{m.usage_subtitle()}</p>
      <UsagePanel search={search} onChange={change} />
    </AuthPage>
  );
}
