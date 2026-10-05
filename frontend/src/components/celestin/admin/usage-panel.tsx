/** The administrator's view of AI usage (spec 015): a period, the totals for it, then the users or the calls.
 *  The page's state is its address (`UsageSearch`), so a click on a user opens that user's calls and the browser's
 *  back button comes back. A cost is the provider's figure or a dash, never a zero. */

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { UsageCalls } from "@/components/celestin/admin/usage-calls";
import { costOf, coverageText, ROLE_LABEL } from "@/components/celestin/admin/usage-labels";
import { Loading } from "@/components/celestin/admin/usage-loading";
import { Pager } from "@/components/celestin/pager";
import { useDebouncedApply } from "@/hooks/use-debounced-apply";
import { field, muted, panel, secondary } from "@/components/celestin/styles";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PERIODS,
  USAGE_VIEWS,
  periodRange,
  usageDetailQuery,
  usageSummaryQuery,
  usageUsersQuery,
  USERS_PAGE_SIZE,
  type PeriodId,
  type Range,
  type UsageSearch,
  type UsageTotals,
  type UserOrder,
  type UserUsage,
} from "@/lib/admin-usage";
import { formatCount } from "@/lib/i18n-format";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

/** How often an open page re-measures its rolling period. */
const REFRESH_MS = 5 * 60_000;

export type Change = (patch: Partial<UsageSearch>) => void;

const PERIOD_LABEL: Record<PeriodId, () => string> = {
  today: m.usage_period_today,
  "7d": m.usage_period_7d,
  "30d": m.usage_period_30d,
  all: m.usage_period_all,
  custom: m.usage_period_custom,
};

export function UsagePanel({ search, onChange }: { search: UsageSearch; onChange: Change }) {
  // The rolling periods are measured from an anchor, so the queries keep one key between two refreshes. The anchor
  // moves when a period is chosen (again too: that is how to refresh) and every few minutes while the page is open.
  const [anchor, setAnchor] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setAnchor(Date.now()), REFRESH_MS);
    return () => clearInterval(id);
  }, []);
  const range = useMemo(
    () => periodRange(search.period, search.from, search.to, new Date(anchor)),
    [search.period, search.from, search.to, anchor],
  );
  return (
    <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-4">
      <PeriodBar search={search} onChange={onChange} onRefresh={() => setAnchor(Date.now())} />
      <Summary range={range} />
      <section className={panel}>
        <div role="group" aria-label={m.usage_view_label()} className="flex flex-wrap gap-1.5">
          {USAGE_VIEWS.map((view) => (
            <button
              key={view}
              type="button"
              aria-pressed={search.view === view}
              onClick={() => onChange({ view, page: 0 })}
              className={cn(
                secondary,
                search.view === view && "border-primary bg-primary/10 text-primary",
              )}
            >
              {view === "users" ? m.usage_view_users() : m.usage_view_calls()}
            </button>
          ))}
        </div>
        {search.view === "users" ? (
          <UsersView range={range} search={search} onChange={onChange} />
        ) : (
          <UsageCalls range={range} search={search} onChange={onChange} />
        )}
      </section>
    </div>
  );
}

function PeriodBar({
  search,
  onChange,
  onRefresh,
}: {
  search: UsageSearch;
  onChange: Change;
  onRefresh: () => void;
}) {
  return (
    <section className={panel} aria-label={m.usage_period_label()}>
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label={m.usage_period_label()} className="flex flex-wrap gap-1.5">
          {PERIODS.map((period) => (
            <button
              key={period}
              type="button"
              aria-pressed={search.period === period}
              onClick={() => {
                onRefresh();
                onChange({ period, page: 0 });
              }}
              className={cn(
                secondary,
                search.period === period && "border-primary bg-primary/10 text-primary",
              )}
            >
              {PERIOD_LABEL[period]()}
            </button>
          ))}
        </div>
        {search.period === "custom" && (
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-sm">
              {m.usage_period_from()}
              <input
                type="date"
                value={search.from}
                max={search.to || undefined}
                onChange={(event) => onChange({ from: event.target.value, page: 0 })}
                className={cn(field, "w-auto")}
              />
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              {m.usage_period_to()}
              <input
                type="date"
                value={search.to}
                min={search.from || undefined}
                onChange={(event) => onChange({ to: event.target.value, page: 0 })}
                className={cn(field, "w-auto")}
              />
            </label>
          </div>
        )}
      </div>
      {search.period === "custom" && search.from && search.to && search.from > search.to && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {m.usage_period_invalid()}
        </p>
      )}
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-32">
      <dt className={muted}>{label}</dt>
      <dd className="text-lg font-bold">{value}</dd>
      {sub && <dd className={muted}>{sub}</dd>}
    </div>
  );
}

