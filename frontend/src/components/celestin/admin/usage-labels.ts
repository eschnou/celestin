/** The words for the ledger's closed vocabularies: tables of message functions, never called at import (the
 *  language is the request's). The raw values are the database's, not what the administrator reads. */

import type { UsageFeature, UsageRole, UsageStatus, UsageTotals } from "@/lib/admin-usage";
import { formatCost, formatCount } from "@/lib/i18n-format";
import { m } from "@/paraglide/messages";

export const ROLE_LABEL: Record<UsageRole, () => string> = {
  tutor: m.usage_role_tutor,
  authoring: m.usage_role_authoring,
  transcription: m.usage_role_transcription,
  voice: m.usage_role_voice,
};

export const FEATURE_LABEL: Record<UsageFeature, () => string> = {
  tutor_turn: m.usage_feature_tutor_turn,
  discussion_turn: m.usage_feature_discussion_turn,
  authoring: m.usage_feature_authoring,
  document_reading: m.usage_feature_document_reading,
  work_reading: m.usage_feature_work_reading,
  dictation: m.usage_feature_dictation,
  voice_session: m.usage_feature_voice_session,
  ai_test: m.usage_feature_ai_test,
};

export const STATUS_LABEL: Record<UsageStatus, () => string> = {
  ok: m.usage_status_ok,
  failed: m.usage_status_failed,
  truncated: m.usage_status_truncated,
  cancelled: m.usage_status_cancelled,
};

/** What a cost cell says: the figure the provider reported, or a dash. Never a zero it did not say. */
export function costOf(totals: Pick<UsageTotals, "cost_usd">): string {
  return totals.cost_usd === null ? "—" : formatCost(totals.cost_usd);
}

/** « Calls with a cost reported by the provider: 2 of 5. » */
export function coverageText(totals: Pick<UsageTotals, "costed_calls" | "calls">): string {
  return m.usage_cost_coverage({
    costed: formatCount(totals.costed_calls),
    calls: formatCount(totals.calls),
  });
}
