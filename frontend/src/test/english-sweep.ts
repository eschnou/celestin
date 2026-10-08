/** The English sweep (spec 010 R3, task 10.3): French the interface left behind.
 *
 *  Walks the text and the accessible attributes of a rendered screen and returns every
 *  piece that carries an accented French letter or a guillemet *outside* an element marked
 *  `lang="fr"`. Course text is French and marked as such; interface text in an English
 *  interface must not be. It sees accented French only (the ESLint rule has the same
 *  blind spot), which is the part of French an English sentence cannot contain. */

import { FRENCH as FRENCH_LETTERS } from "../../eslint-rules/i18n.js";
import { APP_NAME } from "@/lib/brand";
import type { Locale } from "@/lib/locale";

// Accents are not the only tell: short unaccented words the interface uses. Whole words, so
// "Physics" or "course" never match. A conservative list, not a dictionary.
const UNACCENTED_WORDS =
  "vide|Retour|Connexion|Chapitre|cours|Annuler|Enregistrer|Supprimer|Ouvrir|Commencer|Reprendre|Suivant|Valider|Fermer|Mes|Nouveau|Nouvelle|Tableau|Graphique|Exercices|Parcours|indice|exposant";
const FRENCH = new RegExp(`${FRENCH_LETTERS}|\\b(?:${UNACCENTED_WORDS})\\b`);
const ATTRIBUTES = ["aria-label", "title", "placeholder", "alt"];

// The product's name carries an accent in both languages: it is not French left behind.
const isFrench = (text: string) => FRENCH.test(text.replaceAll(APP_NAME, ""));

export function frenchOutsideCourseText(root: ParentNode = document.body): string[] {
  const found: string[] = [];
  // The root's own `lang` is the interface's: only a French region *inside* the page is course text.
  const outside = (element: Element | null) => {
    const region = element?.closest('[lang="fr"]');
    return !region || region === document.documentElement;
  };

  const walker = document.createTreeWalker(root as Node, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? "";
    if (isFrench(text) && outside(node.parentElement)) found.push(text.trim());
  }
  for (const element of Array.from(root.querySelectorAll("*"))) {
    if (!outside(element)) continue;
    for (const name of ATTRIBUTES) {
      const value = element.getAttribute(name);
      if (value && isFrench(value)) found.push(`${name}="${value}"`);
    }
  }
  return found;
}

// --- the other interface languages (spec 017 §5.5) ---------------------------------------------
//
// Dutch has accents of its own (« België », « één »), so a Dutch screen is checked by whole
// words only: the French and the English the interface might have left behind. Course text,
// whatever language it is in, says so with `lang` and is not looked at.

const FRENCH_WORDS =
  /\b(?:Retour|Connexion|Déconnexion|Chapitre|Annuler|Enregistrer|Supprimer|Commencer|Reprendre|Suivant|Valider|Fermer|Exercices|Parcours|Paramètres|Mes cours|Nouveau|Nouvelle|Réessayer|Matière|Tableau)\b/;
const ENGLISH_WORDS =
  /\b(?:Back|Sign in|Sign out|Cancel|Save|Delete|Next|Previous|Settings|Chapter|Chapters|Course|Courses|Lesson|Practice|Summary|Loading|Try again|Continue|Resume|Review|Search|Close|Copy|Rename|Preparing)\b/;

/** The detectors, by interface language: what must not appear in a screen written in it. */
export const FOREIGN: Record<Locale, (text: string) => boolean> = {
  fr: (text) => ENGLISH_WORDS.test(text),
  en: (text) => isFrench(text),
  nl: (text) => FRENCH_WORDS.test(text) || ENGLISH_WORDS.test(text),
};

/** Text of another language in a screen written in `locale`, outside the regions that carry a `lang`
 *  of their own (course text is marked, whichever language it is in). */
export function foreignTextOutside(locale: Locale, root: ParentNode = document.body): string[] {
  const found: string[] = [];
  const foreign = FOREIGN[locale];
  const outside = (element: Element | null) => {
    const region = element?.closest("[lang]");
    return !region || region === document.documentElement || region.getAttribute("lang") === locale;
  };
  const walker = document.createTreeWalker(root as Node, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? "";
    if (foreign(text.replaceAll(APP_NAME, "")) && outside(node.parentElement))
      found.push(text.trim());
  }
  for (const element of Array.from(root.querySelectorAll("*"))) {
    if (!outside(element)) continue;
    for (const name of ATTRIBUTES) {
      const value = element.getAttribute(name);
      if (value && foreign(value.replaceAll(APP_NAME, ""))) found.push(`${name}="${value}"`);
    }
  }
  return found;
}
