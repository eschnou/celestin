/** The English sweep (spec 010 R3, task 10.3): French the interface left behind.
 *
 *  Walks the text and the accessible attributes of a rendered screen and returns every
 *  piece that carries an accented French letter or a guillemet *outside* an element marked
 *  `lang="fr"`. Course text is French and marked as such; interface text in an English
 *  interface must not be. It sees accented French only (the ESLint rule has the same
 *  blind spot), which is the part of French an English sentence cannot contain. */

import { FRENCH as FRENCH_LETTERS } from "../../eslint-rules/i18n.js";
import { APP_NAME } from "@/lib/brand";

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
