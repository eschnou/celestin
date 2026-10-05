/** The administrator's view of the AI usage ledger (spec 015): totals, per user, per call. Read-only.
 *  A cost is the provider's own figure or nothing: `cost_usd` is `null` when none was reported, and is
 *  never shown as zero. */

import { keepPreviousData, queryOptions } from "@tanstack/react-query";
import { MODEL_ROLES, type AdminUser, type ModelRole } from "./admin";
import { getJson } from "./tutor/client";

export type UsageRole = ModelRole;
export const USAGE_ROLES = MODEL_ROLES;
export const USAGE_FEATURES = [
  "tutor_turn",
  "discussion_turn",
  "authoring",
  "document_reading",
  "work_reading",
  "dictation",
  "voice_session",
  "ai_test",
] as const;
export type UsageFeature = (typeof USAGE_FEATURES)[number];
export const USAGE_STATUSES = ["ok", "failed", "truncated", "cancelled"] as const;
export type UsageStatus = (typeof USAGE_STATUSES)[number];

export type UsageTotals = {
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  /** The sum of the costs providers reported, in USD; `null` when no call reported one. */
  cost_usd: number | null;
  /** How many of `calls` reported a cost. */
  costed_calls: number;
};

export type UsageSummary = { totals: UsageTotals; models: string[] };
export type UserUsage = UsageTotals & {
  user_id: string;
  name: string;
  email: string;
  enabled: boolean;
};
export type UserUsageList = { users: UserUsage[]; total: number };
export type UserUsageDetail = {
  user: AdminUser;
  totals: UsageTotals;
  by_role: (UsageTotals & { role: UsageRole })[];
  by_model: (UsageTotals & { model: string; provider: string })[];
};
export type UsageCall = {
  id: number;
  created_at: string;
  user_id: string;
  user_name: string;
  user_email: string;
  course_id: string | null;
  chapter_id: string | null;
  course_subject: string | null;
  course_language: string | null;
  correlation_id: string | null;
  role: UsageRole;
  feature: UsageFeature;
  model: string;
  provider: string;
  status: UsageStatus;
  error_code: string | null;
  latency_ms: number | null;
  ttft_ms: number | null;
  input_tokens: number | null;
  cached_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  input_audio_tokens: number | null;
  output_audio_tokens: number | null;
  audio_seconds: number | null;
  cost_usd: number | null;
};
export type UsageCallList = { calls: UsageCall[]; has_more: boolean };

export const USERS_PAGE_SIZE = 25;
export const CALLS_PAGE_SIZE = 50;

// ------------------------------------------------------------------ what the page's address says

export const PERIODS = ["today", "7d", "30d", "all", "custom"] as const;
export type PeriodId = (typeof PERIODS)[number];
export const USER_ORDERS = ["calls", "input_tokens", "output_tokens", "cost", "name"] as const;
export type UserOrder = (typeof USER_ORDERS)[number];
export const USAGE_VIEWS = ["users", "calls"] as const;
export type UsageView = (typeof USAGE_VIEWS)[number];

export type UsageSearch = {
  view: UsageView;
  period: PeriodId;
  /** `YYYY-MM-DD`, local days: the custom period, both ends included. */
  from: string;
  to: string;
  q: string;
  order: UserOrder;
  desc: boolean;
  page: number;
  user: string;
  /** The user's name, for the chip that says whose calls these are. Display only. */
  uname: string;
  role: UsageRole | "";
  feature: UsageFeature | "";
  model: string;
  status: UsageStatus | "";
  correlation: string;
};

export const DEFAULT_SEARCH: UsageSearch = {
  view: "users",
  period: "30d",
  from: "",
  to: "",
  q: "",
  order: "calls",
  desc: true,
  page: 0,
  user: "",
  uname: "",
  role: "",
  feature: "",
  model: "",
  status: "",
  correlation: "",
};

const oneOf = <T extends string>(allowed: readonly T[], value: unknown, fallback: T): T =>
  typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
const text = (value: unknown, max: number): string =>
  typeof value === "string" ? value.slice(0, max) : "";
const day = (value: unknown): string =>
  typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))
    ? value
    : "";

/** The page's search parameters, whatever the address held: an unknown value is the default. */
export function parseUsageSearch(raw: Record<string, unknown>): UsageSearch {
  const page = Number(raw["page"]);
  return {
    view: oneOf(USAGE_VIEWS, raw["view"], DEFAULT_SEARCH.view),
    period: oneOf(PERIODS, raw["period"], DEFAULT_SEARCH.period),
    from: day(raw["from"]),
    to: day(raw["to"]),
    q: text(raw["q"], 100),
    order: oneOf(USER_ORDERS, raw["order"], DEFAULT_SEARCH.order),
    desc: raw["desc"] !== false && raw["desc"] !== "false",
    page: Number.isInteger(page) && page > 0 ? page : 0,
    user: text(raw["user"], 32),
    uname: text(raw["uname"], 100),
    role: oneOf(["", ...USAGE_ROLES], raw["role"], ""),
    feature: oneOf(["", ...USAGE_FEATURES], raw["feature"], ""),
    model: text(raw["model"], 200),
    status: oneOf(["", ...USAGE_STATUSES], raw["status"], ""),
    correlation: text(raw["correlation"], 32),
  };
}

