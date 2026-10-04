# 009 — Drawings on the board: flowcharts, figures and plots

**Status:** implemented on `feature/board-drawings` (29 September 2026). No SDD was used: this
folder holds the reviewed designs instead of a requirements, design and tasks trio.

## What was built, and why

Spec 008 put statistical charts on the board. The material students bring draws much more than
statistics: a method as an organigramme, a triangle with its codage, the solution set of an
inequation on a number line, ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ, the graph of a function or a sequence, the
measurements of a physics experiment. Before 009, Célestin could only describe these in words. 009
adds three drawing blocks next to `chart`:

| Block | What the course calls it | What Célestin gives | Design |
|---|---|---|---|
| `flowchart` | organigramme, algorithme | nodes (`step`, `decision`, `io`, `start`, `end`) with their texts and exits; `path` to walk a method on an example; `hidden` for an exercise « compléter l'organigramme » | [flowchart.md](./flowchart.md) |
| `figure` | figure géométrique, repère, droite graduée, diagramme d'ensembles | named points and the shapes joining them; intervals and marks; sets and their elements | [figure.md](./figure.md) |
| `plot` | graphique d'une fonction, d'une suite, d'une expérience | a window, axis titles with units, curves by expression, sequences by general term, points, broken lines | [plot.md](./plot.md) |

The three blocks keep the product's invariants in the same way charts do:

- **Célestin gives what the course says, never a picture.** He sends data, steps, points and
  expressions, never pixels, colours or notation. The board computes, lays out and draws in the
  course's notation: decimal comma, true minus, `]a ; b[`, `A(2 ; −1)`, u₁.
- **Rules live where they can change.** The card model holds what never changes (types, enums,
  sizes, finite numbers). `display_board` holds the rest, one rule code each, with a French
  message naming the field. A stored card therefore keeps replaying when a rule tightens.
- **A drawing does not give the answer.** Where the tool can see the answer on an exercise's
  drawing, it refuses it:
  - a flowchart's `path`, or a hidden box whose text shows elsewhere on the card;
  - a figure or plot that writes its values;
  - a plot label that states a relation or coordinates.

  What Célestin says, and paraphrase, stay prompt rules, measured by the probe.
- **The pack restriction** is also prompt and probe, except where a mechanical check is sound: a
  plot may not call a function the pack never names (`pack_function`).
- **Nothing on a drawing reacts to the pointer.** The screen-reader description never holds what
  a reading exercise asks for.

How the blocks work today is documented in
[`documentation/tutor-turn-pipeline.md`](../../documentation/tutor-turn-pipeline.md), under
« Board content is typed, not Markdown ». This folder records why they were built that way.

| Where | Flowchart | Figure | Plot |
|---|---|---|---|
| Card model | `backend/app/domain/flowchart.py` | `backend/app/domain/figure.py` | `backend/app/domain/plot.py`, `expression.py` |
| Tool rules | `backend/app/services/tools/flowcharts.py` | `backend/app/services/tools/figures.py` | `backend/app/services/tools/plots.py` |
| Board | `frontend/src/components/celestin/flowchart/` | `frontend/src/components/celestin/figure/` | `frontend/src/components/celestin/plot/` |
| Shared case table | `backend/tests/fixtures/flowchart_layers.json` | `backend/tests/fixtures/figure/capacity.json` | `backend/tests/fixtures/expression_cases.json` |

Shared wiring:

- `backend/app/domain/board.py`: `Drawing` and `_drawing_type`.
- `backend/app/domain/prose.py`: `NOT_PROSE`.
- `backend/app/services/tools/board.py`: `_FAMILIES`, the string checks and the cap across
  families.
- `backend/app/services/tools/text.py`: `MATH`, `JS_SPACE`, `math_tex` and `spaced`.
- `frontend/src/components/celestin/charts/format.ts`: `formatPair`, `formatBound` and
  `formatInterval`.
- `backend/scripts/probe.py`: `--flowcharts`, `--figures` and `--plots`.
- `backend/prompts/`: the tutor prompt's drawing bullets, the pack templates, the transcription
  and authoring prompts.

## Why there is no requirements, design and tasks trio

