// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { frenchOutsideCourseText } from "../english-sweep";

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