function Summary({ range }: { range: Range }) {
  const summary = useQuery(usageSummaryQuery(range));
  const totals = summary.data?.totals;
  return (
    <section className={panel} aria-label={m.usage_title()}>
      {summary.isPending && <Loading />}
      {summary.isError && !totals ? (
        <p role="alert" className="text-sm text-destructive">
          {m.usage_failed()}
        </p>
      ) : (
        totals && (
          <>
            <dl className="flex flex-wrap gap-x-8 gap-y-3">
              <Stat label={m.usage_sum_calls()} value={formatCount(totals.calls)} />
              <Stat
                label={m.usage_sum_input()}
                value={formatCount(totals.input_tokens)}
                sub={`${m.usage_sum_cached()} : ${formatCount(totals.cached_tokens)}`}
              />
              <Stat
                label={m.usage_sum_output()}
                value={formatCount(totals.output_tokens)}
                sub={`${m.usage_sum_reasoning()} : ${formatCount(totals.reasoning_tokens)}`}
              />
              <Stat label={m.usage_sum_cost()} value={costOf(totals)} />
            </dl>
            {totals.calls > 0 && (
              <p className={cn(muted, "mt-3")}>
                {totals.costed_calls === 0 ? m.usage_cost_none() : coverageText(totals)}
              </p>
            )}
          </>
        )
      )}
    </section>
  );
}

/** The table's columns, in order; the ones with an `order` sort the list. */
const COLUMNS: { order?: UserOrder; label: () => string; numeric: boolean }[] = [
  { order: "name", label: m.usage_col_user, numeric: false },
  { order: "calls", label: m.usage_col_calls, numeric: true },
  { order: "input_tokens", label: m.usage_col_input, numeric: true },
  { label: m.usage_col_cached, numeric: true },
  { order: "output_tokens", label: m.usage_col_output, numeric: true },
  { order: "cost", label: m.usage_col_cost, numeric: true },
];

function UsersView({
  range,
  search,
  onChange,
}: {
  range: Range;
  search: UsageSearch;
  onChange: Change;
}) {
  const [typed, setTyped] = useState(search.q);
  const [open, setOpen] = useState<string | null>(null);
  // The address can change the search under the box (Back, a link): the box follows it.
  useEffect(() => setTyped(search.q), [search.q]);
  // The search waits for a pause in the typing, and starts again from the first page.
  useDebouncedApply(typed, search.q, (q) => onChange({ q, page: 0 }));

  const list = useQuery(usageUsersQuery(range, search));
  const data = list.data;
  const offset = search.page * USERS_PAGE_SIZE;
  const sortBy = (order: UserOrder) =>
    onChange({ order, desc: search.order === order ? !search.desc : order !== "name", page: 0 });

  return (
    <div className="mt-4">
      <input
        type="search"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        aria-label={m.usage_search_label()}
        placeholder={m.usage_search_label()}
        maxLength={100}
        className={cn(field, "w-full sm:w-72")}
      />
      {list.isPending && <Loading />}
      {list.isError && !data ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {m.usage_failed()}
        </p>
      ) : (
        <div className={cn("mt-4 overflow-x-auto", list.isPlaceholderData && "opacity-60")}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                {COLUMNS.map(({ order, label, numeric }) =>
                  order ? (
                    <TableHead
                      key={order}
                      className={numeric ? "text-right" : undefined}
                      aria-sort={
                        search.order === order ? (search.desc ? "descending" : "ascending") : "none"
                      }
                    >
                      <button
                        type="button"
                        onClick={() => sortBy(order)}
                        aria-label={m.usage_sort_by({ column: label() })}
                        className="font-semibold hover:underline"
                      >
                        {label()}
                        {search.order === order && (search.desc ? " ↓" : " ↑")}
                      </button>
                    </TableHead>
                  ) : (
                    <TableHead key="cached" className="text-right">
                      {label()}
                    </TableHead>
                  ),
                )}
                <TableHead className="text-right">{m.usage_col_actions()}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.users.map((user) => (
                <UserRows
                  key={user.user_id}
                  user={user}
                  range={range}
                  expanded={open === user.user_id}
                  onToggle={() => setOpen(open === user.user_id ? null : user.user_id)}
                  onCalls={() =>
                    onChange({ view: "calls", user: user.user_id, uname: user.name, page: 0 })
                  }
                />
              ))}
            </TableBody>
          </Table>
          {data && data.users.length === 0 && (
            <p className={cn(muted, "py-6 text-center")}>{m.usage_users_empty()}</p>
          )}
        </div>
      )}
      {data && data.total > USERS_PAGE_SIZE && (
        <Pager
          label={m.admin_range({
            from: formatCount(offset + 1),
            to: formatCount(Math.min(offset + USERS_PAGE_SIZE, data.total)),
            total: formatCount(data.total),
          })}
          hasPrev={search.page > 0}
          hasNext={offset + USERS_PAGE_SIZE < data.total}
          onPrev={() => onChange({ page: search.page - 1 })}
          onNext={() => onChange({ page: search.page + 1 })}
        />
      )}
    </div>
  );
}