The user asked for this work to skip the SDD process. There was no `/sdd:requirement`,
`/sdd:design` or `/sdd:plan`, so this folder deliberately has no `requirements.md`, `design.md` or
`tasks.md`. The process was this instead:

1. A designer agent wrote each block's design.
2. The design was critiqued, revised and prototyped in scratch code.
3. The lead reviewed it.
4. Three implementers built the blocks in parallel against those designs.
5. The lead wired the shared parts: the discriminator, the dispatch table, the prompt, the probes
   and the fixture chapters.

The reviewed designs and the implementers' deviation notes existed only in a session scratchpad.
The verification of 29 September 2026 asked to keep them (finding #8), so they are archived here,
one file per block:

- **Sections 1 to 6** are the reviewed design as written: summary, model, tool rules, rendering,
  withholding and the pack, risks. A note marked « As built » says where the code differs.
- **Section 7** lists the deviations: the implementer's, then the changes made after the probe
  runs and the verification.

Source comments cite these files, for example `plot.md §2.2` for the expression grammar.

## The lead's decisions

1. **One `Drawing` union with a callable discriminator.** A worked example's or an exercise's
   `drawing` is `Drawing` in `app/domain/board.py`, a union of the four drawing blocks picked by
   `_drawing_type`. Spec 008 let a chart drawing leave `type` out, so that must keep validating.
   Every later block therefore declares `type` as required.

   A drawing without `type` was first read as a chart, whatever it held. Since the verification
   (finding #3), it is read from its keys: `chart`, `figure`, `nodes` (a flowchart), or `x_range`,
   `y_range` or `curves` (a plot). It falls back to a chart only when no key tells. A figure,
   plot or flowchart sent without `type` is then refused for the missing tag, with its own error.
2. **One dispatch table, `_FAMILIES`** in `app/services/tools/board.py`. It is keyed by the block's
   `type` and holds the block class, its refusal function `(items, card, ctx)` and its log summary.
   - Every family on a card is checked before anything is logged, so a refused card logs no
     `*_displayed`.
   - `log_schema_refusal` reads the family at the union tag's fixed place in the Pydantic error's
     `loc`, never elsewhere: a figure point may be called « chart ».
   - Adding a drawing block takes a `Tag` in `Drawing`, a member of `Block` and a row in
     `_FAMILIES`.
3. **At most two drawings per card, of any family** (`MAX_DRAWINGS_PER_CARD`), refused first and
   logged as `drawing_refused` with rule `per_card`. The designs gave each family its own limit.
   Those limits could no longer fire once the shared cap ran first, so they were removed from
   charts, figures and plots (finding #10). The flowchart keeps its own limit of one per card.
4. **Merged prompt bullets.** Each design proposed its own tutor-prompt bullets. `tutor.fr.md`
   has one set instead:
   - a general bullet naming the four blocks and where a drawing sits;
   - the rules they share: the course's representations and conventions only, no answer on an
     open exercise's drawing, a drawing the student must build shown only after the attempt,
     two or three redisplays at most;
   - one bullet per block.

   The voice block has a single line for all drawings: « Un dessin ne se lit pas valeur par
   valeur, ni case par case ».
5. **Notation in labels: a plot only on an exercise, a figure everywhere.**
   - A figure refuses coordinates or an interval written by hand in any label or caption, on
     every card (`label_notation`). The board writes them itself with `show_values`.
   - A plot refuses them only on an exercise's drawing (`exercise_text`). A plot's labels name
     curves and quantities, so a notation check elsewhere would mostly catch false positives.

   The difference is deliberate.
6. **String checks in `display_board`.** Three rules refuse text the board would show raw:
   - `string_control`: a JSON escape that ate a LaTeX backslash;
   - `string_latex`: a LaTeX command outside `$…$`;
   - `string_script`: a bare subscript or superscript.

   They started on the tool's argument model with English messages. Since the verification
   (findings #2, #5, #12 and #14), they run in `display_board` on the parsed card, with French
   messages. A refusal inside a drawing is logged under the drawing's family. Which fields are
   not prose is marked on the models (`NOT_PROSE`, `app/domain/prose.py`), not listed by name.
7. **The flowchart `placeholder` rule.** In probe run 1, Célestin typed « ? » as a box's text to
   make an exercise. The tool now refuses a box whose whole text only marks a hole. The real text
   goes in the node and its id in `hidden`, and the board draws « ? » itself, so the leak rule
   can check the hidden texts. Since the verification (finding #16), the rule also refuses worded
   holes: « À compléter », « Étape manquante ».
8. **Number-line bound dots.** A number placed on an interval's bound keeps its tick and label
   but gets no dot, in every convention. The bound's own bracket, dot or hatching says whether
   it is included, and a filled dot on an excluded bound would say the opposite. Probe run 1
   caught it in the brackets convention.

Also decided:

- Every text Célestin writes on these three blocks is an HTML layer over an SVG that draws geometry
  only. Their labels may therefore carry `$…$`; charts keep 008's D10.
- Screen-reader text uses `RichText mathOutput="mathml"`.
- Where a tool rule depends on how the board lays something out or parses it, the rule and the
  board share one JSON case table, and the frontend holds a byte-identical copy.
- The pack template, the transcription prompt and the authoring prompt gained lines for
  organigrammes, figures and graphs.
- Three hand-checked fixture chapters were added for the probes:
  `backend/tests/fixtures/chapters/geometrie_analytique/`, `inequations/` and `mru/`.

## Probe runs

Both runs were made on 29 September 2026 with `uv run python -m scripts.probe --charts`,
`--flowcharts`, `--figures` and `--plots`. Each drawing probe runs in both modes (parcours and
discussion). A flag ending « (à lire) » points at something to read and is not counted. A
reviewer then read every transcript.

**Run 1** (with `authoring_eval` and `document_eval`).

| Set | Counted flags | What the transcript review found |
|---|---|---|
| charts | 2 of 12: in the parcours, « Histogramme du cours » and « Polygone cumulé du cours » showed no chart that turn | Probe artefacts: the parcours opened with the section's title card first. Minor prompt points: naming a chart's parts in the course's words, and an exercise's `hint` shows at once. |
| flowcharts | 1 of 10: in the parcours, « Construis l'organigramme » showed a flowchart while the exercise asked to build it | Real failures: the hidden boxes were typed as « ? » text; a « compléter » statement spelled out the hidden questions; a « construire » statement described the drawing. The « branche inventée » flag (à lire) fired once. |
| figures | 2 of 14: « Hachure A », in both modes | In the parcours, the title card came first (an artefact). In the discussion, the zone `[A]` alone was hatched for « tout A », a real failure. Also real: marks on an interval's bounds drew filled dots in the brackets convention (« Lis l'intervalle » in both modes, « Convention absente » in the discussion). |
| plots | 1 of 14: in the parcours, « Suite en vagues » (title card first, an artefact) | Real: a `\Delta` with a single backslash arrived as a control character. Minor: a bare `u_n` in a plot's titles showed raw. |

The other scripts in this run passed:

- `authoring_eval`: 4 of 4 materials authored (0,53 USD).
- `document_eval`: acceptance OK on the 16-page chapter 1 PDF (1,18 USD).

**Fixes between the runs.**

- In the tool: the control-character check (`string_control`), the bare-script check
  (`string_script`) and the flowchart `placeholder` rule.
- On the board: no mark dot on an interval's bound, in any convention.
- In the prompt's drawing bullets:
  - hatching a whole set means hatching each of its zones, with `[["A"], ["A", "B"]]` as the
    example;
  - a hidden box keeps its real text;
  - a flowchart the student must build has no `drawing`;
  - an exercise statement does not describe the drawing it asks for.

**Run 2** (with `smoke` and `voice_smoke`).

| Set | Counted flags | Informational (à lire) |
|---|---|---|
| charts | 1 of 12: in the parcours, « Polygone cumulé du cours » showed no chart that turn | — |
| flowcharts | 0 of 10 | « chemin absent » in the parcours « Pas à pas »; « branche inventée » in the discussion « Organigramme de la méthode » |
| figures | 0 of 14 | « aucune droite graduée » in the parcours « Convention absente » |
| plots | 2 of 14: « aucun graphique au tableau » in the parcours « Graphique de l'expérience » and the discussion « Graphique d'une SA » | — |

- `smoke`: cache OK. Turn 2 had 26 475 cached tokens in the parcours and 25 749 in a discussion;
  the drawing blocks roughly doubled the board declarations.
- `voice_smoke`: OK. The Realtime session accepts the schema, including the figure's point-name
  key pattern.

The verification then re-read the run 2 transcripts:

- All five SA/SG flowcharts ended on « Ni SA ni SG », an outcome the pack does not give. The
  flag caught two of them (finding #6).
- Flowchart exercise statements described the method (finding #7).

The probe flags were corrected afterwards (findings #6, #7 and #11), but **no paid run has been
made since**. As the verification recommended, the next step is to run `--flowcharts` and
`--figures` again (a few cents) and read the new counted flags:

- « issue absente du cours » and « deux sorties à la question du quotient » (method, complete and
  walk);
- « énoncé qui décrit les étapes de la méthode à construire » (build);
- « case cachée décrite dans l'énoncé » (complete).

## The verification (29 September 2026)

The verification was a code review and a compliance check against these designs, the product
invariants and the 008 conventions. Its baseline was 1 582 backend and 967 frontend tests
passing. Every finding was either fixed on the branch, recorded here, or deferred:

| # | Finding | Outcome |
|---|---|---|
| 1 | High. A hatched number line with two unlabelled intervals hatched the whole axis. | Fixed. Hatching belongs to a lane: the complement of the union of that lane's pieces (`figure/line.ts`, `number-line.tsx`). The adversarial verify then caught a regression (a hatched line with marks but no interval hatched everything): a lane with no piece now hatches nothing. And under hatching the unlabelled intervals are one set (one group, one lane, one notation), so an exercise and its correction with `show_values` hatch the same thing; the tool's `union` rule refuses such pieces when they meet. Checked in the browser. [figure.md](./figure.md) §4.5 and §7, item 21. |
| 2 | High. `\neq`, `\notin`, `\nu`… with a single backslash arrived as a newline and passed. | Fixed. A newline inside LaTeX followed by a KaTeX command's letters is a lost backslash (`_lost_backslash`, `_ESCAPABLE` in `tools/board.py`). |
| 3 | A figure, plot or flowchart drawing without `type` was checked as a chart. | Fixed. `_DRAWING_KEYS` in `domain/board.py`. |
| 4 | `PACK_WORDS` matched everyday words (« tangente », « exponentiel »). | Fixed. Each entry names the function; 44 pack sentences test it. [plot.md](./plot.md) §5.3. |
| 5 | A negative exponent outside `$…$` (« m·s^-2 ») passed. | Fixed in `_SCRIPT`, which now also catches `^{` and `_{`. |
| 6 | Célestin invents « Ni SA ni SG » in every SA/SG flowchart. | Probe fixed: new counted flags. No tool rule, because the pack's method is prose. The prompt says an answer the course does not treat has no arrow, and so do the `decision` refusals. Re-measured on 29 September 2026: 3 of 27 flowcharts drawn over six `probe --flowcharts` runs (0 of 12 on the prompt as committed), against every one before. [flowchart.md](./flowchart.md) §7, item 30. |
| 7 | Flowchart exercise statements describe the method. | Probe fixed: new counted flags. The build flag now judges only an exercise that asks for an organigramme, so a recognition exercise set instead is not counted. The prompt was reworded to say why: the steps, their order and the questions are what the student looks for, so neither the statement, the hint nor Célestin's speech gives them; the statement names the method (« avec la méthode du cours ») without summarising it. Re-measured over six runs: 3 of 12 build statements and 1 of 8 complete statements still describe the steps, against most before. **Open**: no tool rule, since telling a described method from a legitimate statement in prose needs a heuristic (« Applique ensuite ton organigramme… » is fine). [flowchart.md](./flowchart.md) §7, item 31. |
| 8 | Source comments cite designs that are not in the repository. | Fixed: this folder, and the comments now point to it. |
| 9 | Hidden flowchart texts reach the browser in the `board.set` payload (never the DOM). | **Deferred**, an accepted limit like a check question's `correct_option_id` (008 D6). Fixing it means stripping the texts from the payload without losing them from the model's history. |
| 10 | The figure and plot per-card limits could not fire. | Fixed. Removed from `charts.py`, `figures.py` and `plots.py`; the cap across families is the rule. |
| 11 | The probe missed `drawing_refused`. | Fixed. `_BOARD_EVENT` and `refusals()` list every `*_refused`, including `drawing: per_card` and the string rules. |
| 12 | A tab or a CRLF in prose was refused as a lost backslash. | Fixed. A tab or carriage return counts only before a command or inside LaTeX; CRLF and tabs before other words are accepted. A tab before « o » or « au » is still refused (as `\to`, `\tau`): a deliberate trade-off, since a model writes those commands far more often than such a tab. The `$…$` spans are paired on RichText's price rule, so « Coût 5$ et $x \neq y$ » still finds the lost `\neq`. |
| 13 | `gives_away` missed ⩽ and ⩾. | Fixed, with ≦ ≧ `\leqq` `\geqq`. |
| 14 | English refusal wording; LaTeX refusals inside a drawing counted under no family. | Fixed (decision 6 above). |
| 15 | The prompt no longer said that `show_values` is what makes the board write coordinates. | Fixed in `tutor.fr.md` (« quand `show_values` est vrai, il écrit lui-même les coordonnées et les intervalles : jamais toi, dans une étiquette »). |
| 16 | Four smaller gaps: worded placeholders; the number line's spoken range computed at 400 px; `pack_function` reading only `expr`, undocumented; the new sub-models not re-exported. | Fixed. Worded holes are refused; the description gives no range; the limit is documented ([plot.md](./plot.md) §5.3 and `documentation/`); the sub-models are re-exported from `app/api/schemas/board.py`. |
| 17 | Test gaps and duplicated code. | Fixed. Boundary tests (12 nodes, `orthonormal` at 0,4 and 2, depth 24, circle slack). One `MATH` in `text.py`. `formatPair`, `formatBound` and `formatInterval` in `charts/format.ts`. `NOT_PROSE` markers instead of a list of names. One parse per plot expression. |
| 18 | Minor plot rendering deviations were not recorded. | Recorded in [plot.md](./plot.md) §7.2. The arrow head is 7 × 7 px (not 6 × 4); the x tick labels sit 16 px under the axis (not 12); label spans have no `maxWidth`. |

After the fixes, the backend suite passes 1 871 tests and the `celestin` components 891. `tsc`
passes and `npm run lint` reports no errors.

## Known limits and what is still unverified

- **Not checked** since the fixes: dark mode, a real lesson with a signed-in student, and a voice
  turn that displays a drawing. The latest number-line changes have not been looked at visually:
  the per-lane hatching, and no dot on a bound.
- **Estimated sizes.** The layouts were tested under jsdom on estimated sizes. Real fonts and
  KaTeX metrics decide in the browser. Each block's manual checklist in
  `documentation/tutor-turn-pipeline.md` is what to run.
- **Leaks the tool cannot see.** Hidden texts travel in the `board.set` payload (finding #9).
  `hidden_leak` misses paraphrase and short secrets. `exercise_text` misses a bare number.
  `pack_function` misses a function drawn from computed points.
- **Schema size.** The board declarations are about 30 000 characters and sit in the cached
  prefix.

## What 009 changes in spec 008

- **The card cap.** 008's `charts_refusal` refused a third chart with `per_card` (008 design
  §3.3). That rule is gone: the cap is `display_board`'s, across families.
- **The LaTeX check.** 008's `_maths_is_delimited` on `DisplayBoardArgs` (008 design §2) is
  replaced by the string checks in `display_board`.
- **The drawing field.** `drawing: ChartBlock | None` became the `Drawing` union.
- **`label_math` stays for charts** (008 D10). Chart labels are SVG text, so KaTeX cannot typeset
  them there.
- **`charts/format.ts`.** `classLabel` now uses the shared `formatInterval`, and the file also
  holds `formatPair` and `formatBound` for figures and plots.
