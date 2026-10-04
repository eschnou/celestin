/** The administrator's dashboard (spec 012): the accounts, enabling and disabling one, resetting a
 *  password. Every route here answers `403` to anyone but an admin. */

import { keepPreviousData, queryOptions, type QueryClient } from "@tanstack/react-query";
import type { Role, RegistrationMode } from "./auth";
import type { Locale } from "./locale";
import { getJson, sendJson } from "./tutor/client";
import { invalidateHealth } from "./tutor/health";

export type AdminUser = {
  id: string;
  email: string;
  name: string;
  role: Role;
  locale: Locale;
  enabled: boolean;
  created_at: string;
  last_seen_at: string | null;
};

export type UserStatus = "all" | "enabled" | "disabled";
export type UsersFilter = { q: string; status: UserStatus; offset: number };
export const PAGE_SIZE = 25;

export type UserList = {
  users: AdminUser[];
  /** How many match the filter, for paging. */
  total: number;
  /** The whole table, for the filter tabs. */
  counts: { total: number; enabled: number; disabled: number };
  registration_mode: RegistrationMode;
};

export const ADMIN_USERS_KEY = ["admin", "users"] as const;

export const adminUsersQuery = (filter: UsersFilter) =>
  queryOptions({
    queryKey: [...ADMIN_USERS_KEY, filter] as const,
    queryFn: () => {
      const params = new URLSearchParams({
        status: filter.status,
        limit: String(PAGE_SIZE),
        offset: String(filter.offset),
      });
      if (filter.q.trim()) params.set("q", filter.q.trim());
      return getJson<UserList>(`/api/admin/users?${params}`);
    },
    // Typing in the search box must not blank the table between keystrokes.
    placeholderData: keepPreviousData,
  });

export async function setUserEnabled(id: string, enabled: boolean): Promise<AdminUser> {
  const response = await sendJson(`/api/admin/users/${id}`, { enabled }, { method: "PATCH" });
  return ((await response.json()) as { user: AdminUser }).user;
}

/** The new password is in this answer and nowhere else: it is shown once and never stored. */
export async function resetUserPassword(
  id: string,
): Promise<{ user: AdminUser; password: string }> {
  const response = await sendJson(`/api/admin/users/${id}/reset-password`);
  return (await response.json()) as { user: AdminUser; password: string };
}

// ---------------------------------------------------------------- the AI provider (specs 013, 014)

export type ModelRole = "tutor" | "authoring" | "transcription" | "voice";
export const MODEL_ROLES: ModelRole[] = ["tutor", "authoring", "transcription", "voice"];
export type AiSlot = "default" | ModelRole;
export type ApiStyle = "responses" | "chat";
export type StructuredMode = "schema" | "json";
export type Effort = "low" | "medium" | "high";
/** Where a value comes from: the server's environment (read-only here), what an administrator stored, or
 *  the built-in default. */
export type Source = "environment" | "stored" | "default";
export type Field<T> = { value: T; source: Source };
/** Which key is in force and where it comes from. Never the key: at most its last four characters. */
export type KeyView = {
  source: "environment" | "stored" | "none";
  last4: string | null;
  unreadable: boolean;
};
export type ConnectionView = {
  base_url: Field<string | null>;
  api_style: Field<ApiStyle>;
  structured: Field<StructuredMode>;
  key: KeyView;
};
export type RoleView = {
  model: Field<string | null>;
  /** `value: null` is « not sent ». */
  reasoning_effort: Field<Effort | null>;
  voice_transcription_model: Field<string | null> | null;
  own_connection: ConnectionView | null;
  uses_default: boolean;
  /** The role has a model and a usable connection. */
  resolved: boolean;
};
export type AiSettingsView = {
  can_store: boolean;
  configured: boolean;
  voice_available: boolean;
  default: ConnectionView;
  roles: Record<ModelRole, RoleView>;
};

export type ConnectionInput = {
  base_url: string;
  api_style: ApiStyle;
  structured: StructuredMode;
  /** A new key, or null to keep the stored one. */
  api_key: string | null;
  clear_key: boolean;
};
export type RoleInput = {
  /** null: the built-in default. */
  model: string | null;
  /** null: the built-in default; "": not sent. */
  reasoning_effort: Effort | "" | null;
  voice_transcription_model?: string | null;
  /** null: the role uses the default connection. */
  connection: ConnectionInput | null;
};
export type SaveAiSettings = {
  default: ConnectionInput;
  roles: Partial<Record<ModelRole, RoleInput>>;
};

export type LiveCode =
  | "rejected"
  | "unreachable"
  | "model_not_found"
  | "no_tool_calls"
  | "tool_arguments"
  | "no_image_input"
  | "schema_unsupported"
  | "other";
export type AiTest = {
  roles: {
    role: ModelRole;
    connection: "ok" | "rejected" | "unreachable";
    /** The server authenticates but cannot list models: the availability is unknown. */
    limited: boolean;
    model_visible: boolean | null;
    live: { status: "ok" | "failed"; code: LiveCode | null } | null;
  }[];
};
export type ModelListing = {
  status: "ok" | "rejected" | "unreachable";
  ids: string[];
  limited: boolean;
};

const AI_URL = "/api/admin/ai";
export const AI_KEY = ["admin", "ai"] as const;

export const aiSettingsQuery = queryOptions({
  queryKey: AI_KEY,
  queryFn: () => getJson<AiSettingsView>(AI_URL),
  staleTime: 0,
});

export async function saveAiSettings(request: SaveAiSettings): Promise<AiSettingsView> {
  const response = await sendJson(AI_URL, request, { method: "PUT" });
  return (await response.json()) as AiSettingsView;
}

/** The model ids a slot's saved connection lists, as suggestions. */
export function aiModels(slot: AiSlot): Promise<ModelListing> {
  return getJson<ModelListing>(`${AI_URL}/models?slot=${slot}`);
}

export async function testAi(live = false): Promise<AiTest> {
  const response = await sendJson(`${AI_URL}/test`, { live });
  return (await response.json()) as AiTest;
}

/** After a save: the server answered with the new state, so the section takes it as it is (no second
 *  read), and the dashboard's banner and the mic read the health again. */
export function afterAiChange(queryClient: QueryClient, view: AiSettingsView): Promise<void> {
  queryClient.setQueryData(AI_KEY, view);
  return invalidateHealth(queryClient);
}
