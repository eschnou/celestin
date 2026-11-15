/**
 * What the interface says to the model on the learner's behalf (spec 010 R4.3).
 *
 * These strings are sent to the tutor and echoed as the learner's turns: they are
 * prompt content, in the course's language (spec 011), whatever language the
 * interface is in. They live apart from the message catalog so nobody translates
 * them by accident. Never import `@/paraglide/messages` here.
 */

import { useCourseLanguage, type CourseLanguage } from "@/lib/course-language";
import type { RevisionOutcome } from "@/lib/tutor/types";

export const REVIEW_MESSAGE = (title: string) => `Je voudrais revoir la section « ${title} ».`;
export const START_MESSAGE = (title: string) => `On commence la section « ${title} » ?`;
/** A section already begun in an earlier séance (spec 019): « Reprendre ». */
export const RESUME_MESSAGE = (title: string) => `On reprend la section « ${title} » ?`;
/** « Passer » (spec 019): only the student decides, so it is said, not asked. */
export const SKIP_MESSAGE = (title: string) => `Je passe la section « ${title} ».`;
export const NEXT_STEP_MESSAGE = "Étape suivante.";
export const NEXT_SECTION_MESSAGE = "Section suivante.";
export const ANSWER_MESSAGE = (text: string) => `Ma réponse à la question : « ${text} ».`;
export const WORK_MESSAGE = (text: string) => `Voici mon travail, lu sur ma photo :\n${text}`;
/** A révision's quick replies (spec 020 D3): the student's own judgement of a question. */
export const ASSESS_MESSAGE: Record<RevisionOutcome, string> = {
  solid: "Pour moi, c'est acquis.",
  shaky: "Pour moi, c'est fragile.",
  todo: "Pour moi, c'est à revoir.",
};

/** The tool result the voice session returns to the model when the board tool failed. */
export const VOICE_TOOL_FAILED = "Outil indisponible. Dis-le à l'élève et continue sans.";

/** The same sentences for each course language; the French ones are the constants above. */
export type LearnerSentences = {
  review: (title: string) => string;
  start: (title: string) => string;
  resume: (title: string) => string;
  skip: (title: string) => string;
  nextStep: string;
  nextSection: string;
  answer: (text: string) => string;
  /** What she sends after a photo of her work was read into text (and she corrected it). */
  work: (text: string) => string;
  /** A révision's quick reply: how the question went, in the student's own words. */
  assess: (outcome: RevisionOutcome) => string;
  voiceToolFailed: string;
};

export const LEARNER_SENTENCES: Record<CourseLanguage, LearnerSentences> = {
  fr: {
    review: REVIEW_MESSAGE,
    start: START_MESSAGE,
    resume: RESUME_MESSAGE,
    skip: SKIP_MESSAGE,
    nextStep: NEXT_STEP_MESSAGE,
    nextSection: NEXT_SECTION_MESSAGE,
    answer: ANSWER_MESSAGE,
    work: WORK_MESSAGE,
    assess: (outcome) => ASSESS_MESSAGE[outcome],
    voiceToolFailed: VOICE_TOOL_FAILED,
  },
  en: {
    review: (title) => `I'd like to review the section “${title}”.`,
    start: (title) => `Shall we start the section “${title}”?`,
    resume: (title) => `Shall we pick up the section “${title}” again?`,
    skip: (title) => `I'm skipping the section “${title}”.`,
    nextStep: "Next step.",
    nextSection: "Next section.",
    answer: (text) => `My answer to the question: “${text}”.`,
    work: (text) => `Here is my work, read from my photo:\n${text}`,
    assess: (outcome) =>
      ({
        solid: "I'd say it's solid.",
        shaky: "I'd say it's shaky.",
        todo: "I'd say I need to review it.",
      })[outcome],
    voiceToolFailed: "Tool unavailable. Tell the student and carry on without it.",
  },
  nl: {
    review: (title) => `Ik wil graag de sectie “${title}” herhalen.`,
    start: (title) => `Beginnen we met de sectie “${title}”?`,
    resume: (title) => `Gaan we verder met de sectie “${title}”?`,
    skip: (title) => `Ik sla de sectie “${title}” over.`,
    nextStep: "Volgende stap.",
    nextSection: "Volgende sectie.",
    answer: (text) => `Mijn antwoord op de vraag: “${text}”.`,
    work: (text) => `Hier is mijn werk, ingelezen van mijn foto:\n${text}`,
    assess: (outcome) =>
      ({
        solid: "Voor mij is dat gekend.",
        shaky: "Voor mij is dat wankel.",
        todo: "Voor mij is dat te herhalen.",
      })[outcome],
    voiceToolFailed: "Hulpmiddel niet beschikbaar. Zeg het aan de leerling en ga verder zonder.",
  },
};

export const learnerSentences = (language: CourseLanguage): LearnerSentences =>
  LEARNER_SENTENCES[language];

/** The sentences of the course on screen (French outside a provider). */
export const useLearnerSentences = (): LearnerSentences => learnerSentences(useCourseLanguage());
