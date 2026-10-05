/** The ledger, call by call (spec 015 R6.5): filters, a table, and « next » driven by `has_more`. */

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { FEATURE_LABEL, ROLE_LABEL, STATUS_LABEL } from "@/components/celestin/admin/usage-labels";
import { Loading } from "@/components/celestin/admin/usage-loading";
import type { Change } from "@/components/celestin/admin/usage-panel";
import { Pager } from "@/components/celestin/pager";
import { field, muted, secondary } from "@/components/celestin/styles";
import { useDebouncedApply } from "@/hooks/use-debounced-apply";
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
  DEFAULT_SEARCH,
  USAGE_FEATURES,
  USAGE_ROLES,
  USAGE_STATUSES,
  usageCallsQuery,
  usageSummaryQuery,
  type Range,
  type UsageCall,
  type UsageSearch,
} from "@/lib/admin-usage";
import { formatCost, formatCount, formatDateTime, formatDurationMs } from "@/lib/i18n-format";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

const FILTERS = ["role", "feature", "model", "status", "correlation", "user"] as const;
const dash = (value: number | null, format: (n: number) => string = formatCount): string =>
  value === null ? "—" : format(value);

export function UsageCalls({
  range,
  search,
  onChange,
}: {
  range: Range;
  search: UsageSearch;
  onChange: Change;
}) {
  const calls = useQuery(usageCallsQuery(range, search));
  // The models seen in the period, for the model filter: the summary's query, already in the cache.
  const models = useQuery(usageSummaryQuery(range)).data?.models ?? [];
  const data = calls.data;
  const filtered = FILTERS.some((key) => search[key] !== DEFAULT_SEARCH[key]);

  return (
    <div className="mt-4">
      <div
        role="group"
        aria-label={m.usage_filter_label()}
        className="flex flex-wrap items-end gap-3"
      >
        <Pick
          label={m.usage_filter_role()}
          value={search.role}
          onChange={(role) => onChange({ role: role as UsageSearch["role"], page: 0 })}
          options={USAGE_ROLES.map((value) => ({ value, label: ROLE_LABEL[value]() }))}
        />
        <Pick
          label={m.usage_filter_feature()}
          value={search.feature}
          onChange={(feature) => onChange({ feature: feature as UsageSearch["feature"], page: 0 })}
          options={USAGE_FEATURES.map((value) => ({ value, label: FEATURE_LABEL[value]() }))}
        />
        <Pick
          label={m.usage_filter_model()}
          value={search.model}
          onChange={(model) => onChange({ model, page: 0 })}
          options={[...new Set([...models, ...(search.model ? [search.model] : [])])].map(
            (value) => ({
              value,
              label: value,
            }),
          )}
        />
        <Pick
          label={m.usage_filter_status()}
          value={search.status}
          onChange={(status) => onChange({ status: status as UsageSearch["status"], page: 0 })}
          options={USAGE_STATUSES.map((value) => ({ value, label: STATUS_LABEL[value]() }))}
        />
        <GroupFilter
          value={search.correlation}
          onApply={(correlation) => onChange({ correlation, page: 0 })}
        />
        {search.user && (
          <Badge variant="secondary" className="gap-1.5 py-1">
            {m.usage_filter_user_chip({ name: search.uname || search.user })}
            <button
              type="button"
              aria-label={m.usage_filter_user_clear()}
              onClick={() => onChange({ user: "", uname: "", page: 0 })}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </Badge>
        )}
        {filtered && (
          <button
            type="button"
            className={secondary}
            onClick={() =>
              onChange({
                role: "",
                feature: "",
                model: "",
                status: "",
                correlation: "",
                user: "",
                uname: "",
                page: 0,
              })
            }
          >
            {m.usage_filter_clear()}
          </button>
        )}
      </div>

      {calls.isPending && <Loading />}
      {calls.isError && !data ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {m.usage_failed()}
        </p>
      ) : (
        <div className={cn("mt-4 overflow-x-auto", calls.isPlaceholderData && "opacity-60")}>
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  m.usage_col_time,
                  m.usage_col_user,
                  m.usage_col_role,
                  m.usage_col_feature,
                  m.usage_col_model,
                  m.usage_col_provider,
                  m.usage_col_status,
                  m.usage_col_latency,
                  m.usage_col_ttft,
                  m.usage_col_input,
                  m.usage_col_cached,
                  m.usage_col_output,
                  m.usage_col_reasoning,
                  m.usage_col_audio,
                  m.usage_col_cost,
                  m.usage_col_group,
                ].map((label, index) => (
                  <TableHead key={index} className="whitespace-nowrap">
                    {label()}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.calls.map((call) => (
                <CallRow
                  key={call.id}
                  call={call}
                  onGroup={(correlation) => onChange({ correlation, page: 0 })}
                />
              ))}
            </TableBody>
          </Table>
          {data && data.calls.length === 0 && (
            <p className={cn(muted, "py-6 text-center")}>{m.usage_calls_empty()}</p>
          )}
        </div>
      )}

      {data && (search.page > 0 || data.has_more) && (
        <Pager
          label={m.usage_page({ page: formatCount(search.page + 1) })}
          hasPrev={search.page > 0}
          hasNext={data.has_more}
          onPrev={() => onChange({ page: search.page - 1 })}
          onNext={() => onChange({ page: search.page + 1 })}
        />
      )}
    </div>
  );
}

