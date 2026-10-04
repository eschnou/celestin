/** Editing the path section by section (005 R5.3): no YAML, no JSON. */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import { danger, field, fieldError, label, secondary, panel } from "@/components/celestin/styles";
import { useCourseLanguage } from "@/lib/course-language";
import { KIND_LABEL, SECTION_KINDS } from "@/lib/tutor/labels";
import type { ChapterContent, CurriculumIn, SectionKind } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { EditorFooter, IssueList, useContentSave } from "./save-button";

const TEXT_MAX = 600;
const text = (required: string, tooLong: string) =>
  z.string().trim().min(1, required).max(TEXT_MAX, tooLong);
const lines = (value: string) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

// A factory called in render: a message read at import would freeze the language.
const makeSectionSchema = () =>
  z
    .object({
      id: z.string(),
      kind: z.enum(SECTION_KINDS),
      title: text(m.content_title_required(), m.content_title_too_long({ max: TEXT_MAX })),
      goal: text(m.content_goal_required(), m.content_goal_too_long({ max: TEXT_MAX })),
      done_when: text(m.content_done_required(), m.content_done_too_long({ max: TEXT_MAX })),
      pack: z.string(),
      beats: z.string(),
      exercises: z.string(),
      count: z.coerce.number().int().min(1, m.content_count_min()).max(10, m.content_count_max()),
    })
    .superRefine((section, ctx) => {
      if (section.kind === "teach") {
        const beats = lines(section.beats);
        if (beats.length === 0)
          ctx.addIssue({ code: "custom", path: ["beats"], message: m.content_beats_min() });
        if (beats.length > 12)
          ctx.addIssue({ code: "custom", path: ["beats"], message: m.content_beats_max() });
      } else {
        const exercises = lines(section.exercises);
        if (exercises.length === 0)
          ctx.addIssue({ code: "custom", path: ["exercises"], message: m.content_exercises_min() });
        if (exercises.length > 12)
          ctx.addIssue({ code: "custom", path: ["exercises"], message: m.content_exercises_max() });
      }
    });

const makeSchema = () =>
  z.object({
    title: text(m.content_path_title_required(), m.content_path_title_too_long({ max: TEXT_MAX })),
    sections: z
      .array(makeSectionSchema())
      .min(1, m.content_sections_min())
      .max(40, m.content_sections_max()),
  });

type Values = z.infer<ReturnType<typeof makeSchema>>;
type SectionValues = Values["sections"][number];

function newId(): string {
  return `s-${Math.random().toString(36).slice(2, 8).padEnd(6, "0")}`;
}

function toValues(content: ChapterContent): Values {
  const curriculum = content.curriculum!;
  return {
    title: curriculum.title,
    sections: curriculum.sections.map((s) => ({
      id: s.id,
      kind: s.kind,
      title: s.title,
      goal: s.goal,
      done_when: s.done_when,
      pack: s.pack.join("\n"),
      beats: s.beats.join("\n"),
      exercises: s.exercises.join("\n"),
      count: s.count ?? 1,
    })),
  };
}

/** What the API expects: a teach section has no exercises, the others no beats. */
export function toCurriculum(values: Values): CurriculumIn {
  return {
    title: values.title.trim(),
    sections: values.sections.map((s) => {
      const teach = s.kind === "teach";
      return {
        id: s.id,
        kind: s.kind,
        title: s.title.trim(),
        goal: s.goal.trim(),
        done_when: s.done_when.trim(),
        pack: lines(s.pack),
        beats: teach ? lines(s.beats) : [],
        exercises: teach ? [] : lines(s.exercises),
        count: teach ? null : s.count,
      };
    }),
  };
}

const EMPTY: Omit<SectionValues, "id"> = {
  kind: "teach",
  title: "",
  goal: "",
  done_when: "",
  pack: "",
  beats: "",
  exercises: "",
  count: 1,
};

