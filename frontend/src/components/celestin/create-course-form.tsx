/** Creating a course: a name, a subject and a language, the last two for good (005 R1.2, R1.3; spec 011 R1). */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  DEFAULT_COURSE_LANGUAGE,
  isCourseLanguage,
  type CourseLanguage,
} from "@/lib/course-language";
import { useLocale } from "@/lib/i18n";
import { AUTONYM } from "@/lib/locale";
import { apiMessage } from "@/lib/tutor/client";
import type { CourseSummary, Subject, SubjectId } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { field, fieldError, label, primary, secondary, panel } from "./styles";

// A factory called in render: a message read at import would freeze the language.
const makeSchema = () =>
  z.object({
    name: z
      .string()
      .trim()
      .min(1, m.course_create_name_required())
      .max(80, m.course_create_name_too_long()),
    subject: z.string().min(1, m.course_create_subject_required()),
    language: z.string().min(1),
  });

type Values = z.infer<ReturnType<typeof makeSchema>>;

export function CreateCourseForm({
  subjects,
  onCreate,
  onCancel,
}: {
  subjects: Subject[];
  onCreate: (name: string, subject: SubjectId, language: CourseLanguage) => Promise<CourseSummary>;
  onCancel: () => void;
}) {
  const schema = useMemo(makeSchema, []);
  // The interface language is the natural first guess, when a subject is offered in it.
  const locale = useLocale();
  const offered = useMemo(
    () => [...new Set(subjects.flatMap((subject) => subject.languages))],
    [subjects],
  );
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      subject: "",
      language:
        isCourseLanguage(locale) && offered.includes(locale)
          ? locale
          : (offered[0] ?? DEFAULT_COURSE_LANGUAGE),
    },
  });
  const subjectId = form.watch("subject");
  const languages = subjects.find((subject) => subject.id === subjectId)?.languages ?? offered;
  const language = form.watch("language");
  useEffect(() => {
    const first = languages[0];
    if (first && !languages.includes(language as CourseLanguage)) form.setValue("language", first);
  }, [languages, language, form]);
  const [serverError, setServerError] = useState<string | null>(null);
  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      await onCreate(values.name, values.subject as SubjectId, values.language as CourseLanguage);
    } catch (err) {
      setServerError(apiMessage(err, m.course_create_failed()));
    }
  });
  const { errors, isSubmitting } = form.formState;
  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label={m.courses_new()}
      className={`space-y-4 ${panel}`}
    >
      <div>
        <label className={label} htmlFor="course-name">
          {m.course_name_label()}
        </label>
        <input
          id="course-name"
          className={field}
          placeholder={m.course_create_placeholder()}
          autoComplete="off"
          {...form.register("name")}
        />
        {errors.name && <p className={fieldError}>{errors.name.message}</p>}
      </div>
      <div>
        <label className={label} htmlFor="course-subject">
          {m.course_create_subject_label()}
        </label>
        <select id="course-subject" className={field} {...form.register("subject")}>
          <option value="" disabled>
            {m.course_create_subject_placeholder()}
          </option>
          {subjects.map((subject) => (
            <option key={subject.id} value={subject.id}>
              {subject.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-muted-foreground">{m.course_create_subject_locked()}</p>
        {errors.subject && <p className={fieldError}>{errors.subject.message}</p>}
      </div>
      {offered.length > 1 && (
        <div>
          <label className={label} htmlFor="course-language">
            {m.course_create_language_label()}
          </label>
          <select id="course-language" className={field} {...form.register("language")}>
            {languages.map((code) => (
              <option key={code} value={code} lang={code}>
                {AUTONYM[code]}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            {m.course_create_language_hint()} {m.course_create_language_locked()}
          </p>
        </div>
      )}
      {serverError && (
        <p role="alert" className="text-sm text-destructive">
          {serverError}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={isSubmitting} className={primary}>
          {m.course_create_submit()}
        </button>
        <button type="button" onClick={onCancel} className={secondary}>
          {m.common_cancel()}
        </button>
      </div>
    </form>
  );
}
