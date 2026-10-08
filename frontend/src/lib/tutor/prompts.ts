/**
 * What the interface says to the model on the learner's behalf (spec 010 R4.3).
 *
 * These strings are sent to the tutor and echoed as the learner's turns: they are
 * prompt content, in the course's language (spec 011), whatever language the
 * interface is in. They live apart from the message catalog so nobody translates
 * them by accident. Never import `@/paraglide/messages` here.
 */

import { useCourseLanguage, type CourseLanguage } from "@/lib/course-language";

export const REVIEW_MESSAGE = (title: string) => `Je voudrais revoir la section « ${title} ».`;
export const START_MESSAGE = (title: string) => `On commence la section « ${title} » ?`;
export const NEXT_STEP_MESSAGE = "Étape suivante.";
export const NEXT_SECTION_MESSAGE = "Section suivante.";
export const ANSWER_MESSAGE = (text: string) => `Ma réponse à la question : « ${text} ».`;
export const WORK_MESSAGE = (text: string) => `Voici mon travail, lu sur ma photo :\n${text}`;

/** The tool result the voice session returns to the model when the board tool failed. */
export const VOICE_TOOL_FAILED = "Outil indisponible. Dis-le à l'élève et continue sans.";

/** The same sentences for each course language; the French ones are the constants above. */
export type LearnerSentences = {
  review: (title: string) => string;
  start: (title: string) => string;
  nextStep: string;
  nextSection: string;
  answer: (text: string) => string;
  /** What she sends after a photo of her work was read into text (and she corrected it). */
  work: (text: string) => string;
  voiceToolFailed: string;
};

export const LEARNER_SENTENCES: Record<CourseLanguage, LearnerSentences> = {
  fr: {
    review: REVIEW_MESSAGE,
    start: START_MESSAGE,
    nextStep: NEXT_STEP_MESSAGE,
    nextSection: NEXT_SECTION_MESSAGE,
    answer: ANSWER_MESSAGE,
    work: WORK_MESSAGE,
    voiceToolFailed: VOICE_TOOL_FAILED,
  },
  en: {
    review: (title) => `I'd like to review the section “${title}”.`,
    start: (title) => `Shall we start the section “${title}”?`,
    nextStep: "Next step.",
    nextSection: "Next section.",
    answer: (text) => `My answer to the question: “${text}”.`,
    work: (text) => `Here is my work, read from my photo:\n${text}`,
    voiceToolFailed: "Tool unavailable. Tell the student and carry on without it.",
  },
  nl: {
    review: (title) => `Ik wil graag de sectie “${title}” herhalen.`,
    start: (title) => `Beginnen we met de sectie “${title}”?`,
    nextStep: "Volgende stap.",
    nextSection: "Volgende sectie.",
    answer: (text) => `Mijn antwoord op de vraag: “${text}”.`,
    work: (text) => `Hier is mijn werk, ingelezen van mijn foto:\n${text}`,
    voiceToolFailed: "Hulpmiddel niet beschikbaar. Zeg het aan de leerling en ga verder zonder.",
  },
};

export const learnerSentences = (language: CourseLanguage): LearnerSentences =>
  LEARNER_SENTENCES[language];

/** The sentences of the course on screen (French outside a provider). */
export const useLearnerSentences = (): LearnerSentences => learnerSentences(useCourseLanguage());