/** Only what differs from the defaults, so the address stays short. */
export function searchParams(search: UsageSearch): Partial<UsageSearch> {
  const out: Partial<UsageSearch> = {};
  for (const key of Object.keys(DEFAULT_SEARCH) as (keyof UsageSearch)[]) {
    if (search[key] !== DEFAULT_SEARCH[key]) (out as Record<string, unknown>)[key] = search[key];
  }
  return out;
}

/** A span as the server takes it: instants with an offset, `since` included, `until` excluded. */
export type Range = { since?: string; until?: string };

const startOfDay = (date: Date): Date =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate());
/** A local `YYYY-MM-DD` as local midnight. */
const localDay = (value: string): Date => {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
};

/** The span of a period, from local calendar days for « today » and the custom range, and from `now` for the
 *  rolling ones. « All » has no ends. A custom range whose end is not after its start is read as open-ended. */
export function periodRange(period: PeriodId, from: string, to: string, now: Date): Range {
  switch (period) {
    case "today":
      return { since: startOfDay(now).toISOString() };
    case "7d":
      return { since: new Date(now.getTime() - 7 * 86_400_000).toISOString() };
    case "30d":
      return { since: new Date(now.getTime() - 30 * 86_400_000).toISOString() };
    case "all":
      return {};
    case "custom": {
      const since = from ? localDay(from) : null;
      const end = to ? localDay(to) : null;
      const until = end ? new Date(end.getFullYear(), end.getMonth(), end.getDate() + 1) : null;
      const range: Range = {};
      if (since) range.since = since.toISOString();
      if (until && (!since || until > since)) range.until = until.toISOString();
      return range;
    }
  }
}

// ------------------------------------------------------------------ the queries

export const ADMIN_USAGE_KEY = ["admin", "usage"] as const;

function params(range: Range, extra: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  if (range.since) query.set("since", range.since);
  if (range.until) query.set("until", range.until);
  for (const [key, value] of Object.entries(extra)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

export const usageSummaryQuery = (range: Range) =>
  queryOptions({
    queryKey: [...ADMIN_USAGE_KEY, "summary", range] as const,
    queryFn: () => getJson<UsageSummary>(`/api/admin/usage/summary${params(range, {})}`),
    placeholderData: keepPreviousData,
  });

export const usageUsersQuery = (
  range: Range,
  { q, order, desc, page }: Pick<UsageSearch, "q" | "order" | "desc" | "page">,
) =>
  queryOptions({
    // Only what the request carries is in the key: switching view and back is a cache hit.
    queryKey: [...ADMIN_USAGE_KEY, "users", range, { q, order, desc, page }] as const,
    queryFn: () =>
      getJson<UserUsageList>(
        `/api/admin/usage/users${params(range, {
          q: q.trim(),
          order,
          direction: desc ? "desc" : "asc",
          limit: USERS_PAGE_SIZE,
          offset: page * USERS_PAGE_SIZE,
        })}`,
      ),
    // Typing in the search box must not blank the table between keystrokes.
    placeholderData: keepPreviousData,
  });

export const usageDetailQuery = (userId: string, range: Range) =>
  queryOptions({
    queryKey: [...ADMIN_USAGE_KEY, "detail", userId, range] as const,
    queryFn: () =>
      getJson<UserUsageDetail>(
        `/api/admin/usage/users/${encodeURIComponent(userId)}${params(range, {})}`,
      ),
  });

export const usageCallsQuery = (
  range: Range,
  {
    user,
    role,
    feature,
    model,
    status,
    correlation,
    page,
  }: Pick<UsageSearch, "user" | "role" | "feature" | "model" | "status" | "correlation" | "page">,
) =>
  queryOptions({
    queryKey: [
      ...ADMIN_USAGE_KEY,
      "calls",
      range,
      { user, role, feature, model, status, correlation, page },
    ] as const,
    queryFn: () =>
      getJson<UsageCallList>(
        `/api/admin/usage/calls${params(range, {
          user_id: user,
          role,
          feature,
          model,
          status,
          correlation_id: correlation,
          limit: CALLS_PAGE_SIZE,
          offset: page * CALLS_PAGE_SIZE,
        })}`,
      ),
    placeholderData: keepPreviousData,
  });
