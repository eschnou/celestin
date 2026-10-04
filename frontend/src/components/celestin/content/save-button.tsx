/** Save, with a confirmation first when saving will reset the chapter's progress (005 R5.5). */

import { useState } from "react";
import { ConfirmDialog } from "@/components/celestin/confirm-dialog";
import { primary, secondary } from "@/components/celestin/styles";
import { ApiError, apiMessage, type ContentIssue } from "@/lib/tutor/client";
import { m } from "@/paraglide/messages";

export function SaveButton({
  label,
  confirm,
  disabled,
  onSave,
}: {
  label: string;
  confirm: string | null;
  disabled: boolean;
  onSave: () => void;
}) {
  if (!confirm) {
    return (
      <button type="button" onClick={onSave} disabled={disabled} className={primary}>
        {label}
      </button>
    );
  }
  return (
    <ConfirmDialog
      trigger={
        <button type="button" disabled={disabled} className={primary}>
          {label}
        </button>
      }
      title={m.content_save_confirm_title()}
      description={confirm}
      confirm={m.common_save()}
      onConfirm={onSave}
    />
  );
}

export function StaleNotice({ onReload }: { onReload: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm"
    >
      {m.content_stale()}
      <button
        type="button"
        onClick={onReload}
        className="font-semibold text-primary hover:underline"
      >
        {m.content_reload()}
      </button>
    </div>
  );
}

export function IssueList({ issues }: { issues: { where: string; message: string }[] }) {
  if (issues.length === 0) return null;
  return (
    <ul
      role="alert"
      className="space-y-1 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
    >
      {issues.map((issue, i) => (
        <li key={i}>
          <span className="font-semibold">{issue.where}</span>
          {m.content_issue_separator()}
          {issue.message}
        </li>
      ))}
    </ul>
  );
}

/** What an editor needs to save and to say why a save was refused. */
export function useContentSave() {
  const [issues, setIssues] = useState<ContentIssue[]>([]);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (save: () => Promise<unknown>) => {
    setBusy(true);
    setIssues([]);
    setError(null);
    try {
      await save();
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale_version") setStale(true);
      else if (err instanceof ApiError && err.issues.length) setIssues(err.issues);
      else setError(apiMessage(err, m.content_save_failed()));
    } finally {
      setBusy(false);
    }
  };
  return { run, issues, stale, error, busy };
}

/** The bottom of an editor: why the last save failed, then save and cancel. */
export function EditorFooter({
  label,
  confirm,
  state,
  issues,
  onSave,
  onCancel,
  onReload,
}: {
  label: string;
  confirm: string | null;
  state: ReturnType<typeof useContentSave>;
  issues: ContentIssue[];
  onSave: () => void;
  onCancel: () => void;
  onReload: () => void;
}) {
  return (
    <>
      {state.stale && <StaleNotice onReload={onReload} />}
      <IssueList issues={issues} />
      {state.error && (
        <p role="alert" className="text-sm text-destructive">
          {state.error}
        </p>
      )}
      <div className="flex gap-2">
        <SaveButton
          label={label}
          confirm={confirm}
          disabled={state.busy || state.stale}
          onSave={onSave}
        />
        <button type="button" onClick={onCancel} className={secondary}>
          {m.common_cancel()}
        </button>
      </div>
    </>
  );
}
