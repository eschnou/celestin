// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { foreignTextOutside, frenchOutsideCourseText } from "../english-sweep";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("frenchOutsideCourseText", () => {
  it("finds French chrome: text and accessible attributes", () => {
    document.body.innerHTML = `<main><h1>Mes cours</h1><button aria-label="Réessayer">x</button>
      <p>Tu as 3 chapitres terminés</p><input placeholder="Choisis une matière"></main>`;
    expect(frenchOutsideCourseText()).toEqual([
      "Mes cours",
      "Tu as 3 chapitres terminés",
      'aria-label="Réessayer"',
      'placeholder="Choisis une matière"',
    ]);
  });

  it("lets course text through where it says it is French, at any depth", () => {
    document.body.innerHTML = `<main><p lang="fr">Les suites numériques</p>
      <div lang="fr"><ul><li>Définition « suite »</li></ul></div>
      <button lang="fr" title="Étape">x</button></main>`;
    expect(frenchOutsideCourseText()).toEqual([]);
  });

  it("finds a few unaccented French words too, as whole words", () => {
    document.body.innerHTML = `<main><p>Graphique vide</p><button title="Retour">x</button></main>`;
    expect(frenchOutsideCourseText()).toEqual(["Graphique vide", 'title="Retour"']);
  });

  it("does not take the accent of the product's name for French", () => {
    document.body.innerHTML = `<main><h1>Professor Célestin</h1><input placeholder="Write to Célestin…"></main>`;
    expect(frenchOutsideCourseText()).toEqual([]);
  });

  it("does not take English, digits or unaccented French for a leak", () => {
    document.body.innerHTML = `<main><h1>My courses</h1><p>12 / 30 chapters done</p><p>Physics course, Retouch</p></main>`;
    expect(frenchOutsideCourseText()).toEqual([]);
  });
});

describe("foreignTextOutside (spec 017)", () => {
  it("finds French and English in a Dutch screen, as whole words", () => {
    document.body.innerHTML = `<main><h1>Mijn cursussen</h1><p>Retour naar de cursus</p>
      <button aria-label="Sign out">x</button><input placeholder="Zoeken op naam"></main>`;
    expect(foreignTextOutside("nl")).toEqual(["Retour naar de cursus", 'aria-label="Sign out"']);
  });

  it("does not take Dutch accents, digits or the product's name for a leak", () => {
    document.body.innerHTML = `<main><h1>Célestin — één cursus in België</h1><p>12 / 30 hoofdstukken afgerond</p></main>`;
    expect(foreignTextOutside("nl")).toEqual([]);
  });

  it("lets course text through where it carries a language of its own, whichever it is", () => {
    document.body.innerHTML = `<main><p lang="fr">Retour au chapitre</p><div lang="en"><p>Back to the lesson</p></div>
      <p lang="nl">Terug naar de les</p></main>`;
    expect(foreignTextOutside("nl")).toEqual([]);
  });

  it("keeps the English detector what it was", () => {
    document.body.innerHTML = `<main><h1>Mes cours</h1><p lang="fr">Les suites</p></main>`;
    expect(foreignTextOutside("en")).toEqual(["Mes cours"]);
  });

  it("looks for English in a French screen too", () => {
    document.body.innerHTML = `<main><h1>Mes cours</h1><button>Sign in</button></main>`;
    expect(foreignTextOutside("fr")).toEqual(["Sign in"]);
  });
});
