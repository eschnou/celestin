/** Correcting the chapter's text (the transcription of its document) or replacing the document:
 *  a new preparation, the current content kept until it succeeds (005 R5.4, 006 R4, R5). */

import { useState } from "react";
import { field, secondary } from "@/components/celestin/styles";
import { useCourseLanguage } from "@/lib/course-language";
import { MARKER_EXAMPLES } from "@/lib/tutor/transcription-markers";
import { apiMessage } from "@/lib/tutor/client";
import { formatCount } from "@/lib/i18n-format";
import type { ChapterContent, Limits } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { SaveButton } from "./save-button";

export function SourceField({
  id,
  value,
  onChange,
  limits,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  limits: Limits;
}) {
  const language = useCourseLanguage();
  const length = value.trim().length;
  const tooShort = length > 0 && length < limits.chapter_text_min_chars;
  const tooLong = length > limits.chapter_text_max_chars;
  return (
    <div>
      <textarea
        id={id}
        lang={language}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={12}
        className={`${field} font-mono text-xs`}
        aria-describedby={`${id}-count`}
      />
      <p
        id={`${id}-count`}
        className={`mt-1 text-xs ${tooShort || tooLong ? "text-destructive" : "text-muted-foreground"}`}
      >
        {m.content_source_count({ count: length, formatted: formatCount(length) })}
        {tooShort &&
          ` · ${m.content_source_min({ min: formatCount(limits.chapter_text_min_chars) })}`}
        {tooLong &&
          ` · ${m.content_source_max({ max: formatCount(limits.chapter_text_max_chars) })}`}
      </p>
    </div>
  );
}

export function sourceFits(value: string, limits: Limits): boolean {
  const length = value.trim().length;
  return length >= limits.chapter_text_min_chars && length <= limits.chapter_text_max_chars;
}

export function sourceLabel(content: ChapterContent): string {
  return content.source_kind === "document"
    ? m.content_source_label_document()
    : m.content_source_label_text();
}

export function SourceEditor({
  content,
  limits,
  onSave,
  onCancel,
}: {
  content: ChapterContent;
  limits: Limits;
  onSave: (text: string) => Promise<unknown>;
  onCancel: () => void;
}) {
  const language = useCourseLanguage();
  const [text, setText] = useState(content.source_text);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const running = content.authoring_state === "generating";
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSave(text);
    } catch (err) {
      setError(apiMessage(err, m.content_source_start_failed()));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-3">
      <label htmlFor="source-editor" className="block text-sm font-semibold">
        {sourceLabel(content)}
      </label>
      {content.source_kind === "document" && (
        <p className="text-xs text-muted-foreground">
          {m.content_source_hint(MARKER_EXAMPLES[language])}
        </p>
      )}
      <SourceField id="source-editor" value={text} onChange={setText} limits={limits} />
      {running && <p className="text-sm text-muted-foreground">{m.content_source_running()}</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <SaveButton
          label={m.content_submit_again()}
          confirm={m.content_source_warning()}
          disabled={busy || running || !sourceFits(text, limits)}
          onSave={() => void save()}
        />
        <button type="button" onClick={onCancel} className={secondary}>
          {m.common_cancel()}
        </button>
      </div>
    </div>
  );
}
