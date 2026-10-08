import { describe, expect, it } from "vitest";
import { renderErrorPage } from "../error-page";

describe("renderErrorPage", () => {
  it("is French by default", () => {
    const page = renderErrorPage();
    expect(page).toContain('<html lang="fr">');
    expect(page).toContain("Cette page ne s'est pas chargée");
    expect(page).toContain("Réessayer");
  });

  it("speaks English when asked", () => {
    const page = renderErrorPage("en");
    expect(page).toContain('<html lang="en">');
    expect(page).toContain("<title>This page didn't load</title>");
    expect(page).toContain("Try again");
    expect(page).not.toContain("Réessayer");
  });

  it("speaks Dutch when asked (spec 017)", () => {
    const page = renderErrorPage("nl");
    expect(page).toContain('<html lang="nl">');
    expect(page).toContain("<title>Deze pagina is niet geladen</title>");
    expect(page).toContain("Opnieuw proberen");
    expect(page).not.toContain("Réessayer");
  });
});
