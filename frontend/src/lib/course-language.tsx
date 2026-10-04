/**
 * The language of the course: the material, the pack, the path, Célestin's speech and the
 * notation the board draws (spec 011). It belongs to the course and never changes. It is
 * not the interface language (`lib/locale.ts`): regions that show course text carry
 * `lang={language}` so a screen reader pronounces them in the course's language, whatever
 * language the buttons around them are in.
 *
 * The route that shows a course, a chapter or its content provides it from what the server
 * sent; outside a provider (tests of a single component) it is French.
 */
import { createContext, useContext, type ReactNode } from "react";

export const COURSE_LANGUAGES = ["fr", "en"] as const;
export type CourseLanguage = (typeof COURSE_LANGUAGES)[number];
export const DEFAULT_COURSE_LANGUAGE: CourseLanguage = "fr";

const CourseLanguageContext = createContext<CourseLanguage>(DEFAULT_COURSE_LANGUAGE);

export function CourseLanguageProvider({
  language,
  children,
}: {
  language: CourseLanguage;
  children: ReactNode;
}) {
  return (
    <CourseLanguageContext.Provider value={language}>{children}</CourseLanguageContext.Provider>
  );
}

export function useCourseLanguage(): CourseLanguage {
  return useContext(CourseLanguageContext);
}