export function CurriculumEditor({
  content,
  onSave,
  onCancel,
  onReload,
}: {
  content: ChapterContent;
  onSave: (curriculum: CurriculumIn) => Promise<unknown>;
  onCancel: () => void;
  onReload: () => void;
}) {
  const language = useCourseLanguage();
  const schema = useMemo(makeSchema, []);
  const form = useForm<Values>({
    resolver: zodResolver(schema) as never,
    defaultValues: toValues(content),
  });
  // `id` is the section's own id: React Hook Form keys its rows under `key` instead.
  const sections = useFieldArray({ control: form.control, name: "sections", keyName: "key" });
  const saving = useContentSave();
  const { errors } = form.formState;
  const submit = form.handleSubmit((values) => saving.run(() => onSave(toCurriculum(values))));
  const { issues } = saving;

  // `where` is a data protocol with the server, not interface text: it names a section as
  // `section « id »` in both languages (backend/app/domain/messages/issues.py).
  /* eslint-disable no-restricted-syntax */
  const issuesFor = (id: string) => issues.filter((issue) => issue.where === `section « ${id} »`);
  const general = issues.filter((issue) => !issue.where.startsWith("section « "));
  /* eslint-enable no-restricted-syntax */

  return (
    <form
      onSubmit={(event) => event.preventDefault()}
      noValidate
      aria-label={m.content_edit_path()}
      className="space-y-4"
    >
      <div>
        <label className={label} htmlFor="curriculum-title">
          {m.content_path_title_label()}
        </label>
        <input
          id="curriculum-title"
          lang={language}
          className={field}
          {...form.register("title")}
        />
        {errors.title && <p className={fieldError}>{errors.title.message}</p>}
      </div>
      <ol className="space-y-3">
        {sections.fields.map((section, index) => {
          const kind = form.watch(`sections.${index}.kind`) as SectionKind;
          const sectionErrors = errors.sections?.[index];
          const prefix = `section-${index}`;
          return (
            <li key={section.key} className={`space-y-3 ${panel}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-muted-foreground">{index + 1}</span>
                <label htmlFor={`${prefix}-kind`} className="sr-only">
                  {m.content_section_kind({ n: index + 1 })}
                </label>
                <select
                  id={`${prefix}-kind`}
                  className={`${field} w-auto`}
                  {...form.register(`sections.${index}.kind`)}
                >
                  {SECTION_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {KIND_LABEL[k]()}
                    </option>
                  ))}
                </select>
                <div className="ml-auto flex gap-1">
                  <button
                    type="button"
                    className={secondary}
                    disabled={index === 0}
                    onClick={() => sections.move(index, index - 1)}
                    aria-label={m.content_section_up({ n: index + 1 })}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className={secondary}
                    disabled={index === sections.fields.length - 1}
                    onClick={() => sections.move(index, index + 1)}
                    aria-label={m.content_section_down({ n: index + 1 })}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className={danger}
                    onClick={() => sections.remove(index)}
                    aria-label={m.content_section_remove({ n: index + 1 })}
                  >
                    {m.common_remove()}
                  </button>
                </div>
              </div>
              <Field
                id={`${prefix}-title`}
                label={m.content_field_title()}
                error={sectionErrors?.title?.message}
              >
                <input
                  id={`${prefix}-title`}
                  className={field}
                  lang={language}
                  {...form.register(`sections.${index}.title`)}
                />
              </Field>
              <Field
                id={`${prefix}-goal`}
                label={m.content_field_goal()}
                error={sectionErrors?.goal?.message}
              >
                <input
                  id={`${prefix}-goal`}
                  className={field}
                  lang={language}
                  {...form.register(`sections.${index}.goal`)}
                />
              </Field>
              {kind === "teach" ? (
                <Field
                  id={`${prefix}-beats`}
                  label={m.content_field_beats()}
                  error={sectionErrors?.beats?.message}
                >
                  <textarea
                    id={`${prefix}-beats`}
                    rows={4}
                    className={field}
                    lang={language}
                    {...form.register(`sections.${index}.beats`)}
                  />
                </Field>
              ) : (
                <>
                  <Field
                    id={`${prefix}-exercises`}
                    label={m.content_field_exercises()}
                    error={sectionErrors?.exercises?.message}
                  >
                    <textarea
                      id={`${prefix}-exercises`}
                      rows={3}
                      className={field}
                      lang={language}
                      {...form.register(`sections.${index}.exercises`)}
                    />
                  </Field>
                  <Field
                    id={`${prefix}-count`}
                    label={m.content_field_count()}
                    error={sectionErrors?.count?.message}
                  >
                    <input
                      id={`${prefix}-count`}
                      type="number"
                      min={1}
                      max={10}
                      className={`${field} w-24`}
                      {...form.register(`sections.${index}.count`)}
                    />
                  </Field>
                </>
              )}
              <Field id={`${prefix}-pack`} label={m.content_field_pack()}>
                <textarea
                  id={`${prefix}-pack`}
                  rows={2}
                  className={field}
                  lang={language}
                  {...form.register(`sections.${index}.pack`)}
                />
              </Field>
              <Field
                id={`${prefix}-done`}
                label={m.content_field_done()}
                error={sectionErrors?.done_when?.message}
              >
                <input
                  id={`${prefix}-done`}
                  className={field}
                  lang={language}
                  {...form.register(`sections.${index}.done_when`)}
                />
              </Field>
              <IssueList issues={issuesFor(section.id)} />
            </li>
          );
        })}
      </ol>
      {errors.sections?.root?.message && (
        <p className={fieldError}>{errors.sections.root.message}</p>
      )}
      {errors.sections?.message && <p className={fieldError}>{errors.sections.message}</p>}
      <button
        type="button"
        className={secondary}
        onClick={() => sections.append({ ...EMPTY, id: newId() })}
      >
        {m.content_add_section()}
      </button>
      <EditorFooter
        label={m.content_path_save()}
        confirm={content.has_progress ? m.content_reset_warning() : null}
        state={saving}
        issues={general}
        onSave={() => void submit()}
        onCancel={onCancel}
        onReload={onReload}
      />
    </form>
  );
}

function Field({
  id,
  label: text,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className={label} htmlFor={id}>
        {text}
      </label>
      {children}
      {error && <p className={fieldError}>{error}</p>}
    </div>
  );
}
