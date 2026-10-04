import type { FlowNodeKind } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { pathState, readingOrder, type Graph } from "./graph";
import { layers } from "./layout";

/**
 * A flowchart as an ordered list of steps: what a screen reader reads, and what
 * the board shows when the drawing will not fit. Steps are numbered in reading
 * order (depth-first from the first node, each node's exits in Célestin's order).
 *
 * Each step says where it leads: every labelled arrow (« Si « oui » : étape 3. »
 * for a question, « Flèche « puis » : étape 5. » otherwise), a loop (« Retour à
 * l'étape 2. »), a jump (« Ensuite : étape 6. »), a branch that stops (« Fin du
 * chemin. »); a step with none of these goes on to the next number.
 *
 * `rich` parts are Célestin's text and go through RichText (maths included); the
 * rest is ours. A hidden node reads « à compléter »: its text is already gone.
 */

export type StepPart = { rich: boolean; text: string };
export type Step = { parts: StepPart[] };

/** The step number and what kind of box it is: message functions, read when the steps are built. */
const HEAD: Record<FlowNodeKind, (input: { n: number }) => string> = {
  step: m.describe_flowchart_step,
  decision: m.describe_flowchart_step_decision,
  io: m.describe_flowchart_step_io,
  start: m.describe_flowchart_step_start,
  end: m.describe_flowchart_step_end,
};

export function describe(g: Graph): Step[] {
  const order = readingOrder(g);
  const number = new Array<number>(g.nodes.length).fill(0);
  order.forEach((i, k) => (number[i] = k + 1));
  const { loops } = layers(g.nodes.map((node) => node.exits.map((e) => e.to)));
  const back = new Set(loops.map(([u, v]) => u * g.nodes.length + v));
  const walk = pathState(g);

  return order.map((i) => {
    const node = g.nodes[i]!;
    const k = number[i]!;
    const plain = (text: string): StepPart => ({ rich: false, text });
    const parts: StepPart[] = [plain(HEAD[node.kind]({ n: k }))];
    parts.push(
      node.hidden ? plain(m.describe_flowchart_hidden()) : { rich: true, text: node.text },
    );
    const mark =
      walk.current === i
        ? m.describe_flowchart_current()
        : walk.visited.has(i)
          ? m.describe_flowchart_visited()
          : "";
    if (mark) parts.push(plain(` ${mark}`));
    // « Sont-elles égales ? » needs no full stop after it.
    if (mark || node.hidden || !/[.?!…:]\s*$/.test(node.text)) parts.push(plain("."));
    for (const exit of node.exits) {
      const to = number[exit.to]!;
      const loop = back.has(i * g.nodes.length + exit.to);
      if (exit.label !== null) {
        // A question's answers, and any arrow Célestin labelled: the board writes them all.
        const lead =
          node.kind === "decision"
            ? m.describe_flowchart_if_open()
            : m.describe_flowchart_arrow_open();
        const close = loop
          ? m.describe_flowchart_close_loop({ n: to })
          : m.describe_flowchart_close_step({ n: to });
        parts.push(plain(lead), { rich: true, text: exit.label }, plain(close));
      } else if (loop) {
        parts.push(plain(` ${m.describe_flowchart_loop({ n: to })}`));
      } else if (to !== k + 1) {
        parts.push(plain(` ${m.describe_flowchart_jump({ n: to })}`));
      }
    }
    // Where a branch stops: otherwise the next number reads as its next step.
    if (node.exits.length === 0 && node.kind !== "end")
      parts.push(plain(` ${m.describe_flowchart_dead_end()}`));
    return { parts };
  });
}

/** A step as plain text, maths left as written (tests and debugging). */
export const stepText = (step: Step) => step.parts.map((p) => p.text).join("");
