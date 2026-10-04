import { describe as suite, expect, it } from "vitest";
import { describe, stepText } from "../describe";
import { sanitise } from "../graph";
import { HIDDEN, LOOP, METHOD, NESTED, PATH, REPEAT, SECRET } from "./fixtures";

const read = (block: Parameters<typeof sanitise>[0]) => describe(sanitise(block)).map(stepText);

suite("describe", () => {
  it("reads the method in order, each answer with where it leads", () => {
    expect(read(METHOD)).toEqual([
      "Étape 1 — Calculer les différences entre termes consécutifs.",
      "Étape 2 — question : Sont-elles égales ? Si « oui » : étape 3. Si « non » : étape 4.",
      "Étape 3 — C'est une SA. Fin du chemin.",
      "Étape 4 — Calculer les quotients entre termes consécutifs.",
      "Étape 5 — question : Sont-ils égaux ? Si « oui » : étape 6.",
      "Étape 6 — C'est une SG. Fin du chemin.",
    ]);
  });

  it("says where a branch stops, but not after an end box", () => {
    const steps = read(NESTED);
    expect(steps.filter((s) => s.endsWith(" Fin du chemin."))).toHaveLength(3);
    expect(read(LOOP)[7]).toBe("Étape 8 — fin : Fin.");
    expect(read(HIDDEN)[2]).toBe("Étape 3 — C'est une SA. Fin du chemin.");
  });

  it("reads an arrow's label on a step too, since the board writes it", () => {
    const steps = read({
      type: "flowchart",
      nodes: [
        { id: "a", text: "Lancer le dé", next: [{ to: "b", label: "puis" }] },
        { id: "b", text: "Noter le résultat", next: [{ to: "a", label: "$n < 10$" }] },
      ],
    });
    expect(steps).toEqual([
      "Étape 1 — Lancer le dé. Flèche « puis » : étape 2.",
      "Étape 2 — Noter le résultat. Flèche « $n < 10$ » : retour à l'étape 1.",
    ]);
    const [, second] = describe(
      sanitise({
        type: "flowchart",
        nodes: [
          { id: "a", text: "A", next: [{ to: "b", label: "puis" }] },
          { id: "b", text: "B", next: [{ to: "a", label: "$n < 10$" }] },
        ],
      }),
    );
    expect(second!.parts.filter((p) => p.rich).map((p) => p.text)).toEqual(["B", "$n < 10$"]);
  });

  it("says where a loop goes back to, and names the kinds of boxes", () => {
    const steps = read(LOOP);
    expect(steps[0]).toBe("Étape 1 — départ : Début.");
    expect(steps[1]).toBe("Étape 2 — entrée ou sortie : Lire $n$.");
    expect(steps[3]).toBe(
      "Étape 4 — question : $i \\leqslant n$ ? Si « oui » : étape 5. Si « non » : étape 7.",
    );
    expect(steps[5]).toBe("Étape 6 — $i \\leftarrow i + 1$. Retour à l'étape 4.");
    expect(steps[7]).toBe("Étape 8 — fin : Fin.");
    expect(read(REPEAT)[2]).toContain("Si « non » : retour à l'étape 2.");
  });

  it("says « Ensuite » only when the next step is not the following one", () => {
    const steps = read({
      type: "flowchart",
      nodes: [
        {
          id: "q",
          kind: "decision",
          text: "Q ?",
          next: [
            { to: "a", label: "oui" },
            { to: "b", label: "non" },
          ],
        },
        { id: "a", text: "A", next: [{ to: "c" }] },
        { id: "b", text: "B", next: [{ to: "c" }] },
        { id: "c", text: "C" },
      ],
    });
    expect(steps[1]).toBe("Étape 2 — A.");
    expect(steps[2]).toBe("Étape 3 — C. Fin du chemin.");
    expect(steps[3]).toBe("Étape 4 — B. Ensuite : étape 3.");
  });

  it("reads a hidden box as to be completed, never its text", () => {
    const steps = read(HIDDEN);
    expect(steps[3]).toBe("Étape 4 — à compléter.");
    expect(steps.join(" ")).not.toContain(SECRET);
  });

  it("marks the walk-through", () => {
    const steps = read(PATH);
    expect(steps[3]).toContain("(étape en cours)");
    expect(steps[4]).toContain("(déjà parcourue)");
    expect(steps[6]).not.toContain("(");
  });

  it("keeps Célestin's texts and answers apart for RichText", () => {
    const [, question] = describe(sanitise(LOOP)).slice(2);
    expect(question!.parts.filter((p) => p.rich).map((p) => p.text)).toEqual([
      "$i \\leqslant n$ ?",
      "oui",
      "non",
    ]);
  });
});