/** « 3/5 »: calls that reported a cost, out of all of them; its title says it in words. */
function Coverage({ totals }: { totals: UsageTotals }) {
  return (
    <span
      className={cn(muted, "ml-1")}
      title={totals.costed_calls === 0 ? m.usage_cost_unreported() : coverageText(totals)}
    >
      {formatCount(totals.costed_calls)}/{formatCount(totals.calls)}
    </span>
  );
}

function UserRows({
  user,
  range,
  expanded,
  onToggle,
  onCalls,
}: {
  user: UserUsage;
  range: Range;
  expanded: boolean;
  onToggle: () => void;
  onCalls: () => void;
}) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <Fragment>
      <TableRow>
        <TableCell>
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={m.usage_expand_label({ name: user.name })}
            onClick={onToggle}
          >
            <Chevron className="size-4" aria-hidden />
          </button>
        </TableCell>
        <TableCell>
          <span className="font-medium">{user.name}</span>{" "}
          {!user.enabled && <Badge variant="destructive">{m.usage_disabled()}</Badge>}
          <div className={cn(muted, "break-all")}>{user.email}</div>
        </TableCell>
        <TableCell className="text-right">{formatCount(user.calls)}</TableCell>
        <TableCell className="text-right">{formatCount(user.input_tokens)}</TableCell>
        <TableCell className="text-right">{formatCount(user.cached_tokens)}</TableCell>
        <TableCell className="text-right">{formatCount(user.output_tokens)}</TableCell>
        <TableCell className="whitespace-nowrap text-right">
          {costOf(user)}
          <Coverage totals={user} />
        </TableCell>
        <TableCell className="text-right">
          <button
            type="button"
            className={secondary}
            aria-label={m.usage_show_calls_label({ name: user.name })}
            onClick={onCalls}
          >
            {m.usage_show_calls()}
          </button>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell />
          <TableCell colSpan={7}>
            <Detail userId={user.user_id} range={range} />
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  );
}

function Detail({ userId, range }: { userId: string; range: Range }) {
  const detail = useQuery(usageDetailQuery(userId, range));
  if (detail.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {m.usage_detail_failed()}
      </p>
    );
  }
  if (!detail.data) return <Loading />;
  const { by_role, by_model } = detail.data;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <h3 className="text-sm font-bold">{m.usage_by_role()}</h3>
        <ul className="mt-1 grid gap-1 text-sm">
          {by_role.map((row) => (
            <li key={row.role}>
              {ROLE_LABEL[row.role]()} · {formatCount(row.calls)} · {formatCount(row.input_tokens)}{" "}
              / {formatCount(row.output_tokens)} · {costOf(row)}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="text-sm font-bold">{m.usage_by_model()}</h3>
        <ul className="mt-1 grid gap-1 text-sm">
          {by_model.map((row) => (
            <li key={`${row.model}|${row.provider}`}>
              {row.model || "—"} <span className={muted}>{row.provider}</span> ·{" "}
              {formatCount(row.calls)} · {formatCount(row.input_tokens)} /{" "}
              {formatCount(row.output_tokens)} · {costOf(row)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
