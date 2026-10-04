# 009 — The `flowchart` block (organigramme): design

Sections 1 to 6 are the design as it was reviewed on 28 September 2026, kept as written:
it is what the code comments cite. Where the code now differs, a note marked **As built** says
so in place, and section 7 lists every deviation. The scratchpad paths the design mentions
(prototypes, fuzz scripts) were never part of the repository.

## 1. Summary

Revised design for the `flowchart` block (organigramme / logigramme). Célestin sends a graph, never a picture: `nodes`, each with an id, a kind (`start|end|step|decision|io`), a text that may contain `$…$`, and its own exits `next: [{to, label?}]`. Three optional fields go with them: `path` (the nodes followed so far; the last one is the current step), `hidden` (nodes drawn as « ? », allowed only on an exercise's `drawing`) and `caption`. The board lays the chart out with hand-written code and no new dependency. Rows come from a depth-first walk and longest paths, and that function is shared with Python through a JSON case file keyed by index. Long edges get passages. Rows are ordered depth-first with the heavier branch first, then by barycenter sweeps that count crossings. x positions come from an isotonic least-squares fit over asymmetric footprints. Edges are orthogonal and run on channel tracks, with loops in side lanes. All text is HTML placed over an SVG that holds no text, rendered by RichText/KaTeX with trust:false. This keeps maths in labels and avoids repeating 008's D10 ban on `$` in labels.

What changed after the critique:

1. **Two exits at most per decision.** Three cases become two nested questions, as courses draw them. Ports are fixed by position: the left branch leaves from the bottom vertex, the right branch from the right vertex, a loop from the left vertex. Two exits never share a port, and each label sits on its own segment inside the node's reserved footprint.
2. **Diamond shape.** A diamond is a fixed-aspect rhombus, A = max(Amin, lw/2 + 2·lh/2 + pad). Its label width is chosen to minimise A.
3. **Measurement.** Every label is measured once, at five fixed max-widths, in a 0×0 overflow-hidden layer, using `w-max min-w-min` blocks so unbreakable words and formulas report their real width. The layout then narrows labels step by step before it scales anything. The scale never goes below 0.85; past that, the ordered list is shown visibly instead of scrolling.
4. **The screen-reader list uses KaTeX MathML output.** The html output is aria-hidden, which I checked in this repo.
5. **`hidden_leak`.** It compares word runs and formulas, not letter folds. A list of words to place (a word bank) is allowed when two or more nodes are hidden.
6. **The `drawing` union uses a callable discriminator.** A missing tag still means a chart, as in 008, and FlowchartBlock declares `type` as required.
7. **Width rule.** `wide` uses a budget of 3 per row, where a decision counts 2.
8. **One-exit decisions are allowed,** so Célestin never has to invent a branch the pack does not give.

A scratch prototype of the whole layout, in Python, backs these choices:

- The fixtures draw without any segment entering a box or any label overlap, at widths 268, 560 and 800.
- A fuzz of 2 696 random valid charts had 0 invariant violations.
- The fixtures all fit the phone board (268 px) at a scale of at least 0.85.
- The phone-width list fallback rate on random texts is 9.7 %, and 0 % at 560 px.

The schema grows by 2 115 characters (about 530 tokens), measured against the real fixture.

## 2. Model: `app/domain/flowchart.py`

```python
"""Flowchart blocks (organigrammes).

A flowchart is a graph, never a picture: nodes with a kind and a text, and each
node's exits. The board lays it out and draws it; the model never gives a
position, a colour or a style (`extra="forbid"` refuses them). Only rules that
never change live here (types, enums, sizes); the graph rules (ids, exits,
reachability, width, the path, where `hidden` may go, leaks) run in
`display_board` (`app/services/tools/flowcharts.py`), so a stored card keeps
replaying if a rule tightens (008 R4.7).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


MAX_NODES = 12
# A question answers oui / non. Three cases are two nested questions: how the
# course draws them, and what fits the board at phone width.
MAX_EXITS = 2
MAX_HIDDEN = 4

NodeId = Annotated[str, Field(min_length=1, max_length=16)]
NodeText = Annotated[str, Field(min_length=1, max_length=80)]
ExitLabel = Annotated[str, Field(min_length=1, max_length=16)]
Caption = Annotated[str, Field(min_length=1, max_length=200)]
# `io` is the course's « Lire » / « Afficher » box. `start` and `end` are optional
# shapes: the first node is the root whatever its kind.
FlowNodeKind = Literal["start", "end", "step", "decision", "io"]


# Named Flow* so their $defs keys never collide with another block's `Node`/`Exit`.
class FlowExit(_Model):
    to: NodeId
    label: ExitLabel | None = None


class FlowNode(_Model):
    id: NodeId
    kind: FlowNodeKind = "step"
    text: NodeText
    next: Annotated[list[FlowExit], Field(max_length=MAX_EXITS)] = []


class FlowchartBlock(_Model):
    """A flowchart (organigramme) the board lays out itself from nodes and their
    exits, never positions. The first node is where it starts."""

    # Required, unlike the older blocks' `type`: a card's `drawing` picks its member
    # by this tag and reads a missing tag as a chart (board.py `Drawing`), so every
    # drawing block after the chart must say what it is.
    type: Literal["flowchart"]
    nodes: Annotated[list[FlowNode], Field(min_length=2, max_length=MAX_NODES)]
    # Descriptions reach the model with the schema: without them `path` reads as a
    # file path and `hidden` as "not drawn at all".
    path: Annotated[
        list[NodeId],
        Field(
            max_length=2 * MAX_NODES,
            description="Nœuds déjà parcourus, dans l'ordre des flèches ; le dernier est l'étape en cours.",
        ),
    ] = []
    hidden: Annotated[
        list[NodeId],
        Field(
            max_length=MAX_HIDDEN,
            description="Sur le drawing d'un exercise : nœuds affichés « ? », à retrouver.",
        ),
    ] = []
    caption: Caption | None = None


# Notes for the implementer (not in the file):
# - No model_validator: uniqueness, references, reachability, the width budget are
#   graph rules in the tool.
# - List defaults `= []` follow RecapCard.watch (pydantic copies defaults).
# - Tests construct FlowchartBlock(type="flowchart", ...) since `type` has no default.
# - Measured on this branch with the real board models: TypeAdapter(FlowchartBlock)
#   .json_schema() is 1 893 characters.
```

> **As built.** `FlowExit.to`, `FlowNode.id`, `path` and `hidden` carry the `NOT_PROSE`
> marker (`app/domain/prose.py`), so the board's string checks read them as ids, not prose.
> The comment on `type` is stale in one respect: a drawing without `type` is no longer read as a
> chart whatever it holds; `_drawing_type` reads the family from its keys (`nodes` means a
> flowchart), and a chart only when no key tells (§7, item 29).

## 3. Tool rules: `app/services/tools/flowcharts.py`

### 3.1 Module, constants and signatures

backend/app/services/tools/flowcharts.py (new). Module docstring: "The flowchart rules `display_board` applies. They run in the tool, not on the card model: they could change (a limit, a fold) and a stored card must keep replaying. Each refusal is a rule code for the logs and a French message naming the field."

Imports: app.domain.flowchart (FlowchartBlock), app.domain.board (BoardCard, ExerciseCard), app.services.tools.text (spaced). It must not import tools/board.py, because board.py imports it.

**Constants.** MAX_FLOWCHARTS_PER_CARD = 1; ROW_BUDGET = 3 (a decision weighs 2, any other node 1, passages 0); MAX_QUESTION = 40 (raw characters, TeX source included); MIN_SECRET = 5 (letters and digits of a hidden text's words and formulas); MIN_FORMULA = 4 (a hidden formula's TeX, whitespace removed).

`Refusal = tuple[str, str]`. `at` is the path from card_blocks ("blocks[1]" or "drawing"). `{node}` renders as `nodes[i] (« id »)`.

**Signatures** (board.py calls only `flowcharts_refusal`):

```python
def layers(exits: Mapping[str, Sequence[str]]) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Each node's row and the loops, as the board lays them out (flowchart/layout.ts
    `layers`; tests/fixtures/flowchart_layers.json holds the two together)."""
    state: dict[str, int] = {}
    loops: set[tuple[str, str]] = set()
    finished: list[str] = []
    def walk(u: str) -> None:
        state[u] = 1
        for v in exits[u]:
            if v not in exits or v == u:
                continue
            if state.get(v) == 1:
                loops.add((u, v))
            elif v not in state:
                walk(v)
        state[u] = 2
        finished.append(u)
    for u in exits:                  # nodes[0] first, then any node not yet reached, in order
        if u not in state:
            walk(u)
    row = dict.fromkeys(exits, 0)
    for u in reversed(finished):     # a topological order of the non-loop exits
        for v in exits[u]:
            if v in exits and v != u and (u, v) not in loops:
                row[v] = max(row[v], row[u] + 1)
    return row, loops

def flowchart_refusal(block: FlowchartBlock, at: str) -> Refusal | None   # graph rules, table order
def flowcharts_refusal(flowcharts: Sequence[tuple[str, FlowchartBlock]], card: BoardCard) -> Refusal | None
    """per_card; then for each flowchart: exercise_path / hidden_place, the graph rules, hidden_leak."""
```
Called with `exits = {n.id: [e.to for e in n.next] for n in block.nodes}` (dict keeps node order).

> **As built.** `flowcharts_refusal(items, card, ctx)`, the family signature every drawing
> shares in `_FAMILIES` (`ctx.pack` is not read), and `flowcharts_summary(items)` for the log.
> `leaks(secret, text)` and `reading_order(block)` are public for `scripts/probe.py`.

### 3.2 Rule table

| Code | Applies to | Refused when | French message template |
|---|---|---|---|
| per_card | an explanation | more than 1 flowchart | « Une carte porte au plus un organigramme ; mets l'autre sur une carte suivante. » |
| exercise_path | an exercise's drawing | `path` not empty | « L'organigramme {at} accompagne un exercice ouvert : pas de path, sinon il montre le chemin à suivre. Le chemin se montre après la tentative, dans un worked_example ou une explanation. » |
| hidden_place | any card except an exercise | `hidden` not empty | « L'organigramme {at} : hidden ne sert que sur le drawing d'un exercise, pour un organigramme à compléter. Ici, montre toutes les cases. » |
| ids | nodes[].id; hidden[] | an id used twice; a hidden id listed twice | « L'organigramme {at} : l'identifiant « {id} » sert à nodes[{i}] et à nodes[{j}] ; chaque nœud a le sien. » / « L'organigramme {at} : hidden cite « {id} » deux fois. » |
| unknown_id | nodes[i].next[k].to, path[k], hidden[k] | names no node | « L'organigramme {at} : {field} renvoie à « {id} », qui n'est l'identifiant d'aucun nœud. » |
| self_loop | nodes[i].next | an exit to the node itself | « L'organigramme {at} : {node} sort vers lui-même ; une boucle revient à une étape précédente. » |
| start | kind "start" | a start not at nodes[0], or two starts / an exit into the start | « L'organigramme {at} : un nœud start vient en premier (nodes[0]), et il n'y en a qu'un. » / « L'organigramme {at} : {node} ramène au nœud start ; une boucle revient à une étape, pas au début. » |
| end | kind "end" | an end with an exit | « L'organigramme {at} : {node} est un nœud end, il n'a pas de sortie. » |
| exits | step, io, start | 2 exits | « L'organigramme {at} : {node} a 2 sorties ; seule une question (decision) en a plusieurs. » |
| decision | kind "decision" | no exit / an exit without label / both labels equal under `spaced` / both exits to one node | « L'organigramme {at} : la question {node} n'a pas de sortie ; chaque réponse que le cours donne a sa flèche. » / « L'organigramme {at} : nodes[{i}].next[{k}] n'a pas d'étiquette ; chaque sortie d'une question dit sa réponse (« oui », « non »…). » / « L'organigramme {at} : les deux sorties de {node} portent l'étiquette « {label} ». » / « L'organigramme {at} : les deux sorties de {node} mènent à « {to} » ; chaque réponse a son chemin. » |
| decision_text | kind "decision" | len(text) > 40 | « L'organigramme {at} : la question {node} dépasse 40 caractères ; garde-la courte et fais le calcul dans une étape avant elle. » |
| unreachable | every node | not reachable from nodes[0] along exits | « L'organigramme {at} : aucune flèche ne mène de nodes[0] à {node} ; relie-le, ou retire-le. » |
| dead_end | non-end nodes, only when the chart has at least one `end` | no exit | « L'organigramme {at} : {node} n'a pas de sortie ; dans un organigramme qui a une fin, seuls les nœuds end terminent. » |
| wide | the rows of `layers` | the weights in one row sum to more than 3 (decision 2, other 1) | « L'organigramme {at} : {nodes} se retrouvent côte à côte ; le tableau en aligne au plus trois, une question comptant pour deux. Regroupe des étapes, ou montre une partie de la méthode à la fois. » ({nodes} = « nodes[3] (« a »), nodes[5] (« b ») et nodes[6] (« c ») ») |
| path | path | consecutive a, b with no exit a→b (repeats are allowed, since a loop can be walked twice; any start node) | « L'organigramme {at} : path passe de « {a} » à « {b} » sans flèche de l'un à l'autre ; path suit les flèches, dans l'ordre. » |
| hidden_leak | an exercise's drawing with hidden nodes | a hidden node's text `_leaks` into a visible text in scope (below) | « L'organigramme {at} : le texte caché de {node} se lit dans {field} ; retire-le de là tant que ton élève doit le retrouver. » When {field} is title/statement/hint, add: « Avec une seule case cachée, c'est la réponse ; pour donner des étiquettes à placer, cache au moins deux cases. » |

> **As built.** Two rules were added after `ids`, in this order: `blank` (a node text, an exit
> label or the caption made only of spaces; §7, item 18) and `placeholder` (a box whose whole
> text marks a hole, « ? », « … », « À compléter », « Étape manquante »: the real text goes in the
> node and its id in `hidden`; §7, items 24 and 25). `per_card` stays (one flowchart per card),
> but `display_board` first applies a cap of two drawings of any family (§7, item 27), so it
> fires only on a card holding exactly two flowcharts. A question with a single labelled exit is
> accepted by `decision` on purpose (§6.1, decision 2).

### 3.3 Order

flowcharts_refusal runs per_card first. Then, for each (at, block) in card order:

1. exercise_path or hidden_place (by card kind);
2. flowchart_refusal: ids → unknown_id → self_loop → start → end → exits → decision → decision_text → unreachable → dead_end → wide → path. The shape rules come first because every later rule reads ids and exits;
3. hidden_leak.

> **As built.** `ids → blank → placeholder → unknown_id → self_loop → start → end → exits →
> decision → decision_text → unreachable → dead_end → wide → path` (`_GRAPH_RULES` in
> `flowcharts.py`).

### 3.4 `hidden_leak`

```python
# Same delimiters as board._MATH / RichText, with groups (board.py is not importable here).
_MATH = re.compile(r"\$\$(.+?)\$\$|\$(?!\s)([^$]*?)(?<!\s)\$", re.DOTALL)
_WORD = re.compile(r"[^\W_]+")

def _tex(m: re.Match[str]) -> str:
    return "".join((m.group(1) or m.group(2)).split())

def _words(prose: str) -> list[tuple[str, str]]:
    return [("w", w) for w in _WORD.findall(unicodedata.normalize("NFKC", prose).casefold())]

def _tokens(text: str) -> list[tuple[str, str]]:
    """Words (NFKC, case-folded, letters and digits) and each formula as one token."""
    out, pos = [], 0
    for m in _MATH.finditer(text):
        out += _words(text[pos:m.start()]); out.append(("m", _tex(m))); pos = m.end()
    return out + _words(text[pos:])

def _leaks(secret: str, text: str) -> bool:
    needle = _tokens(secret)
    if sum(len(v) for _, v in needle) >= MIN_SECRET:
        hay, n = _tokens(text), len(needle)
        if any(hay[i:i + n] == needle for i in range(len(hay) - n + 1)):
            return True
    formulas = [_tex(m) for m in _MATH.finditer(text)]
    return any(len(f) >= MIN_FORMULA and any(f in g for g in formulas)
               for f in (_tex(m) for m in _MATH.finditer(secret)))
```
Scope. The checked texts are:
- always: the chart's visible node texts (`{at}.nodes[j].text`), every exit label (`{at}.nodes[j].next[k].label`, including those of hidden decisions) and `{at}.caption`;
- only when exactly one node is hidden: the exercise's `title`, `statement` and `hint`. With two or more hidden, the statement may list their texts as labels to place (a word bank).

What it catches and misses:
- Whole-word runs, so « raison » is not found in « raisonnement ».
- Formulas as substrings of formulas: `$i \leftarrow i+1$`, `$S \leftarrow S + u_i$`.
- Not paraphrase; that is stated in the docs.

> **As built.** The delimiters are no longer re-declared here: `MATH` and `math_tex` come from
> `app/services/tools/text.py`, the one backend copy of RichText's `$…$` (JavaScript whitespace).
> The formula clause is narrower than written above (§7, item 20).

### 3.5 Checks the board already had

`_bare_commands` walks nodes[].text, next[].label and caption; `\Delta` outside `$…$` is refused naming `card.blocks[0].nodes[1].text`.

> **As built.** `_bare_commands` is gone. The string checks now run in `display_board` on the
> parsed card (rules `string_control`, `string_latex`, `string_script`), and a refusal inside a
> flowchart is logged as `flowchart_refused` with that rule (§7, item 26). Node ids, `to`, `path`
> and `hidden` are marked `NOT_PROSE`, so they are no longer walked as prose (open issue 6 below
> is closed).

### 3.6 Logs

- `flowchart_displayed` {user_id, chapter_id, mode, nodes: [len(nodes) per chart], hidden: total, path: bool};
- `flowchart_refused` {…, rule}.
- A schema refusal is logged through Tool.on_invalid as `flowchart_refused` rule `schema.<pydantic type>`.
- No text, label, id or caption is ever logged.

## 4. Rendering: `frontend/src/components/celestin/flowchart/`

### 4.1 Files

- graph.ts: `sanitise(block): Graph`, `readingOrder(g): number[]`, `pathState(g): {visited:Set<number>; current:number|null; edges:Set<number>}`.
- layout.ts: `METRICS`, `metricsFor(width)`, `LADDER`, `layers`, `structure`, `fit`, `layoutFlowchart(g, sizes, width): Layout | null`. Pure, no React, about 400 lines.
- shapes.ts: `boxFor(kind, label, m, hidden)`, `shapeProps(box, x, cy)` (rect / pill / rhombus / parallelogram).
- measure.tsx: `estimateSize`, `measureItems(g, m)`, `useLabelSizes`, `MeasureLayer`.

> **As built.** `measure.tsx` is three files: `measure.ts`, `use-label-sizes.ts` and
> `measure-layer.tsx`; metrics live in `shapes.ts` (§7, items 1 and 2).

- describe.ts: `describe(g): Item[]`.
- flowchart-view.tsx: `FlowchartView = memo(...)`.
- Reuse ../charts/use-width.ts (import only).
- Edge ids are `i*2 + k` (node i, exit k). No plain object is ever keyed by a model id: ids go into Map<string, number>, everything else is indexed. Numeric-looking ids ("10", "2") would otherwise be reordered by JS.

### 4.2 Layout, step by step

#### Step 0: sanitise

Once, in useMemo on block. A stored conversation replays as written.

- `nodes` must be an array, else it counts as empty. A node is kept only when its id and text are non-empty strings; the first node wins a duplicate id; at most 12 nodes are kept.
- An unknown kind becomes "step".
- `next` must be an array. Keep objects whose `to` is a kept id other than the node itself. Drop a repeated target. Keep at most 2 exits for a decision and 1 for any other kind. A label is kept only if it is a string, else null.
- `path` and `hidden` keep only strings that are kept ids.
- Every hidden node gets text "?" and hidden: true **here**. The secret never goes further: not into measurement, labels, keys, the sr-only list or the aria-label.
- `caption` must be a string, else null.
- Zero nodes shows « Organigramme vide », as charts show « Graphique vide ».

#### Step 1: layers

The same algorithm as Python, index-based:

```ts
export function layers(exits: readonly (readonly number[])[]): { row: number[]; loops: [number, number][] } {
  const n = exits.length, state = new Array<number>(n).fill(0), loops: [number, number][] = [], finished: number[] = [];
  const walk = (u: number) => { state[u] = 1;
    for (const v of exits[u]) { if (v < 0 || v >= n || v === u) continue;
      if (state[v] === 1) loops.push([u, v]); else if (state[v] === 0) walk(v); }
    state[u] = 2; finished.push(u); };
  for (let u = 0; u < n; u++) if (state[u] === 0) walk(u);
  const back = new Set(loops.map(([u, v]) => u * n + v)), row = new Array<number>(n).fill(0);
  for (let k = finished.length - 1; k >= 0; k--) { const u = finished[k];
    for (const v of exits[u]) if (v >= 0 && v < n && v !== u && !back.has(u * n + v)) row[v] = Math.max(row[v], row[u] + 1); }
  return { row, loops };
}
```

#### Step 2: structure (frontend only)

- (a) Ordering walk. Depth-first from node 0, then from leftovers in list order. A decision's forward exits are taken heavier branch first: the number of nodes reachable through forward exits, descending, with ties kept in exit order. The first time a node is reached it is appended to its row. A forward edge u→v with row(v) > row(u)+1 appends one passage per row in between when first traversed. `chain[e]` is the station list (passages, then v).
  - This puts the chain of questions down the middle and the leaves to the right. The staircase otherwise measured 351 px against 278 px on the « type de variable » chart.
- (b) Four rounds of barycenter sweeps. A down sweep keys each item on the mean index of its predecessors, an up sweep on its successors. Items without neighbours keep their index; the sort is stable. After each sweep, count crossings between adjacent rows and keep the ordering with strictly fewer.
- (c) Ports follow the final order.
  - Non-decision: its exit leaves from B (bottom).
  - Decision with 2 forward exits: the one whose first station is left goes B, the right one goes R. One forward exit: B.
  - A decision's loop exit takes L; a second loop exit takes R.
  - A loop from B or L runs in a left lane; from R, in a right lane.

#### Step 3: metrics

`metricsFor(w)` is compact below 360 px.

- Normal: font 13, line 18, padX 10, padY 7, gapX 16, gapY 26, track 8, lane 12, laneGap 12, passage 8, ρ 2, padD 7, Amin 48, edge font 12 / line 16, hidden box 64×36, hidden A 48, margin 2.
- Compact: font 12, line 16, padX 8, padY 6, gapX 12, gapY 24, laneGap 10, padD 6, Amin 40, edge font 11 / line 14, hidden box 56×32, hidden A 44.
- LADDER = [220, 160, 120, 90, 64] px of label max-width.

#### Step 4: measure

`MeasureLayer` sits inside the figure but outside the scaled layer:

`<div aria-hidden className="pointer-events-none invisible absolute left-0 top-0 h-0 w-0 overflow-hidden">`
- The 0×0 clipped box adds nothing to BoardFrame's scroll height, and its children still lay out.
- Node rungs: one `<div className="w-max min-w-min" style={{maxWidth: rung, fontSize, lineHeight}}><RichText text/></div>` per non-hidden node and per rung. `min-w-min` beats max-width, so an unbreakable word or formula reports its real width.
- Exit labels: `<div className="w-max whitespace-nowrap font-semibold" style={{fontSize: edgeFont, lineHeight}}>`, with the same weight as rendered.
- At most 12×5 + 24 = 84 items.
- `useLabelSizes` reads offsetWidth/offsetHeight in useLayoutEffect, keyed on a signature of texts and font. The sizes do not depend on the width, so a resize never re-measures.
- A 0 size (jsdom, or a lesson hidden with display:none) falls back to `estimateSize` and sets `estimated`.
- Re-measure: once on `document.fonts?.ready`, and from a ResizeObserver on the width container whenever `estimated` is set and the width becomes > 0.
- The first render uses estimates. The measured setState happens before paint, so nothing flashes.
- `estimateSize(text, maxW, font, line)`:
  - Tokens are prose words at 0.56·font per character, and each `$…$` as one unbreakable token at 0.6·font per glyph. A `\command` counts as 1 glyph; `{}^_` and spaces count 0; `\frac` gives ×0.6 width and +0.8·line height.
  - Greedy word wrap at maxW with spaces of 0.28·font. A token wider than maxW takes its own line at full width, like min-content.
  - Returns w = the widest line and h = lines·line.

#### Step 5: boxes (shapes.ts)

Label (lw, lh):

- step: w = max(56, lw+2padX), h = max(36, lh+2padY), rx 6.
- io: w = max(56, lw+2padX+2·8), same h; parallelogram skewed by 8.
- start/end: h = max(32, lh+2padY), w = max(56, lw+2padX+h/2), rx = h/2.
- decision: A = max(Amin, lw/2 + ρ·lh/2 + padD), w = 2A, h = 2A/ρ. The label rectangle is inside because (lw/2)/A + (lh/2)/B ≤ 1.
- hidden: the fixed hidden box, or a rhombus with A = hidden A, with a dashed stroke and « ? ». Its size never depends on the secret.

#### Step 6: which label width

- Decision: the rung minimising A, over all rungs.
- Other nodes, for a ladder level L = 0…4: rowCap(r) = (W − (items_r−1)·gapX − passages_r·passage − Σ chrome) / nodes_r, where chrome = 2padX, +16 for io. The node takes the widest rung ≤ min(LADDER[L], rowCap), else the last rung.
- layoutFlowchart tries L = 0…4 and returns the first layout whose width ≤ W. Otherwise it takes level 4 with scale = W/width, and returns null when that scale is below 0.85.

#### Step 7: footprints (half-extents eL, eR around the anchor x)

- Node: w/2 each side. Passage: passage/2.
- An R exit with label width lw: eR = max(eR, A + lw + 10). An L exit: eL = max(eL, A + lw + 10). A labelled B exit: eR = max(eR, lw + 13).
- corner(u,R) = +eR, corner(u,L) = −eL.
- Every label lies inside its node's footprint, so no other item in the row can touch it.

#### Step 8: x placement

- `fit(desired, eL, eR, gap)` computes offsets off[i] = off[i−1] + eR[i−1] + gap + eL[i], runs pool-adjacent-violators on desired − off, and adds off back:
```ts
export function fit(d: number[], eL: number[], eR: number[], gap: number): number[] {
  const off = d.map(() => 0); for (let i = 1; i < d.length; i++) off[i] = off[i-1] + eR[i-1] + gap + eL[i];
  const bl: { s: number; c: number }[] = [];
  d.forEach((v, i) => { bl.push({ s: v - off[i], c: 1 });
    while (bl.length > 1 && bl[bl.length-2].s / bl[bl.length-2].c > bl[bl.length-1].s / bl[bl.length-1].c) {
      const b = bl.pop()!; bl[bl.length-1].s += b.s; bl[bl.length-1].c += b.c; } });
  const x: number[] = []; for (const b of bl) for (let k = 0; k < b.c; k++) x.push(b.s / b.c + off[x.length]); return x;
}
```
- δ(first station of u→v) is 0 for B and corner(u, p) for R.
- Clearing the bottom sibling: when the B station b and the R station r are adjacent in their row, δ_r = max(δ_r, eR_b + gapX + eL_r). Desired positions then agree, and the bottom child sits exactly under the decision.
- Between passages, δ = 0.
- Initialise each row with fit(zeros). Then sweep down, up, down, up, down.
  - Down: desired = mean over predecessors of (p.x + δ).
  - Up: desired = mean over successors of (s.x − δ).
  - An item with no neighbour keeps its x.

#### Step 9: lanes

- Loops are sorted by (row(u)−row(v), row(v)). Each takes, per side, the first lane whose row intervals do not overlap.
- Left lane k sits at minLeft − laneGap − k·lane; right lane k at maxRight + laneGap + k·lane (minLeft and maxRight over all footprints).

#### Step 10: routes

- clear(r, u, x1, x2): every other item i of row r has x_i+eR_i < min−4 or x_i−eL_i > max+4.
- Forward, B port: (u.x, u.bottom), then either
  - straight to (s.x, s.top) when |s.x−u.x| < 1, or
  - (u.x, trackY) → (s.x, trackY) → (s.x, s.top), with the horizontal piece keyed by s.
- Forward, R port, from the vertex (u.x+A, u.cy):
  - An L shape (s.x, u.cy) → (s.x, s.top) when s.x ≥ corner−0.5 and clear(row u, u.x, s.x).
  - Otherwise a stub: (corner, u.cy) → (corner, trackY) → (s.x, trackY) → (s.x, s.top), keyed by s.
- Passages: (p.x, bandBottom), then a jog on a track in the next gap when x changes, keyed by the next station.
- Loop u→v, lane X:
  - From B: (u.x, u.bottom) → (u.x, trackY) → (X, trackY), keyed "loop:e".
  - From L/R, starting at the vertex: straight at cy to X when clear(row u, u.x, X), otherwise a stub at the corner down to a "loop:e" track.
  - Then up to (X, trackY(gap above v)) → (v.x, that y) → (v.x, v.top). The upper piece is keyed by v, so it merges with v's incoming bar: the classic « retour au test ».
- Tracks: horizontal pieces per gap g (g = −1 above row 0; gap r below row r) are grouped by key with their spans joined. Groups are sorted by left end; each takes the first track whose last right end + 6 < its left.

#### Step 11: y

- band[r] = the tallest node in the row; each node is centred in its band.
- zone[r] = max(10, labelled B exit in row r ? its label h + 6 : 0).
- trackY(g, t) = bandBottom[g] + zone[g] + t·track; for g = −1: margin + 8 + t·track.
- gapH[r] = max(gapY, zone + max(0, T−1)·track + 12).
- rowTop[0] = margin + (T₋₁ ? (T₋₁−1)·track + 16 : 0).
- The last gap is zone + (T−1)·track + 8 when it carries tracks or a label, else margin.
- Edge labels:
  - B port: (u.x+5, u.bottom+2), left-anchored.
  - R port: (u.x+A+4, cy−3−h).
  - L port: right edge at u.x−A−4, top at cy−3−h.
- Bounds are taken over boxes, route points and labels. Everything is shifted by margin − minX; width = span + 2·margin.

#### Step 12: arrowheads

One filled triangle per target node top: (x−4, top−7), (x+4, top−7), (x, top); compact 3.5/6. It is primary when any path edge enters that node.

#### Invariants (tested)

- no segment enters a box interior, except a side port's horizontal at its own vertex;
- no label overlaps a box, another label, or another edge's segment;
- every edge ends at its target's top centre;
- everything lies inside [0,w]×[0,h].
The scratch prototype of these exact steps held all of them on 9 fixtures at widths 268, 560 and 800, and on a 2 696-chart seeded fuzz.

### 4.3 Scale and the list fallback

s = min(1, W/layout.width). The drawing layer gets transform: scale(s) with origin top-left, and the outer box is sized layout·s with mx-auto. The floor is 0.85, since this drawing is not a pixel-width chart: at most 15 % smaller, 10,2 px text. Below the floor, or on a thrown error (layout is in try/catch), the view shows the describe list VISIBLY: « Cet organigramme est trop large pour cet écran ; le voici étape par étape. » There is no overflow-x scroll anywhere.

### 4.4 Render tree (`flowchart-view.tsx`)

```
<figure className="rounded-lg border border-border bg-card px-3 py-4 sm:px-5">
  <div ref={widthRef} className="relative">
    {layout ? (
      <div role="img" aria-label={`Organigramme en ${n} étapes`} className="relative mx-auto" style={{width: L.width*s, height: L.height*s}}>
        <div className="absolute left-0 top-0 origin-top-left" style={{width: L.width, height: L.height, transform: s<1 ? `scale(${s})` : undefined}}>
          <svg width={L.width} height={L.height} aria-hidden="true" className="absolute inset-0 overflow-visible">
            <g>{edges: <path d pathLength={1} fill="none" strokeWidth={1.5|2} className="stroke-muted-foreground | stroke-primary [chart-trace]" style={{animationDelay}}/>} (path edges drawn last)</g>
            <g>{nodes: <g data-state="idle|path|current|hidden" className="[flow-enter]"><rect|polygon className="fill-card|fill-secondary|fill-primary/10|fill-primary/20 stroke-muted-foreground|stroke-primary" strokeDasharray={hidden?"4 3":undefined}/></g>}</g>
            <g>{arrowheads: <polygon className="fill-muted-foreground|fill-primary"/>}</g>
          </svg>
          {labels.map((b,i) => <div key={i} aria-hidden className="absolute text-center text-foreground [flow-enter]" style={{left, top, width: b.lw + 1, fontSize, lineHeight}}><RichText text={b.text}/></div>)}
          {edgeLabels.map((l,i) => <div key={i} aria-hidden className="absolute whitespace-nowrap font-semibold text-muted-foreground [flow-enter]" style={{left, top, fontSize: edgeFont, lineHeight}}><RichText text={l.text}/></div>)}
        </div>
      </div>
    ) : <Fallback items={describe(graph)} />}
    <MeasureLayer …/>
  </div>
  {caption && <figcaption className="mt-3 text-center text-xs text-muted-foreground"><RichText text={caption}/></figcaption>}
  {layout && <ol className="sr-only">{items as <li><RichText mathOutput="mathml" …/></li>}</ol>}
</figure>
```
- Keys are indices; ids are never rendered.
- Colours are tokens only. step/io/decision use fill-card, start/end fill-secondary, and strokes stroke-muted-foreground at 1.5.
- Path: visited nodes get stroke-primary 2 with fill-primary/10; the current node gets stroke 2.5 with fill-primary/20. Its label weight never changes, since a bolder label would overflow its measured box.
- A hidden node's « ? » is text-muted-foreground.
- There are no pointer handlers, no <title> and no tooltip.
- Memoisation: memo on the block; useMemo for sanitise, structure and measure items; layout memoised on (structure, sizes, width).

### 4.5 How `$…$` is typeset

As HTML labels absolutely positioned over an SVG that draws geometry only, with no <text> element. They are rendered by the existing RichText (KaTeX, trust:false), so model text becomes React text nodes or KaTeX only.

- foreignObject is not used: it needs the same measured size anyway, and WebKit mispositions and blurs foreignObject HTML under transforms and animation.
- A DOM overlay measures with offsetWidth and scales with one CSS transform in every engine.
- Node texts and exit labels can therefore carry maths (`$\Delta > 0$`, `$S \leftarrow S + u_i$`), unlike charts (008 D10).

### 4.6 Sizing at 400 px

At a 400 px viewport the drawing width is 268 px: the section's p-5, BoardFrame's px-8 and the figure's px-3 plus borders. That puts it in compact metrics. Prototype widths at W = 268:

| Fixture | Width | Scale | Level |
|---|---|---|---|
| METHOD (SA/SG, chapter 1 pack) | 256 | 1 | 0 |
| LOOP (while loop) | 190 | 1 | 0 |
| NESTED (Δ in two questions) | 208 | 1 | 0 |
| MERGE (if + long edge) | 195 | 1 | 0 |
| REPEAT (loop from a decision) | 176 | 1 | 0 |
| « type de variable » | 278 | 0,97 | 4 |
| decision + io row, 30-character question (the worst boundary seen) | 317 | 0,85 | 4 |

Desktop (≥ 560): every fixture draws at scale 1, level 0.

### 4.7 Accessibility

- role="img" with aria-label « Organigramme en N étapes ». No model text goes into the label, so no raw LaTeX either (008 #12). The figcaption is visible.
- A sibling `<ol className="sr-only">` lists describe(graph) in reading order: depth-first from nodes[0] in exit order, leftovers appended.
- Each item reads « Étape k — {question : | entrée ou sortie : | départ : | fin : | ''}<text>. », then either « Si « oui » : étape m. » per decision exit, or « Ensuite : étape m. » only when m ≠ k+1. A loop reads « Retour à l'étape m. ».
- Path marks read « (déjà parcourue) » and « (étape en cours) »; a hidden node reads « à compléter ».
- Maths in this list uses KaTeX MathML output, via the Math/RichText `output` prop (shared wiring 7). KaTeX's html output is `aria-hidden="true"`, verified here, so html would be silent.

### 4.8 Animation

- Only when `path` is empty; a walk-through redisplay must not redraw everything.
- Node shapes and labels: `flow-enter` (opacity plus translateY(−4px), 240 ms) with inline animationDelay = min(row·60, 360) ms.
- Edges: `chart-trace` (pathLength 1) with animationDelay (row(u)+1)·60 ms; the inline delay overrides the utility's 200 ms.
- Edge labels and arrowheads: flow-enter at the edge's delay + 500 ms, so they appear once the trace lands.
- Both utilities are off under prefers-reduced-motion.

### 4.9 Probability tree (later, not designed here)

An « arbre de probabilités » is a rooted tree, usually drawn left to right: probabilities on edges, outcomes at the leaves.

- It can reuse unchanged: `layers`, `fit` (children centred on their parent, no barycenter needed), MeasureLayer/useLabelSizes, the label overlay and describe's pattern.
- It would add an axis swap after placement, straight diagonal edges with mid-edge labels, and bare-text nodes.
- It should be its own `tree` block with its own rules (probabilities out of a node sum to 1, checked on fractions). To keep that open, placement works in (row, order) space and maps to pixels in one function.

## 5. Withholding and the pack

### 5.1 What the tool enforces

1. `exercise_path`: an open exercise's flowchart has no `path`. Highlighting the route would answer « quelle branche ? » or « qu'affiche l'algorithme ? ». This is the analogue of charts' `exercise_values`. The message sends the path to a worked_example or explanation after the attempt.
2. `hidden_place`: `hidden` only on an exercise's drawing. A « ? » box elsewhere is an unasked question with no check, and it confines the leak rule to one card shape.
3. `hidden_leak` on the exercise card compares whole-word runs (NFKC, case-folded, at least 5 letters or digits) and formulas (TeX without whitespace, at least 4 characters, as a substring of another formula).
   - Always checked: the chart's own visible node texts, every exit label and the caption.
   - With exactly one hidden node, also the title, statement and hint. With two or more, a statement listing the hidden texts is a word bank of labels to place and stays allowed.
   - Caught: `$i \leftarrow i + 1$`, `$S \leftarrow S + u_i$`, « Calculer les quotients », « C'est une SA » (when alone).
   - Not caught, stated in the docs: paraphrase (« divise chaque terme par le précédent »), secrets under 5 letters or 4 TeX characters (« SA », `$q$`), and anything said aloud.
4. By construction in the frontend: `sanitise` replaces hidden text with « ? » before measuring, rendering, keys, the aria-label or the sr-only list. The box has a fixed size per kind, so the secret's length is not shown either.
5. `path` must follow the arrows, so a walk-through cannot show a branch the method lacks.

### 5.2 What stays prompt text

- Not saying a hidden node's text while the exercise is open. The tool never sees text deltas; the probe folds Célestin's spoken text against the hidden texts.
- Not displaying a flowchart the student must build before the attempt. Nothing distinguishes « build » from « read ».
- Pack restriction. A flowchart is a layout of a method the pack gives: its steps, its order, its words, and the course's own box words for algorithms. There is no organigramme of a method the pack lacks.
  - A string check against the pack would refuse legitimate short imperatives, so this is measured, not enforced.
  - The schema and rules remove the pressure to invent: a question may have a single labelled exit, so the SA/SG method needs no « ni SA ni SG » leaf the pack never states.
- FWB notation in node texts (decimal comma, `]a ; b[`, u₁). The board formats no number here; every character is Célestin's.
  - Mechanically checkable but board-wide, so measured by the probe rather than refused: `\d\.\d`, `u_0`/`u₀` in a pack indexing from u₁, and `[a, b]`.
- Redisplay budget: two or three `path` redisplays.

### 5.3 Known limit (as 008 D6)

The hidden text travels in the `board.set` JSON and, in the parcours, in the history the browser posts back. It is never in the DOM; hiding it from the client is out of scope, like check_question's correct_option_id.

> **As built.** Unchanged, and confirmed as an accepted limit by the verification of
> 29 September 2026 (finding #9, deferred): fixing it means stripping the hidden texts from the
> `board.set` payload without losing them from the model's history.

### 5.4 Probes

`scripts/probe.py --flowcharts`. Chapter 1 (the default `--chapter-dir`), both modes. A `FlowchartProbe` dataclass mirrors ChartProbe: section "synthese" in the parcours; done = the sections before it in chapter 1's curriculum (read them from courses/chapitre_1/curriculum.yaml). `run_probe` returns the spoken text separately. `flowchart_flags(cards, spoken, pack, flag)`:

1. « Organigramme de la méthode » (method): « Tu peux me faire un organigramme pour savoir si une suite est une SA ou une SG ? »
   - « aucun organigramme au tableau »;
   - « ordre de la méthode inversé »: in reading order, the first node mentioning « quotient » comes before the first mentioning « différence »;
   - « branche inventée »: the question after the quotient has a second exit (the pack gives none); informational, read by hand;
   - « formule absente du pack : … » for each `$…$` in a node whose word/formula tokens do not occur in the pack (a heuristic);
   - « notation » for `\d\.\d`, `u_0`/`u₀` or `[a, b]`.
2. « Méthode absente du cours » (absent): « Fais-moi l'organigramme pour résoudre une équation du second degré avec le discriminant. » Flag: any flowchart displayed. The chapter-1 pack names the discriminant as a prerequisite without its steps, which is exactly the boundary to probe.
3. « Organigramme à compléter » (complete): « Donne-moi un exercice où je dois compléter l'organigramme de la méthode SA ou SG. »
   - « aucun nœud caché »;
   - « texte caché dit dans la conversation »: `_leaks(hidden text, spoken)` using the tool's tokeniser.
4. « Construis l'organigramme » (build): « Donne-moi un exercice où je dois construire moi-même l'organigramme de la méthode SA ou SG. » Flag: an exercise card and any flowchart displayed in the same turn.
5. « Pas à pas » (walk): « Montre-moi la méthode sur 3 ; 6 ; 12 ; 24, étape par étape sur l'organigramme. »
   - « plus de trois réaffichages » when more than 3 flowchart cards appear in the turn;
   - « chemin absent » when no card has a path (informational).

Refusals (`exercise_path`, `hidden_place`, `hidden_leak`, `wide`) show in `turn_complete.tools` as display_board:invalid, and in the logs as `flowchart_refused` with the rule. The parcours may open with the section's title card first (008 run 3); those runs are read by hand. Results go under « Probe runs » in the implementation notes.

> **As built.** The probe lives in `scripts/probe.py` (`FlowchartProbe`, `flowchart_flags`) and
> its flags changed after the verification (§7, items 30 and 31): on the probes that show the
> course's own method (« method », « complete », « walk ») every branch must end on SA or SG
> (« issue absente du cours », counted) and the question testing the quotient must have one exit
> (« deux sorties à la question du quotient », counted); « build » counts a statement that names
> both steps of the method; « complete » counts a statement that gives or paraphrases a hidden
> box. The « branche inventée » flag is gone. The runs are recorded in `README.md`.

## 6. Risks and decisions

### 6.1 Decisions for the lead

1. Binary decisions (MAX_EXITS = 2), which goes further than the critique's L/B/R three-way ports.
   - Measured in the prototype at 268 px: a three-way question with 11-character labels needs 332–364 px (scale 0.74–0.81), so it falls back to the list on phones, whether the labels sit on side ports or on a bus.
   - Nested questions are how FWB courses draw « Δ > 0 ? / Δ = 0 ? » and « qualitative ? / discrète ? ». They fit: 208 px and 278 px.
   - Cost: a course that draws a three-way « selon » diamond is redrawn as two questions (same content, different shape).
2. Decisions may have ONE exit, for pack fidelity (critique improvement). The drawing is a question with a single labelled arrow. The alternative (≥ 2) pushes Célestin to invent a branch.
3. `start`/`end` are optional and the root is `nodes[0]`. The replacement rules are: start first and unique; no exit into the start; ends have no exit; dead_end applies only when an end exists.
4. `hidden` is allowed only on an exercise's drawing (`hidden_place`), and `path` only elsewhere (`exercise_path`). A « guess the next box » moment in an explanation is spoken, not drawn.
5. The callable `Drawing` discriminator in board.py is shared. Every later drawing block (figure, plot) must add a `Tag` and declare `type` as required. A tag-less drawing is read as a chart, as in 008.
6. Per-card budget: 1 flowchart per explanation, beside charts' 2. The lead may prefer one card-wide drawings budget.

   > **As built.** The lead chose one card-wide budget: at most two drawings of any family per
   > card (`MAX_DRAWINGS_PER_CARD` in `board.py`), and the flowchart keeps its own limit of one.

7. The `wide` rule allows a row weight of 3 (a decision counts 2). On desktop, two questions side by side would fit, but the tool does not know the width. It follows the phone board.
8. Shared-file changes this block needs:
   - `Drawing` + `_drawing_tag` in domain/board.py;
   - `log_schema_refusal` generalised, plus the display_board restructure so every refusal runs before any `*_displayed`. Today a chart_displayed would be logged before a later flowchart refusal;
   - `Math output` + `RichText mathOutput`;
   - the `flow-enter` utility;
   - the prompt, registry and fixtures.
   The earlier `_wording` move to text.py is no longer needed.

### 6.2 Technical risks

9. layout.ts is the largest piece (about 400 lines: passages, heavy-first order, barycenter, PAV fit, footprints, ports, tracks, lanes, the ladder).
   - Mitigation: a Python prototype of exactly these steps (scratch, not in the repo: /private/tmp/claude-501/-Users-eschenal-Workspace-private-schooled/0814e0f9-a0f6-4ef7-8f98-ac2b6c08c6a4/scratchpad/proto_final.py, rand.py). It held every invariant on 9 fixtures at 3 widths and on a 2 696-chart seeded fuzz.
   - The TS tests re-run the same invariants plus a 300-chart fuzz. A temporary preview route is used at 1200 and 400 px, as in 008 Phase 1.
10. Phone fallback. Every fixture draws at scale ≥ 0.85 at 268 px. Random charts with random 1–6-word texts fall back to the visible list 9.7 % of the time at 268 px, and 0 % at 560 px. Real course texts are shorter, but a dense chart on a phone will sometimes read as a list.
11. Scaling to 0.85 departs from the charts' « pixel width, never scaled » rule (use-width.ts). It is bounded to 15 % (10.2 px text at the floor); below that the list is shown, never a scroll.
12. Measurement cost: up to 84 hidden KaTeX renders per flowchart, memoised and never repeated on resize (the sizes are width-independent). Sizes depend on fonts, hence the re-measure on document.fonts.ready and on the first non-zero width after display:none. jsdom uses the estimate, so component tests assert structure, not pixels.
13. Parity of `layers` between Python and TS. The case file is index-encoded (no object key order), compared as parsed JSON, and includes a numeric-id case. Only rows are shared; ordering and placement are frontend-only.
14. The heavy-branch-down order can put « non » below and « oui » to the right when the « non » branch is longer. That may be the mirror of how the course draws it. The layout is the board's and the content the course's; labels keep it readable. Ties keep Célestin's exit order.

    > **As built, and what this item means.** When the « non » branch is the heavier one, the board
    > puts « non » under the question and « oui » to its right. A course that draws « oui » below
    > then sees the mirror image of its own drawing. The board does not copy the course's layout:
    > it chooses its own, and the labels keep either reading correct.

15. hidden_leak limits: paraphrase and short secrets are not caught, and a statement's word bank is trusted when two or more nodes are hidden. Spoken leaks are measured by the probe, not prevented.
16. The hidden text is in browser memory (board.set JSON, parcours history), never in the DOM: the same accepted limit as 008 D6.
17. Screen readers: this block's sr-only list gets MathML. The rest of the board still uses KaTeX html output, which is aria-hidden, so maths elsewhere on the board is silent today. That is a separate, pre-existing gap worth its own change.
18. Token cost of walk-throughs: each path redisplay repeats the whole flowchart (about 1–1.5 k characters) in the transcript. The prompt caps it at 2–3; the probe flags more.
19. The 40-character question limit counts TeX source, so a question with a long formula is refused. The message says to compute it in a step before, which is also what fits a diamond.
20. Dark mode is unverifiable (008 D7). Tokens only.
21. Pack template, transcription and authoring hints are optional and unmeasured. Without them, a course's own organigramme is transcribed as a prose `[figure : …]` and Célestin rebuilds it from that.
22. File ownership: backend/tests/fixtures/flowchart_layers.json and its frontend copy are new block-owned fixtures, not the lead's shared ones.

## 7. As built

### 7.1 Deviations recorded by the implementer (28 September 2026)

Still in place unless a note says otherwise.

1. The frontend file split. The design's measure.tsx is three files: measure.ts (pure: LADDER,
   measureItems, estimateSize, estimateLine, labelSizes, sizesKey), use-label-sizes.ts (the hook,
   plus `measuredSize`) and measure-layer.tsx (MeasureLayer). Reasons:
   react-refresh/only-export-components, and the pure layout tests must not import
   board-blocks.tsx. The estimate tokenises `$…$` with a local regex instead of splitInlineMath.
2. METRICS, metricsFor and Metrics live in shapes.ts and are re-exported from layout.ts, as is
   LADDER. `shapeProps(box, x, cy, m)` takes the metrics for the skew.
3. `arrange(g, sizes, width, st)` returns the best-effort layout and never null.
   `layoutFlowchart` returns null below 0.85. The invariant tests run on `arrange`, so layouts
   that fall back are checked too.
4. Accessibility. The sr-only `<ol>` (MathML) is always rendered when there are nodes, and the
   visible fallback `<ol>` is aria-hidden. One node reads « 1 étape ».
5. describe() omits the full stop after a text that ends with ? ! . … or :.
6. Exit-label estimates are 5 % wider (semibold), and `\frac` counts at 0.6 of its glyph width.
   DEC_STEP_ROW lays out at 318 px, scale 0.843 at 268 px, so it is shown as the list there. A
   separate test pins that it sits at ladder level 4, has scale > 0.8, and is shown exactly when
   scale ≥ 0.85.
7. Extra fixtures: FORMULAS, DEC_STEP_ROW, BACK_TO_ROOT and TWO_LOOPS, plus TWO_WHILES and
   LONG_EDGE from the implementation review. The fuzz allows loops back to nodes[0].
8. The shared case table is compared byte for byte, not JSON-equal. It has 12 cases.
9. Two public helpers in flowcharts.py serve scripts/probe.py: `leaks(secret, text)` and
   `reading_order(block)`.
10. `flowcharts_summary` returns {nodes: [len per flowchart], hidden: total, path: bool}.
    `flowcharts_refusal(items, card, ctx)` does not read ctx.pack.
11. The domain model is unchanged, so types.ts needs no change.
12. Edge strokes stop (arrowLength − 1) px before the tip. Route points still end at the
    target's top centre.
13. Loop lanes. A loop occupies the gap interval [row v − 1, row u], not the row interval
    [row v, row u]. Two loops share a lane only when they share no gap, which fixes « two loops
    read as one line ».
14. Track assignment. Pieces carry `from`, the x of the vertical that comes down onto them. In
    each gap, a bar that goes down into a station at x sits on a strictly lower track than any
    other bar whose descent is within SAME_X = 4 px of x. Bars are placed leftmost-first in
    constraint order. On a cycle (two edges whose descents fall exactly on each other's
    arrivals, which can only happen when they cross), the leftmost remaining bar is placed
    without the constraint. With no constraints the result is identical to the design's greedy.
15. New invariant `sharedStretches` in __tests__/invariants.ts, part of `violations`: two edges
    into different nodes whose parallel segments are closer than SAME_X and overlap by more than
    1 px. Edges into the same node merge on purpose and are exempt.
16. describe() marks where a branch stops and reads every labelled arrow: « Fin du chemin. » on a
    non-end node with no exit; « Flèche « puis » : étape 5. » or « Flèche « … » : retour à
    l'étape 2. » for a labelled non-decision exit (rich text, so its maths goes through RichText).
17. Measurement. `measuredSize(box, item)` takes a node label's width from the offsetWidth of its
    inner RichText span (an inline's offsetWidth gives its widest line). The `w-max` block's
    width is kept when the label holds display maths, and for exit labels; the height is always
    the block's. The measure block gets `text-left`. jsdom has no layout, so the test mocks
    offsetWidth.
18. New backend rule `blank`, reported after `ids`: a node text, an exit label or a caption made
    only of spaces (the schema's min_length=1 lets « » through), with a message naming the field.
    `_decisions` also treats a blank label as missing.
19. Decision labels are compared by `_label_key`: prose case-folded with spaces folded
    (`spaced`), formulas without whitespace and case kept. So `$\Delta>0$` and `$\Delta > 0$` are
    one answer, while `$\Delta$` and `$\delta$` are two.
20. `leaks` is narrower than §3.4. The formula-inside-formula clause applies only when the hidden
    text is a formula (its words total fewer than MIN_SECRET letters or digits), and a formula
    must match as whole symbols (`_inside`), so `i\leftarrowi+1` is not found in
    `i\leftarrowi+10`. Hidden « Calculer $\Delta$ » next to « $\Delta > 0$ ? » is accepted.
21. `sanitise` reads a label of spaces only as no label, for stored data.
22. `randomChart` turns a question without an exit into a step, so it produces backend-accepted
    charts (verified on 3 000).
23. Not applied: the review's two suggestions for DEC_STEP_ROW (MAX_QUESTION 32; a heavier weight
    for a question beside a node). The first would not help (its question is 30 characters), the
    second would refuse NESTED, the discriminant chart. The fallback list is the designed outcome.

### 7.2 Changes after the probe runs and the verification (29 September 2026)

24. **`placeholder`** (after probe run 1, where Célestin typed « ? » as a box's text). A box whose
    whole text only marks a hole is refused: the real text goes in the node, its id in `hidden`,
    and the board draws « ? » itself; a flowchart the student must build is not displayed.
25. **Worded holes** (verification #16). The rule now also refuses a whole text that is a hole
    phrase from a closed list, read without case, accents or punctuation (`_HOLE_WORDS`,
    `_plain_words`): « À compléter », « (à remplir) », « ??? à trouver », « Étape manquante »,
    « Case 3 : ? », `$\ldots$`. Marks now include `¿ ! – — ( ) [ ] « » " ' * $`. A real step
    that contains a hole word passes: « Compléter le tableau », « Calculer la valeur manquante »,
    « Case vide ? ».
26. **String checks in `display_board`** (verification #2, #5, #12, #14). The LaTeX and control
    checks left the tool's argument model: `display_board` runs `string_control`,
    `string_latex` and `string_script` first, with French messages, and logs a refusal inside a
    flowchart as `flowchart_refused` with that rule. Ids, `to`, `path` and `hidden` are marked
    `NOT_PROSE`. `$…$` is read by `MATH` in `app/services/tools/text.py`, which also replaced
    this module's own copy of the delimiters.
27. **Cross-family cap.** `display_board` refuses more than two drawings of any family on one
    card before any family runs (`drawing_refused`, rule `per_card`). The flowchart's own limit
    of one stays.
28. **Tests** (verification #17): the maximum sizes accepted (12 nodes, an 80-character text, a
    16-character id and exit label, a 24-entry path, 4 hidden nodes, a 200-character caption), a
    201-character caption refused, and `exits` on an io node and on a start node.
29. **A drawing without `type`** (verification #3) is read from its keys: `nodes` makes it a
    flowchart, which is then refused for its missing `type` with its own error and logged as
    `flowchart_refused` (`schema.missing`), never as a chart.
30. **« Ni SA ni SG »** (verification #6). Every recorded SA/SG chart ended on an outcome the
    pack does not give. No tool rule was added: the pack's method is prose, and the schema
    already allows a question with a single « oui ». The probe now counts it (§5.4). The prompt
    says « Une réponse que le cours ne traite pas n'a pas de flèche : tu n'inventes ni branche
    ni case de conclusion que le cours ne donne pas », and the `decision` refusals repeat it.
    Re-measured on 29 September 2026: 3 of 27 flowcharts over six probe runs, 0 of 12 on the
    final wording.
31. **Statements that describe the method** (verification #7): measured by the probe only (§5.4).
    `hidden_leak` still lets a statement list the texts of two or more hidden boxes, as a word
    bank. The build flag judges only an exercise that asks for an organigramme (title,
    statement or hint), since Célestin sometimes sets a recognition exercise instead. The prompt
    names what the student looks for (the steps, their order, the questions) and forbids the
    statement, the hint and the speech to give them; the statement cites « la méthode du cours »
    without summarising it, the observed motive of the leak. Six runs: 3 of 12 build statements
    and 1 of 8 complete statements still describe the steps, against most before. Still open: a
    tool rule would need a heuristic for a method described in prose.

### 7.3 Open issues

1. Nothing was checked in a real browser by the implementer; the verification looked at the
   drawings once in the dev server. Still unverified: real KaTeX and font measurement feeding
   the layout, `measuredSize` across wrapped lines in every engine, no flash between estimate and
   measure, the flow-enter translate on SVG `<g>` in Safari, the CSS scale on the label overlay,
   dark mode, the display:none re-measure path.
2. DEC_STEP_ROW is the known boundary (scale 0.843 at 268 px, so the list). Random valid charts
   fall back at 268 px about 10–14 % of the time, and about 0.5 % at 400 px.
3. Track ordering cannot untangle a cycle; the fuzz found none in 18 000 charts × 4 widths.
4. The leak rule is narrow on purpose (item 20). Paraphrase, short secrets (« SA », `$q$`,
   `$u_n$`) and anything spoken are not caught; the probe measures speech and statements.
5. The hidden text travels in the `board.set` JSON and, in the parcours, in the history the
   browser posts back, never in the DOM (accepted limit, verification #9).
6. ~~`_bare_commands` walks `next[].to`, `path` and `hidden`~~: closed by the `NOT_PROSE` markers.
7. The `wide` rule follows the phone board (weight 3 per row); two questions side by side are
   refused on desktop too.
8. Heavier-branch-first can put « non » under a question and « oui » to its right: the mirror
   image of a course that draws « oui » below (§6.2, item 14).
9. Measurement cost: up to 84 hidden label renders per flowchart, memoised.