function Pick({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="grid gap-1 text-sm font-semibold">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(field, "w-auto font-normal")}
      >
        <option value="">{m.usage_filter_any()}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** A group id is typed or pasted: it applies after a pause, like the search of the accounts. */
function GroupFilter({ value, onApply }: { value: string; onApply: (value: string) => void }) {
  const [typed, setTyped] = useState(value);
  useEffect(() => setTyped(value), [value]);
  useDebouncedApply(typed.trim(), value, onApply);
  return (
    <label className="grid gap-1 text-sm font-semibold">
      {m.usage_filter_group()}
      <input
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        maxLength={32}
        className={cn(field, "w-44 font-mono font-normal")}
      />
    </label>
  );
}

function CallRow({ call, onGroup }: { call: UsageCall; onGroup: (id: string) => void }) {
  const audio = call.audio_seconds;
  return (
    <TableRow>
      <TableCell className="whitespace-nowrap">{formatDateTime(call.created_at)}</TableCell>
      <TableCell>
        <div className="font-medium">{call.user_name}</div>
        <div className={cn(muted, "break-all")}>{call.user_email}</div>
      </TableCell>
      <TableCell>{ROLE_LABEL[call.role]()}</TableCell>
      <TableCell>{FEATURE_LABEL[call.feature]()}</TableCell>
      <TableCell className="whitespace-nowrap">{call.model || "—"}</TableCell>
      <TableCell className="whitespace-nowrap">{call.provider || "—"}</TableCell>
      <TableCell>
        <Badge
          variant={
            call.status === "ok"
              ? "secondary"
              : call.status === "failed"
                ? "destructive"
                : "outline"
          }
        >
          {STATUS_LABEL[call.status]()}
        </Badge>
        {call.error_code && <div className={cn(muted, "font-mono")}>{call.error_code}</div>}
      </TableCell>
      <TableCell className="whitespace-nowrap text-right">
        {dash(call.latency_ms, formatDurationMs)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-right">
        {dash(call.ttft_ms, formatDurationMs)}
      </TableCell>
      <TableCell className="text-right">{dash(call.input_tokens)}</TableCell>
      <TableCell className="text-right">{dash(call.cached_tokens)}</TableCell>
      <TableCell className="text-right">{dash(call.output_tokens)}</TableCell>
      <TableCell className="text-right">{dash(call.reasoning_tokens)}</TableCell>
      <TableCell className="whitespace-nowrap text-right">
        {audio === null ? "—" : m.usage_audio_seconds({ seconds: formatCount(Math.round(audio)) })}
      </TableCell>
      <TableCell
        className="whitespace-nowrap text-right"
        title={call.cost_usd === null ? m.usage_cost_unreported() : undefined}
      >
        {dash(call.cost_usd, formatCost)}
      </TableCell>
      <TableCell>
        {call.correlation_id ? (
          <button
            type="button"
            className="font-mono text-xs hover:underline"
            onClick={() => onGroup(call.correlation_id!)}
          >
            {call.correlation_id}
          </button>
        ) : (
          "—"
        )}
      </TableCell>
    </TableRow>
  );
}
