# The tutor turn pipeline

One learner message in, streamed text and board cards out. This is the path every future tutor
capability will extend, so it is worth knowing where each concern lives.

## The shape

```
browser                     backend
───────                     ───────
useTutorSession
  history[] ──POST /api/chat──▶ chat controller       validate, frame SSE
                                  │
                                  ▼
                               TutorService           the round loop
                                  ├─ PromptService    tutor + subject prompts + pack
                                  ├─ ToolRegistry     declare, validate, dispatch
                                  └─ LLMClient ──────▶ the tutor role's client (OpenAI Responses, or any server
                                                         that speaks it or Chat Completions; store=false)
                                  │
  ◀────── text/event-stream ──────┘
```

The browser owns the conversation. There is no `previous_response_id`; the whole transcript is
posted back on every turn as `{course_id, chapter_id, history}`, and `store=false` means nothing is
retained upstream either. A reload starts a fresh conversation by design. What survives is the
chapter progress, which since spec 004 the server owns: the controller loads the student's
`{done, active}` record for the chapter, binds the store to the turn context, and the section tools
persist their transition before the event is emitted (see
[accounts-and-courses.md](./accounts-and-courses.md)). The request needs the signed-in student who
owns the course, and a chapter with content (`409 chapter_not_ready` otherwise).

## What the model receives

Assembled by `app/services/prompt_service.py`, in this order, every round:

1. A `developer` message carrying a `prompt_cache_breakpoint`, in four layers: the tutor prompt
   `backend/prompts/tutor.fr.md` (no subject and no mode in it), with the course's subject prompt
   (`backend/prompts/subjects/<subject>.fr.md`) at `<!-- SUBJECT -->`, the chapter's pack (from the
   database, owner-checked) at `<!-- COURSE_PACK -->`, the curriculum overview at
   `<!-- CURRICULUM -->`, and the mode's two files (`backend/prompts/modes/<mode>.fr.md` and
   `<mode>.opening.fr.md`) at `<!-- MODE -->` and `<!-- MODE_OPENING -->` (see
   [discussion.md](./discussion.md)). Both prompt files may have a `<!-- VOICE -->` block; each is stripped here
   (`render_system_text(voice=False)`) and only sent to a Realtime session (see
   [voice.md](./voice.md)). A sha256 fixture pins the text rendering for chapter 1. In an English
   course every file above is its `*.en.md` twin and the path overview, the state message and the
   tool declarations are the English ones (`chapter.language`, `ctx.language`); the English
   rendering has its own pins (`system_text_sha_en*.txt`). See [course-language.md](./course-language.md).
2. Tool declarations for the mode, in a fixed order: the two board tools, then — in the parcours
   only — the two section tools and `propose_next_step`. A discussion is offered the board pair
   and nothing else, so the declarations it shares with the parcours keep their exact bytes.
3. The transcript, oldest first.
4. A short `developer` message with the date and time in the learner's timezone (`TIMEZONE`,
   default Europe/Brussels) and the state of the path (« État du parcours »), rendered from the
   stored progress. Both change every turn, which is exactly why they come last: nothing
   that varies may sit in front of the cache breakpoint.

**This ordering is the single most consequential detail in the backend.** The prefix for chapter 1 is
about 13,500 tokens and is re-sent on every round. OpenAI's automatic caching matches on an exact prefix (another provider caches by its own rules, or not at all; the breakpoint field is sent to OpenAI only, spec 014), so as
long as nothing varying drifts in front of the breakpoint, all of it bills at a tenth of the input
rate. Measured on a real session: 13,516 input tokens cached on the second turn (16 September 2026).
Editing a chapter's content changes its prefix once; other chapters, and every chapter of the same
subject for the shared layers, are unaffected. Since spec 007 the mode sits in front of the
breakpoint too, so a chapter has **one cached prefix per mode**: the cost is one uncached read per
mode switch, and `scripts/smoke.py` now runs two turns in each mode and fails on a cache miss in
either (measured 20 September 2026: 13 512 cached in the parcours, 12 747 in a discussion; on
29 September 2026, with the four drawing blocks and their prompt: 26 475 and 25 749, the board
declarations being about 30 000 characters). `scripts/smoke.py` prints the current figures.

Two consequences that are easy to violate by accident:

- The prompt goes in a developer message, not the top-level `instructions` field, because
  `instructions` cannot carry a cache breakpoint.
- Renaming a tool, editing a tool description, or reordering the declarations invalidates the cache
  for every session.
- `registry.realtime_declarations()` must stay equal to `declarations()` minus `strict`; a test
  and a snapshot enforce it, so the voice channel cannot drift from the text channel.

`cached_tokens` is logged on every turn. A persistent zero means something upstream of the
breakpoint is varying; `scripts/smoke.py` fails loudly on exactly that.

## The round loop

`app/services/tutor_service.py`. Each round streams a model response, collecting text and tool
calls. If no tool was called, the turn ends. Otherwise every call is validated and executed with a
`TurnContext` (the curriculum and the request's progress), its result appended, and another round
begins. A successful section tool commits its transition through the context (`ctx.commit`: persist, then
adopt) before the next call, so « complete 5, then start 6 » inside one turn sees the new state; a
failed write is a tool error and no event. `MAX_TOOL_ROUNDS` bounds it; hitting the bound ends the
turn cleanly with `reason: max_rounds` rather than hanging.

A malformed tool call is **not** an error. The validation message goes back to the model as the tool
result, and it corrects itself inside the same turn. This is load-bearing: `display_board` is
declared non-strict, because a discriminated union over six card shapes does not fit strict mode's
requirement that every field be required. Validation is ours either way.

The mapping from a tool outcome to the event the browser receives lives in one function,
`app/services/tool_events.py: event_of`, shared with the voice tool endpoint, so both channels show
the learner the same thing for the same call.

`registry.execute` also refuses any tool outside the turn's mode. That is not belt-and-braces:
`/api/voice/tool` takes a tool name from the browser, so the gate is what makes the mode a
server-side fact rather than a prompt-level hope.

Board tools have no server-side effect. They validate, and return the card to emit. The browser holds
the board, so a failed turn cannot corrupt it. Section tools are the same shape with one addition:
their result text (the section brief, or the next section) goes back to the model as
`{"ok": true, "result": …}`, and on later turns `registry.replay_output` recomputes that text from
the curriculum, so the model keeps the beats in front of it without the browser ever seeing them.

## The SSE contract

`POST /api/chat` takes `{course_id, chapter_id, history}` and returns `text/event-stream`;
`POST /api/discussion/turn` takes `{course_id, chapter_id, conversation_id, message}` and returns
the same stream, framed by the same helper (`app/api/sse.py: stream_turn`). A discussion simply
never emits the three path events. Nine events, and this
set is a two-sided contract:
changing it means changing `frontend/src/lib/tutor/types.ts`, the golden transcript tests in
`backend/tests/integration/test_chat_endpoint.py`, and the design document together.

| Event | Data | Effect |
|---|---|---|
| `turn.start` | `turn_id` | turn is in flight |
| `text.delta` | `block_id`, `text` | append to the entry for that block, creating it on first delta |
| `board.set` | `card`, `marker` | render the card, add it to the strip, insert the marker |
| `board.clear` | `marker` | empty the board, keep the strip |
| `section.start` | `section_id`, `review`, `marker` | set the active section unless it is a review, insert the marker |
| `section.done` | `section_id`, `next_section_id`, `marker` | move the section to done, clear active, insert the marker |
| `step.ready` | `marker` | light the « Étape suivante » button on the board until the next card or turn |
| `turn.end` | `reason`, `usage` | `end`, `max_rounds` or `cancelled` |
| `error` | `code`, `message` | French message, transcript preserved |

`block_id` is what keeps ordering honest: each contiguous run of text between tool calls is its own
block, so "text, board, more text" lands as three ordered entries rather than one merged blob.

Tool arguments are deliberately **not** streamed. They are buffered until complete, because a tool
cannot execute on half a JSON object. Prose appears progressively; a board card appears at once.

## Errors

The split is whether the first byte has gone out.

- **Before**: configuration and resource failures become HTTP status codes with a French JSON body.
  A chapter not owned is a 404, a chapter without content a 409, a missing prompt file or a stored
  curriculum that no longer validates a 500, and the turn never starts. An
  inconsistent `progress` is not an error: unknown ids are dropped and an `active` that is unknown
  or already done is cleared, with a warning in the log.
- **After**: the status line is already 200, so everything becomes an `error` event followed by
  `turn.end`. The learner's message stays in the transcript and retry works without retyping.

Client-visible messages are French and generic. Stack traces, prompt content, pack content and key
material stay in the logs.

## Board content is typed, not Markdown

Cards are structured blocks (`text`, `formula`, `quote`, `note`, `definition`, and four drawing
blocks: `chart`, `flowchart`, `figure`, `plot`), with `$…$` for inline maths inside
prose. Nothing the model writes is ever turned into HTML: prose becomes React text nodes and maths
goes through KaTeX with `trust: false`. Rendering model-authored Markdown would mean an HTML pipeline
and a sanitizer, which is an injection surface this design simply does not have.

Some text would show raw on the board, so `display_board` refuses it before anything else, as a
French tool error that names every field at fault, and the model rewrites the card. There are three
string checks, run in this order; the first one any string fails refuses the card:

| Rule | Refused when |
|---|---|
| `string_control` | a control character stands for a LaTeX command whose backslash the JSON ate (below) |
| `string_latex` | a LaTeX command outside `$…$` in prose (a caption reading `1 ; 2 ; 3 ; \dots`) |
| `string_script` | a bare subscript or superscript in prose: `u_n`, `x^2`, `m·s^-2`, `10^-3`, `x_{1}`, `^{2}` |

The model writes a LaTeX command with a single backslash in its JSON, and the JSON decoder reads the
backslash as an escape: `\frac` becomes a form feed and `rac`, `\beta` a backspace and `eta`, `\text` a
tab and `ext`, `\neq` a newline and `eq`. A form feed, a backspace or any other control character is
refused wherever it is. A newline, a tab or a carriage return is ordinary in prose, so there:

- a newline counts only inside LaTeX (a `$…$` span or a field that is not prose), and only when the
  letters after it complete a KaTeX command (`_ESCAPABLE`, taken from KaTeX's own tables). So
  « CE : $q \neq 1$ » whose `\n` arrived as a newline is refused, and a new line of prose starting
  « nombre » is not. The `$…$` spans are paired as RichText pairs them: a `$` right after a digit is
  a price and never opens maths, so « Coût 5$ et $x \neq y$ » still finds the lost `\neq`;
- a tab or a carriage return counts when it starts a known command (`\times`, `\to`, `\tau`,
  `\theta`, `\rightarrow`…), or anywhere inside LaTeX. This refuses a real tab before « o » or
  « au » too: a deliberate trade-off, since a model writes `\to` and `\tau` far more often;
- a CRLF line ending and a tab before any other word in prose are accepted.

The message tells the model to double the backslash; a probe run caught `\Delta` arriving this way.

The checks run in `display_board`, on the card once Pydantic has parsed it, not as a validator on
the card model: a stored transcript replays through the card model, which never ran them, so it
keeps replaying. They walk
the card once and take each string's maths out once (`_strings_refusal`). A string inside a drawing
that fails a check is logged as `<family>_refused` with that rule, once per family involved; a
failure in a text block or in the card's own fields is not logged.

Which strings are prose is marked on the models, not listed by name: a field whose strings are raw
LaTeX, ids or an expression carries `NOT_PROSE` (`app/domain/prose.py`), and a `Literal` field
(`kind`, `draw`, `closed`…) is never prose. The marked fields are `tex` (formula, quote, step), an
option's `id` and `correct_option_id`, a flowchart's node `id`, `to`, `path` and `hidden`, a figure
shape's `of` (point names such as `A_1`), a figure set's `id`, `within` and `shade`, and a plot's
`expr` (its own parser gives the better message). A dict's keys are names, never walked: a figure's
points are keyed by `A_1`.

`$…$` is found by `MATH` in `app/services/tools/text.py`, the backend's one copy of the delimiters the
board's `RichText` uses: `$$…$$`, or `$…$` neither opening nor closing on whitespace, where
whitespace is JavaScript's `\s` (`JS_SPACE`), not Python's. The board's string checks, the flowchart
rules, the figure's label widths and `scripts/probe.py` all read it (`tests/unit/test_text.py`
holds them to the one pattern).

### Definitions are checked against the pack

A `definition` block holds one to six entries, each a `term` and the `text` defining it; related
terms (population, échantillon, individu) share one block. The board renders it as one highlighted
panel headed « Définition(s) », a glossary with the term in a column on the left and in bold where it
first appears in its definition (`markTerm` in `board-blocks.tsx`, ignoring case and runs of
whitespace, never inside maths). No markup comes from the model: the bold is derived from `term`.

`display_board` refuses, as a tool error the model corrects:

- an entry whose `term` does not appear in its `text` (same comparison as the board), and
- an entry whose `text` is not in the chapter's pack. "Word for word" is compared on letters and
  digits only, after dropping LaTeX commands, NFKC-folding and lower-casing, so apostrophes,
  spacing, Markdown emphasis and notation (`$u_n$` against `uₙ`, `\neq` against `≠`) may differ
  while the wording may not. A reworded definition belongs in a `text` block.

The pack reaches the handler as `TurnContext.pack`, set by `load_context` for both modes; with no
pack (unit tests, some scripts) only the term is checked. Like the LaTeX check, this runs when the
tool runs, so a stored card keeps replaying after the pack is edited. `quote` stays for the rest of
what the course highlights: formulas and verbatim sentences that are not definitions, unchecked.

### Charts are drawn from statistics (spec 008)

A `chart` block (`app/domain/chart.py`) is `{"type": "chart", "chart": {...}}`, the inner object a
union on `kind`:

| `kind` | The course's name | Célestin gives |
|---|---|---|
| `bars` | diagramme en barres (qualitative) | `categories`, `values` |
| `sticks` | diagramme en bâtons (discrete), `polygon` over the sticks | `x`, `values` |
| `histogram` | histogramme, `polygon` `none` / `open` / `closed`, `bars` | `bounds` (n + 1), `values` (n), `closed`, `reference_amplitude` |
| `cumulative` | polygone des effectifs / fréquences cumulés, `increasing` or `decreasing` | `bounds`, `values` per class |
| `pie` | diagramme circulaire | `categories`, `values` |
| `box` | boîte à moustaches, 1–4 boxes | `minimum`, `q1`, `median`, `q3`, `maximum` |

Counting charts carry a `measure` (`effectif`, `frequence`, `pourcentage`), axis titles (not the pie), a caption
and `show_values`. An `explanation` takes charts among its blocks (two drawings at most, of any
kind, per card); a `worked_example` and an `exercise` take one as `drawing`, drawn under the
statement. Where a block can sit on a card
is `card_blocks(card)` in `app/domain/board.py`, read by the tool's rules and by `scripts/probe.py`.

Célestin never gives geometry, and the board computes only what has a single definition: cumulative
sums, sector angles, and a histogram's areas (height = value × reference / amplitude, the
reference defaulting to the smallest amplitude). Quartiles, grouped medians and means come from
Célestin, following the pack.

Validation is split like the rest of the board. The card model holds what never changes (types,
enums, sizes, finite non-negative values). `display_board` holds the rest in
`app/services/tools/charts.py`, one rule code each: `lengths`, `order`, `repeated`,
`numeric_categories` (a bar chart whose categories are all numbers is a discrete variable: sticks),
`exercise_values` (an exercise's chart may not write its values while the exercise is open), `integers`
(an `effectif` is whole), `sum` (fréquences to 1, percentages to 100, with a rounding slack per
value), `empty`, `box_order`, `layers`, `reference` (only for unequal classes) and `label_math`
(labels are plain text). How many charts a card holds is `display_board`'s cap across drawing
families (below), so `charts.py` has no `per_card` of its own any more. A refusal is a French tool
result naming the field.
The handler logs `chart_displayed` (`user_id`, `chapter_id`, `mode`, `kinds`) and `chart_refused`
(the same ids and the `rule`); never a label, title or value. A chart the card model refuses never
reaches the handler, so the registry's `on_invalid` hook logs it as `chart_refused` with
`rule: schema.<pydantic error type>` (`schema.greater_than_equal` for a negative value).

For classes (`histogram`, `cumulative`), `values` is one count or fréquence per class. A pack often
gives the course's chart as bar heights or cumulated points; the schema's field description and the
tutor prompt both say to pass the per-class values, since the board computes heights and cumulated
sums itself (`probe --charts` checks it on the course's own histogram and cumulative polygon).

The frontend cleans a chart once (`sanitise`: lists cut to matching lengths, bad numbers to 0,
classes stopped at the first bad bound) and draws every kind with its own SVG
(`frontend/src/components/celestin/charts/`), at the
measured pixel width, in the course's notation: decimal comma, `12,5 %` (on a percentage axis too),
classes as `[a ; b[`, a space between thousands from five digits on (a year stays `2018`).
Nothing on a chart reacts to the pointer. Values are written only with `show_values`, and the
screen-reader table follows the same rule, so a reading exercise does not carry its answers in the
page.

#### Manual checklist — a statistics lesson

1. Seed or open a statistics chapter (`backend/tests/fixtures/chapters/statistique` is a ready one).
2. In the « Représenter une série » section, Célestin shows the course's charts in explanations; the
   histogram of unequal classes has its areas, not its counts, as heights.
3. Ask for a reading exercise: the chart sits under the statement, with gridlines and no values.
4. Ask for « construis l'histogramme »: no histogram appears until you have tried; afterwards it may
   come as the correction.
5. Ask for a representation the course does not use (« en diagramme en barres »): Célestin stays on the
   course's own.
6. At 400 px wide the charts fit, labels thin or turn, and the pie's legend goes under it.

### Four drawing blocks, one path

`chart`, `flowchart` (an organigramme), `figure` (plane geometry, a number line, a diagram of sets)
and `plot` (functions, sequences and measurements in a repère) share everything around their own
rules. Célestin gives what the course says (data, steps, points, expressions), never pixels, colours or
notation; the board computes, lays out and draws in the course's notation.

- **Where they sit.** An explanation takes drawings among its `blocks`; a worked example or an
  exercise takes one as `drawing`, under the statement. `drawing` is the `Drawing` union in
  `app/domain/board.py`, picked by a callable discriminator (`_drawing_type`). 008 let a chart
  drawing leave `type` out, so that must keep validating, and every later drawing block declares
  `type` as required so the model always says what it sends. A drawing without `type` is read from
  its keys (`_DRAWING_KEYS`): `chart` is a chart, `figure` a figure, `nodes` a flowchart, `x_range`,
  `y_range` or `curves` a plot, and a chart when no key tells. A figure, flowchart or plot sent
  without `type` is then refused for the missing tag with its own block's error, and counted under
  its own family (`schema.missing`), never as a chart. A new drawing block is a `Tag` in `Drawing`,
  a key in `_DRAWING_KEYS`, a member of `Block`, and a row in `_FAMILIES`. The block models,
  sub-models included, are re-exported from `app/api/schemas/board.py`.
- **One dispatch.** `display_board` keeps a `_FAMILIES` table (`app/services/tools/board.py`) keyed
  by the block's `type`: the block class, its refusal function `(items, card, ctx)` returning
  `(rule, message)` or `None`, and its log summary. The handler runs, in order: the string checks,
  the definition check, the cap on drawings, then every family on the card in table order (chart,
  flowchart, figure, plot), all before anything is logged as displayed. The first refusal is a
  French tool error naming the field, logged as `<type>_refused` with its `rule`; a card that
  passes logs one `<type>_displayed` per family present. Both carry `user_id`, `chapter_id` and
  `mode`, never a label, a text, an expression or a number. A block the card model refuses never
  reaches the handler: `log_schema_refusal` (the registry's `on_invalid` hook) reads the family at
  the union tag's fixed place in the Pydantic error's `loc` (right after `blocks, <i>` or after
  `drawing`; any other element may be a name the model chose, like a figure point called « chart »)
  and logs `<type>_refused` with `rule: schema.<error type>`. The string checks run first, on the
  parsed card: a failure inside a drawing is logged as `<type>_refused` with rule
  `string_control`, `string_latex` or `string_script`, so the per-family counts are whole.
- **Two drawings per card.** More than two drawing blocks on a card, of any kinds, is refused
  before any family's rules run, and logged as `drawing_refused` with `rule: per_card`
  (`MAX_DRAWINGS_PER_CARD`). The one family limit left is the flowchart's: one per card, so its
  `per_card` fires only on a card holding exactly two flowcharts. Charts, figures and plots have no
  limit of their own any more; theirs could never fire behind the shared cap.
- **Notation in labels.** A figure refuses coordinates or an interval written by hand in any label
  or caption, on every card (`label_notation`): the board writes them itself. A plot refuses them
  only on an exercise's drawing (`exercise_text`), where they would give the answer; elsewhere the
  prompt carries the rule, because a plot's labels name curves and quantities and a notation check
  there would mostly catch false positives. A deliberate difference, not a gap.
- **Maths in labels.** A chart writes its category and box labels as SVG text, which KaTeX cannot
  typeset, so charts still refuse `$` there (`label_math`, 008 deviation D10). The three newer blocks
  keep the SVG for geometry and for the numbers the board writes itself. Every text Célestin wrote sits in
  an HTML layer positioned over the SVG and goes through `RichText` (KaTeX, `trust: false`). So
  node texts, answers, figure labels, axis titles and curve labels may carry `$…$`, and point names
  are typeset as maths. KaTeX's html output is aria-hidden, so screen-reader text uses
  `RichText mathOutput="mathml"`, except for the plot's description, which is plain words by design.
- **Stored cards.** Each view cleans its block once with a total `sanitise` that never throws. When
  nothing usable is left, the three newer views show « Organigramme vide », « Figure vide » or
  « Graphique vide », never an error on the board. Nothing on a drawing reacts to the pointer.
- **Shared case tables.** Where a tool rule depends on how the board lays something out or parses
  it, both sides read one JSON table, and the frontend's copy must stay byte-identical (a backend
  test compares the bytes): `tests/fixtures/flowchart_layers.json`,
  `tests/fixtures/figure/capacity.json`, `tests/fixtures/expression_cases.json`.
- **Shared notation.** The board writes coordinates and intervals in one place,
  `frontend/src/components/celestin/charts/format.ts`: `formatNumber` (decimal comma, true minus),
  `formatPair` (« (2 ; −1,5) ») for a figure's and a plot's points, and `formatInterval` /
  `formatBound` (±∞, an infinite end always open) for a number line's intervals and a chart's
  classes (`classLabel`).
- **Probes.** `scripts/probe.py --charts`, `--flowcharts`, `--figures` and `--plots` run each
  family's probes in both modes (see [running-locally.md](./running-locally.md)). A flag ending
  « (à lire) » points at something to read and is not counted. Each probe's « Refus de l'outil »
  lists every refusal of the turn as « family : rule », read from the board tool's log:
  `drawing : per_card` for the cap, the string rules under the family they hit, and « ? » when a
  refusal carries no rule. The flowchart flags check the course's own method on the probes that
  show it (« method », « complete », « walk »): every branch ends on one of the course's outcomes
  (« issue absente du cours », for a « Ni SA ni SG » the pack never gives), and the question
  testing the quotient has one exit, as in the pack. « build » counts an exercise asking for an
  organigramme whose statement names both steps of the method; « complete » counts a statement
  that gives or paraphrases a hidden box (quoted labels to place are only « à lire »). The
  reviewed designs, the probe runs and the verification of these blocks are recorded in
  `specs/009-board-drawings/`.

Shared limits. The layouts were built and tested under jsdom on estimated sizes. Real fonts, KaTeX
metrics and dark mode are what each block's manual checklist is for. The drawing blocks roughly
doubled the board tools' declarations (`tests/fixtures/board_declarations.json`, about 30 000
characters, from 16 000), which sit in the cached prefix. After a schema change, run
`scripts.voice_smoke`: the Realtime session receives the same declarations, and only the real API
says whether it accepts them. For example, the figure's point names are a key pattern.

### Flowcharts are laid out by the board

A `flowchart` block (`app/domain/flowchart.py`) is a graph, never a picture:

- `nodes` (2–12), each with an `id`, a `kind` (`step` by default, `decision`, `io`, `start`, `end`),
  a `text` of at most 80 characters that may carry `$…$`, and its exits `next: [{to, label?}]` (two
  at most);
- optionally `path` (the nodes walked, the last one current), `hidden` (at most 4, drawn « ? ») and
  `caption`.

The first node is where it starts. An explanation takes one flowchart; a worked example or an
exercise takes one as `drawing`. The card model holds what never changes (kinds, sizes,
`extra="forbid"`, so no position, colour or style). `display_board` holds the graph rules in
`app/services/tools/flowcharts.py`, reported in this order: `per_card`, then for each flowchart where
`path` and `hidden` may go, the graph rules, and the leak rule.

| Code | Refused when |
|---|---|
| `per_card` | an explanation carries a second flowchart |
| `exercise_path` | an exercise's flowchart has a `path` (it would show the way) |
| `hidden_place` | `hidden` anywhere but an exercise's `drawing` |
| `ids` | a node id is used twice, or `hidden` lists one twice |
| `blank` | a node's text, an exit's label or the caption is only spaces |
| `placeholder` | a node's whole text only marks a hole: marks alone (« ? », « ？ », « … », « ⋯ », « ___ », « ( ? ) », « { ? } », « <?> », « □ », `$?$`, `$\ldots$`), or a hole phrase from a closed list read without case, accents or punctuation (« À compléter », « À compléter par l'élève », « À toi de compléter », « (à remplir) », « ??? à trouver », « Étape manquante ici », « Case 3 : ? »). The real text goes in the node and its id in `hidden`, which the board draws « ? »; a flowchart the student must build is not displayed at all. Only the whole text counts: « Compléter le tableau », « Calculer la valeur manquante » and « Case vide ? » are steps and questions |
| `unknown_id` | `next[].to`, `path[]` or `hidden[]` names no node |
| `self_loop` | a node's exit leads to itself |
| `start` | a `start` elsewhere than `nodes[0]`, or an exit back into it |
| `end` | an `end` has an exit |
| `exits` | a step, io or start has two exits |
| `decision` | a question has no exit, an unlabelled exit, two labels that read the same (prose case- and space-folded, formulas compared without spaces, case kept), or both exits to one node. A question with a single labelled exit is accepted on purpose: an answer the course does not treat has no arrow, so the SA/SG method needs no « Ni SA ni SG » branch |
| `decision_text` | a question is over 40 characters (TeX source counted) |
| `unreachable` | no arrow leads from `nodes[0]` to a node |
| `dead_end` | a non-end node has no exit while the chart has an `end` |
| `wide` | a row of the board's own layout weighs over 3 (a question 2, any other node 1) |
| `path` | two consecutive `path` nodes have no arrow between them (a loop may be walked twice) |
| `hidden_leak` | a hidden node's text shows elsewhere on the card (see below) |

`hidden_leak` compares whole runs of words (NFKC, case-folded) and formulas (TeX without spaces).
It skips a hidden text shorter than 5 characters, counting its words' letters and digits and its
formulas' TeX. A hidden text that is a formula (its words under 5 letters, as
`$i \leftarrow i + 1$` or « Si $i \leqslant n$ ») is also found inside any visible formula of at
least 4 characters, as whole symbols. For example, `i\leftarrow i+1` is found in
`S\leftarrow S+u_i ; i\leftarrow i+1` but not in `i\leftarrow i+10`. A hidden text with words is not
given away by its formula alone: hiding « Calculer $\Delta$ » next to « $\Delta > 0$ ? » is
accepted, because that is the method's notation. The rule looks at the visible nodes, every exit
label and the caption. With exactly one hidden node it also looks at the title, the statement and
the hint; with two or more, the statement may list their texts as labels to place. `leaks` and
`reading_order` are public for `scripts/probe.py`.

The rows `wide` counts come from `layers` (a depth-first walk, longest paths, back edges as loops),
the same function as the board's `flowchart/layout.ts`; `tests/fixtures/flowchart_layers.json` and its
byte-identical copy `flowchart/__tests__/layer_cases.json` hold the two together.
`flowchart_displayed` logs `nodes` (per flowchart), the `hidden` total and a `path` flag, never a
text, a label or an id.

The frontend (`frontend/src/components/celestin/flowchart/`) cleans the block once. `sanitise` replaces a
hidden node's text with « ? » at this point, so the secret reaches no DOM node, key, measurement or
aria-label; a label of spaces only counts as none. It then measures every label once at five widths
(`LADDER`) in a 0 × 0 hidden layer: a wrapped label's width is its widest line, read from its inline
RichText span. It then lays the chart out itself:

- rows ordered depth-first with the heavier branch first, then barycenter sweeps;
- x positions from an isotonic fit over footprints that include the exit labels;
- orthogonal edges on tracks between rows. A bar that comes down where another bar goes into its
  box takes the higher track, so no two edges into different boxes run along each other;
- loops in side lanes; two loops that meet in a gap take two lanes;
- a question's left answer leaving from its bottom vertex, its right answer from its right vertex,
  a loop from its left vertex.

The SVG holds geometry only. When the drawing would shrink below 85 % (`MIN_SCALE`), the board
lists the steps instead, under « Cet organigramme est trop large pour cet écran ; le voici étape par
étape. », and it never scrolls. An sr-only ordered list reads the steps in reading order, with maths
as MathML, and each step says where it leads:

- « Si « oui » : étape 3. » for a question's answers;
- « Flèche « puis » : étape 5. » for another labelled arrow;
- « Retour à l'étape 2. » for a loop;
- « Ensuite : étape 6. » for a jump;
- « Fin du chemin. » where a branch stops.

The drawing animates in (`flow-enter`, `chart-trace`) only when there is no `path`, so a redisplay
that walks the method does not replay it.

Known limits:

- `wide` follows the phone board, so two questions side by side are refused even on desktop.
  - About 10–14 % of random valid charts still fall back to the step list at the phone board
    (268 px), and about 0.5 % at 400 px.
  - The known boundary is a 30-character question beside an io box, with a long edge passing
    through the row (`DEC_STEP_ROW` in the fixtures).
  - Real measured sizes decide in the browser.
- The heavier branch goes first. When the « non » branch is the longer one, « non » goes under the
  question and « oui » to its right, which is the mirror image of a course that draws « oui »
  below. The board chooses its own layout rather than copying the course's; the labels keep either
  reading correct, and ties keep Célestin's exit order.
- Célestin tends to add an outcome the course does not give (« Ni SA ni SG ») as a branch or an end
  box. No tool rule can tell, because the pack's method is prose: the prompt and the `decision`
  refusals say an answer the course does not treat has no arrow, and `probe --flowcharts` counts
  it (3 of 27 flowcharts over six runs on 29 September 2026, from every one before).
- Track ordering cannot untangle two edges whose descents fall exactly on each other's arrivals.
  The leftmost is then placed without the constraint. The fuzz found none in 18 000 charts, and
  `sharedStretches` in `__tests__/invariants.ts` would fail it.
- `hidden_leak` does not catch paraphrase, short secrets (« SA », `$q$`, `$u_n$`) or what Célestin says
  aloud, and with two hidden boxes or more it lets the statement list their texts as labels to
  place. The probe measures speech and statements that describe the method or a hidden box: the
  prompt says the steps, their order and the questions are what the student looks for, yet about
  one build statement in four still spells them out (September 2026). No tool rule catches it. The
  hidden text never reaches the DOM, but it travels in the `board.set` JSON and, in the parcours,
  in the history the browser posts back (as 008 D6; an accepted limit, deferred by the
  verification of 29 September 2026).
- A flowchart costs up to 84 hidden label renders (12 nodes × 5 widths + 24 exit labels). They are
  memoised, and crossing the 360 px compact threshold re-measures once.

#### Manual checklist — a method as an organigramme

1. Seed chapter 1 and start « Synthèse — SA ou SG ? ». Ask « Tu peux me faire un organigramme pour
   savoir si une suite est une SA ou une SG ? ». An explanation shows the flowchart. Check that:
   - differences come first, then quotients;
   - the question after the quotient has a single « oui » (the pack gives no third outcome);
   - the « oui » and « non » labels are clear of each other, and every arrow ends on a box top;
   - each box is just wide enough for its longest line.
2. Ask to follow the method on 3 ; 6 ; 12 ; 24. The card comes back with:
   - the walked boxes tinted and the current one darker;
   - the walked arrows in the primary colour;
   - no replay of its entry animation.
   There are two or three redisplays at most.
3. Ask for an exercise « compléter l'organigramme ». The hidden boxes are dashed « ? ». Inspect the
   DOM: the hidden texts appear nowhere, and Célestin does not say them.
4. Ask for an exercise « construire l'organigramme ». No flowchart appears before your attempt.
5. Ask for an algorithm with two « tant que » loops one after the other. Each loop goes back up its
   own lane, and no two arrows run along one line.
6. Resize to 400 px. The method draws at full size. A wider chart either shrinks to 85 % at most or
   turns into the numbered list. There is never a horizontal scroll.
7. With VoiceOver, the drawing reads « Organigramme en N étapes », and the list reads each step, its
   maths, where it leads and where a branch stops (« Fin du chemin. »).
8. With reduced motion, nothing moves. In dark mode, boxes, arrows and labels stay readable.

### Figures are drawn from points and relations

A `figure` block (`app/domain/figure.py`) is `{"type": "figure", "figure": {...}}`, the inner object
a union on `kind`:

| `kind` | What the course calls it | Célestin gives |
|---|---|---|
| `plane` | figure géométrique, repère | `points` (name → [x, y] in the figure's units, y up), `shapes` (`draw` and `of`, the point names: segment, line, ray, vector, polygon, circle, arc, angle, right_angle; plus `radius`, `marks` for the codage, `label`, `style`), `x_range`/`y_range`, `axes`, `grid`, `marker` (cross or dot) |
| `number_line` | droite graduée | `intervals` (`start`/`end`, null = ∞, `closed`, `label`), `marks` (`x`, `label`), `convention` (brackets, dots or hatched) |
| `sets` | diagramme d'ensembles | `layout` (nested, overlap or separate), `sets` (`id`, `label`; outermost first when nested), `elements` (`text`, `within`), `shade`, `universe` |

A plane figure and a number line have `show_values` and `caption`; a diagram of sets has only
`caption`. Point names are the course's (`A`, `B'`, `M''`, `A_1`), typeset as maths. The board
writes `A(2 ; −1)`, `]−∞ ; 2] ∪ ]5 ; +∞[`, the decimal comma and the true minus itself, and only when
`show_values` is set. Intervals that share a label are one set, written as one union.

Zones follow one meaning. `within` lists the sets an element lies in, and only those; the sets that
contain them count without being listed, and `[]` is outside them all. For nested sets, the zone is
the ring of the deepest listed set. A hatched zone in `shade` is written the same way, so hatching a
whole set means hatching each of its zones.

The card model holds what never changes: enums, sizes, finite numbers and point names. A card holds
at most two drawings of any kind (`display_board`'s cap, above). `display_board` holds the rest, in
`app/services/tools/figures.py`.

The span below is the figure's larger extent as the board draws it: its points, its circles, the
origin of a repère and any range given. Labels and captions are read through their LaTeX (`_bare`):
`3{,}5` is 3,5, `\,` and `\left(` are dropped, and `\degree` and `^\circ` are °.

| Code | Refused when |
|---|---|
| `exercise_values` | an exercise's figure sets `show_values` |
| `empty` | a plane with no points, axes or grid; a number line with nothing on it |
| `window` | a range with min ≥ max, or a range without 0 when `axes` is set |
| `scale` | a number beyond ±1 000 000, or a figure less than 0,001 across (the board writes four decimals, so its graduations would read the same) |
| `close_points` | two distinct points closer than 2 % of the span |
| `arity` | a shape has the wrong number of points |
| `repeated` | a name repeated in a shape, a set id or a zone; a zone shaded twice; a number-line mark placed twice |
| `unknown_point` / `unknown_set` | an unknown name |
| `field` | `radius` on a non-circle; `marks` on anything but a segment or an angle |
| `circle` | both or neither of `radius` and a through point |
| `degenerate` | coincident points, a flat polygon, a null or flat angle, a radius under 2 % of the span |
| `crossed` | a bow-tie polygon |
| `not_right` | a right-angle mark more than 1° off |
| `arc_radius` | the ends of an arc more than 2 % apart in distance from its centre |
| `codage` | the same ticks on lengths more than 2 % apart, the same arcs on amplitudes more than 1° apart; more than 5 unmarked angles |
| `measure` | a degree label on an angle (`40°`, `\widehat{B} = 40°`) more than 1° off; length labels on segments (`5 cm`, `\|AB\| = 3{,}5` cm) out of proportion with each other and the drawing. An approximation (≈) is not checked |
| `outside` | a point or circle beyond a given range (2 % slack) |
| `label_notation` | coordinates or an interval written in a label or caption, however the LaTeX spells them (`(2{,}5 ; 1)`, `\left(2 ; 3\right)`, `[\sqrt{2} ; 3]`, `]{-}\infty ; 2]`). Both bounds must start like a number (a sign, then a digit, ∞, `\frac`, `\sqrt`, `\pi` or `\infty`), so `[AB]`, `[a ; b]`, `M(x ; y)` and `(O ; \vec{i}, \vec{j})` pass |
| `order` / `infinite_bound` | start ≥ end; −∞ or +∞ included |
| `union` | pieces under one label that overlap, or touch at a bound either includes |
| `blank` | a set's label, an element or the universe made only of spaces |
| `set_count` | overlap or separate with other than 2–3 sets |
| `region` | a zone of a separate layout listing more than one set |
| `universe` | `[]` used without a universe |
| `crowded` | a zone (more than 6 elements, or more than its slot holds), the label row, a ring or the universe that does not fit the 294 px layout |

The exercise rule comes first, then each figure in card order:

- plane: `empty` → `window` → `scale` → `close_points` → per shape (`arity` → `repeated` →
  `unknown_point` → `field` → `circle` → `degenerate` → `crossed` → `not_right` → `arc_radius`) →
  `codage` → `measure` → `outside` → `label_notation`;
- number line: `empty` → `scale` → per interval (`order` → `infinite_bound`) → `union` →
  `repeated` marks → `label_notation`;
- sets: `repeated` ids → `blank` → `set_count` → per zone (`unknown_set` → `repeated` → `region` →
  `universe`) → `repeated` shade → `crowded` → `label_notation` on the caption.

`crowded` is a contract with `fits` in `frontend/src/components/celestin/figure/venn.ts`. Both read
`backend/tests/fixtures/figure/capacity.json`:

- the constants and the slot capacities;
- `text_px` pairs (whitespace is JavaScript's `\s` on both sides);
- flow cases and 29 `fits` cases.

The frontend copy (`figure/__tests__/capacity.json`) must stay byte-identical, and
`test_figure_capacity.py` checks it. If you change a capacity number, change both copies in the same
commit, formatted with prettier. `figure_displayed` logs the `kinds`.

The frontend (`frontend/src/components/celestin/figure/`):

- **Cleaning.** `sanitise` runs once and is total. It drops a number beyond ±1 000 000
  (`MAX_MAGNITUDE`) like a non-finite one, and ignores a range narrower than 1e-9 (`MIN_SPAN`), so no
  tick computation can throw.
- **Rendering.** Geometry is drawn in SVG at the measured pixel width, with an HTML label layer over
  it (`label-layer.tsx`): KaTeX for `$…$`, `w-max` spans, and flex-wrap flows for zones.
- **Plane.**
  - One scale serves both axes. The window only grows, and content at one place gets a unit around
    it.
  - Arcs are minor arcs. Unmarked angles are tinted sectors, not arcs.
  - A point's label tries its own side, the other side, then a quarter turn either way. It keeps
    off other labels and other points' marks.
- **Number line.**
  - Each written set gets its own lane.
  - A notation too wide for the board breaks before a « ∪ » (or after « = ») onto more lines,
    lifting the lanes above.
  - Every bound and placed number has a tick, and a placed number has a dot, except on an
    interval's bound, in every convention: the bound's own bracket, dot or hatching says whether
    it is included, and a filled dot on an excluded bound would say the opposite (a probe run
    caught it).
  - Labels under the axis take as many rows as they need.
  - The convention draws brackets, dots, or hatching. Hatching belongs to a lane, not to a set: a
    lane hatches, once, what none of its pieces holds (`LineLayout.hatches`, the complement of
    their union). Two unlabelled intervals share the axis, so `]−∞ ; 2]` with `[5 ; +∞[` hatches
    only `]2 ; 5[`; hatching each piece's own complement would hatch the whole axis and read « no
    number fits ». A lane whose pieces fill the axis (S = ℝ, or ℝ privé de 2 with its brackets)
    hatches nothing, which is true, and a lane with no piece hatches nothing either (a hatched line
    that only places numbers is not all hatched). Under hatching the unlabelled intervals are one
    set (`groups(…, hatched)`): one group, one lane, one notation (`]−∞ ; 2] ∪ [5 ; +∞[`), so the
    exercise and its correction with `show_values` hatch the same thing. The tool refuses such
    pieces when they touch or overlap (`union`, « sont hachurés sans étiquette »), as it does for
    pieces sharing a label.
  - Intervals and bounds are written by `formatInterval` / `formatBound` in `charts/format.ts`, a
    bound as its mark's label when a mark sits there (`boundText`), and points by `formatPair`.
  - Test hooks, not handlers: `data-mark` on a mark's dot, `data-hatch` on a lane's hatching,
    `data-zone` on a zone of sets, `data-marker` on a point's marker.
- **Sets.** Overlap and separate layouts use fixed zone slots. Nested sets are rounded rectangles
  with content-sized bands. Below 294 px the drawing scales down.
- **Screen readers.** The description is read as MathML. It names the points without their
  coordinates, and a circle without its radius, unless `show_values` is set. A number line is read
  as the course would say it: « Nombres placés », then each interval by its bounds but not its
  brackets, a bound written as its mark's label when one sits there. It gives no graduation range,
  which depends on the board's width, so the description does not lay the line out a second time.
  There is no `<title>`.

Known limits:

- `label_notation` is a heuristic. A vector's coordinates as a `pmatrix` pass, and so does a bound
  spelled `\sqrt[3]{2}` inside brackets. Coordinates written with letters (`M(x ; y)`, `[a ; b]`)
  pass on purpose.
- `measure` reads a whole label, or what follows a single « = »: `\widehat{A} = \widehat{B} = 40°`
  is not checked. Length labels are compared with each other, so a single one is never checked.
- The scale thresholds are a judgement. A number line « au dix-millième » (1,4142 and 1,4143) is
  refused, because the board writes four decimals. If FWB material needs it, raise the figure's
  decimals rather than lowering the threshold.
- A nested element whose `within` names only an outer set lands in the outer ring. No rule can tell,
  so it stays a prompt rule.
- Label placement is still a heuristic. A very dense figure can still overlap, and a point's label
  next to an axis number stays beside it (B(4 ; 0) next to « 4 »).
- A wide board gives a number line more graduations (0,5 steps at 560 px).
- Text widths are estimates: 7 px a character, 9 px a maths glyph.

#### Manual checklist — figures

In a chapter whose material has figures:

1. A coded right triangle:
   - the square mark is at the right vertex;
   - equal ticks sit on equal sides;
   - an unmarked angle is a tinted sector;
   - the « 5 cm » label does not collide with a midpoint's name.
2. A repère on [−10 ; 10] with a grid:
   - the numbers thin out (every 2 or 5);
   - « x » and « y » are clear of the numbers;
   - `show_values` writes « A(2 ; 3) ».
3. An exercise asking for an intersection point's coordinates: no coordinates are written, and the
   point is not placed.
4. `S = ]−∞ ; 2] ∪ ]5 ; +∞[` with `show_values`:
   - one colour, one lane, one notation;
   - hidden during an exercise;
   - the hatched convention hatches ]2 ; 5[.
5. `S = ]−∞ ; −3] ∪ [−1 ; 1] ∪ [2 ; 3[ ∪ ]4 ; +∞[` with `show_values`, at a 400 px board and on a
   phone: the notation breaks before a « ∪ », and nothing leaves the card.
6. ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ, and population ⊃ échantillon ⊃ individu: every element sits in its ring,
   and nothing overlaps at 400 px.
7. At a 400 px board and on a phone, where the drawing scales down, both of these hold:
   - the divisors of 12 and 18, with A ∩ B hatched;
   - a 3-set Venn with a universe and an outside element.
8. 12 labelled points in a gridded repère with `show_values`, at a 400 px board: no label covers
   another label or a point's mark. Check dark mode too.

### Plots are drawn from expressions

A `plot` block (`app/domain/plot.py`) is a graph in a cartesian plane. It takes:

- `{"type": "plot", ...}` with a window (`x_range`, `y_range`) and the axis titles with their units
  (`x_title`, `y_title`, required);
- optional steps (`x_step`, `y_step`), `grid` (on by default) and `orthonormal`;
- four flat lists:
  - `curves`: an `expr`, an optional `domain` for a piece, `start_dot`/`end_dot` (none, filled or
    hollow), `dashed` and `label`;
  - `sequences`: a general term in n from `first` (default 1) to `last`, drawn as isolated points;
  - `points`: with a `mark` (filled, hollow or cross), `guides` and `show_values`;
  - `lines`: broken lines, `dashed` for construction lines;
- a caption.

It sits among an explanation's blocks (two drawings at most per card, of any kind) or as a
`drawing`.

Célestin gives mathematics, never pixels. `expr` is our closed grammar (`app/domain/expression.py`,
mirrored by `frontend/src/components/celestin/plot/expression.ts`):

- decimals with `.`, and `+ - * / ^`;
- a unary minus: `-x^2` is −(x²), and `2^3^2` is 2⁹;
- implicit products before a name or `(`, as in `2x` and `2(x+1)`; `1/2x` is refused as ambiguous;
- `sqrt cbrt abs exp ln log sin cos tan`, where `log` is base 10 and angles are in radians;
- `pi` (or `π`) and `e`;
- one variable: x or t for a curve, n for a sequence;
- at most 120 characters, nested 24 deep.

Scientific notation, LaTeX, commas, `y =`, `|x|` and `x²` are refused with a targeted message. A value
that is not a finite number at any step is undefined there (NaN) on both sides. Both parsers pass
`tests/fixtures/expression_cases.json` (96 cases). The frontend copy
(`plot/__tests__/expression_cases.json`) is byte-identical, and `test_expression.py` checks it.

The card model holds what never changes: types, enums, sizes and finite numbers. Its limits are a
label of 24 characters at most, 6 curves, 3 sequences, 20 points, 8 lines of up to 30 vertices, and
n from 0 to 1000. `display_board` holds the rest in `app/services/tools/plots.py`, and the first
refusal wins. The order is:

1. the exercise rules, for each plot: `exercise_values`, then `exercise_text`;
2. for each plot in card order, `window` → `step` → `orthonormal` → `empty`, then:
   - each curve: `expr.<code>` → `pack_function` → `domain` → `undefined` → `outside` → `endpoint`;
   - each sequence: `expr.<code>` → `pack_function` → `terms` → `outside` (the range of n) →
     `undefined` → `outside` (the terms);
   - the points, then the lines: `outside`.

| Code | Refused when |
|---|---|
| `exercise_values` | an exercise's drawing has a point with `show_values` or `guides` |
| `exercise_text` | on an exercise's drawing, a title, label or the caption holds a relation or values in brackets (below) |
| `window` | min ≥ max, a bound beyond ±1e6, or a span under 0.001 (float slack 1e-9, the same on the board) |
| `step` | more than 4 decimals, larger than the window, or more than 30 intervals (float slack 1e-9) |
| `orthonormal` | `orthonormal` with a y span over x span outside [0,4 ; 2] (float slack 1e-9 on both sides, the same on the board: exactly 0,4 and 2 are accepted) |
| `empty` | nothing to draw |
| `expr.<code>` | the parser refuses: `syntax`, `unknown_name`, `latex`, `comma`, `equation`, `scientific`, `ambiguous`, `variables`, `depth` |
| `pack_function` | a curve or sequence uses exp, ln, log, cbrt, sin, cos or tan and the chapter's pack never names it (below) |
| `domain` | a ≥ b, or no overlap with the window (touching it at one point is none) |
| `undefined` | a curve has no finite value over its visible domain (401 samples), or a sequence none for n from `first` to `last` |
| `outside` | a curve never enters the window; a sequence's n range beyond `x_range`, or a defined term outside `y_range`; a point outside; a line that never meets the window |
| `endpoint` | a filled dot where the curve is undefined, a hollow one undefined also just inside, or a dot outside the window |
| `terms` | `first` > `last`, or more than 40 terms |

`outside` finds a curve's crossing by bisection across straddling samples, so a pole does not count
as one.

`exercise_text` refuses two things:

- **A relation.** `=`, ≈, ≃, ≠, <, >, ≤, ≥, the slanted ⩽ and ⩾ that FWB courses print, ≦, ≧, ↦,
  →, or the commands `\approx`, `\neq`, `\leq`, `\geq`, `\leqslant`, `\geqslant`, `\leqq`, `\geqq`,
  `\mapsto`, `\longmapsto`, `\to`, `\rightarrow`… (a command counts only when no letter follows it).
- **Values in brackets.** Each innermost pair of parentheses or brackets, either way round, is
  refused when:
  - it has a `;` and one member holds a value (a digit, π, a root or ∞);
  - or its members, split on a comma followed by a space or a sign, hold values in two members.

So `(1/2 ; −9/4)`, `(x_S ; 2)`, `(1,-4)` and `]-1 ; 2[` are refused, while `(0,5)` and
« (cm, toutes les 0,5 s) » pass. `gives_away` is public for `scripts/probe.py`.

`pack_function` counts the number `e` as exp. On a curve it also counts a power whose exponent
holds the variable, such as `2^x`; a geometric sequence's `0.5^(n-1)` stays a power. sqrt and abs
are never looked up. With no pack (unit tests, scripts), the rule is skipped.

Each function counts as named only when the pack names the *function*, not an everyday word that
shares its root (`PACK_WORDS` in `plots.py`, each entry commented, tested both ways on 44 pack
sentences):

| Function | The pack names it with | Not with |
|---|---|---|
| exp | `\exp`, `exp(`, « fonction exponentielle », « exponentielle de base … », the noun (« l'exponentielle »), e raised to a power (`e^x`, `\mathrm{e}^{x}`, `{e}^{-t}`) | the adjective (« une croissance exponentielle »), an electron or a positron (`e^-`, `\mathrm{e}^{+}`), a capital E (`E^{\circ}`) |
| ln | `\ln`, `ln(`, « logarithme népérien / naturel / de base e » | a bare « logarithme », « échelle logarithmique » |
| log | `\log` (with `\log_{10}`, `\log_a`), `log(`, « logarithme décimal / de base 10 » | « logarithmique » |
| cbrt | « racine cubique / troisième », `\sqrt[3]`, ∛ | — |
| sin, cos | `\sin`, `\cos`, « sinus », « cosinus » (the sine of an angle is the function; « sinusoïdal » names its graph) | « cosinus » for sin; `\sinh`, `\arcsin`, `\cosh` |
| tan | `\tan`, `tg` (the Belgian notation), « fonction tangente », the tangent of an angle (« tangente de l'angle », « tangente de $\alpha$ »), « sinus, cosinus et tangente » | the tangent line: « l'équation de la tangente en A », « tangente à la courbe », « droite tangente » |

The rule reads expressions only. A function the pack never names can still be drawn from values
computed elsewhere, as points or as a broken line through them, and nothing mechanical can tell
those from measurements. Only the prompt's general rule covers that case, and `probe --plots`
measures it (`_traced`).

Messages start « Le graphique blocks[i] » or « Le graphique drawing », then name the layer
(« , courbe 2 », « , point 1 ($A$) »). `plot_displayed` logs the plot `count`, the `layers` counts and
the `functions` used, from the closed set; never an expression, a label or a number. Each
expression is parsed once per call: a small cache (`_parsed`) serves both the rules and the log
summary.

The frontend (`frontend/src/components/celestin/plot/`):

- **Replay.** `sanitise` cleans a stored plot once and never throws.
  - It drops bad expressions, points and lines, and a sequence whose first index is outside 0 to
    1000.
  - An absurd window falls back to [−10 ; 10], and a bad step to automatic ticks.
  - « Graphique vide » shows when nothing is left.
- **Sampling.** `sampleCurve` samples a curve adaptively, to within 3 px. A gap still steep after
  12 halvings is joined only when its midpoint splits its rise. So poles and jumps break the curve,
  and a very steep line stays drawn.
- **Axes.**
  - Axes go through 0 with arrows, or on the window's edge without one.
  - An orthonormal plot uses the one step Célestin gave on both axes.
  - Graduation labels thin to a round multiple of the step, anchored at 0.
- **Titles.**
  - The y title goes right of the arrow. Failing that, it goes left of it, and the plot starts
    6 px lower so the top graduation keeps its label. Failing both, it takes a row of its own
    above the arrow.
  - The x title goes to the arrow's tip when nothing is drawn there, otherwise under the plot.
- **Corners.** A graduation label that sits on the other axis's line moves off it when the ticks
  leave room to tell whose it is, and is dropped otherwise. A y label moves 8 px up, or 7 px down
  under a top-edge axis; an x label moves sideways to 3 px clear. `layout` in `layout.ts` makes
  every geometric decision, DOM-free.
- **Colour key.** Solid curves, sequences and lines that share a label share one colour and one
  label; so do those that all have none. Dashed layers are muted.
- **Text.** The SVG holds only numbers, written in the course's notation. Célestin's titles and labels
  are spans over it, typeset by KaTeX inline in the foreground ink, with the group's colour as an
  underline. The caption is shown with KaTeX (aria-hidden) and read from a MathML copy.
- **Nothing to read off.** Nothing reacts to the pointer. The screen-reader text names the axes,
  graduations and layers. It never states an expression, a domain, an endpoint, a range of n or
  vertices, and states coordinates only with `show_values`.

Known limits:

- `exercise_text` has gaps.
  - It does not catch a bare number: « racine : 1,4 » or « $v$ vaut 24 cm/s » look like the
    quantity « toutes les 0,5 s ».
  - A comma pair with one value passes (`(x_S, 2)`); the `;` form is caught.
  - A reading guide drawn by hand as a dashed line escapes every rule, because it looks like an
    asymptote drawn from the y axis. The prompt forbids it, and `probe --plots` flags it.
  - Some false positives cost one retry: « (2 essais, 3 mesures) », a caption naming its window
    « sur $[0 ; 5]$ », `(0 ; b)`.
- Two distinct unlabelled functions share one colour and read as « une courbe en 2 morceaux ». The
  prompt asks for labels; nothing enforces it.
- Sampling is a heuristic. An extremely steep continuous curve is drawn as a jump. The board and the
  tool can disagree on pathological inputs, such as sin(1/x) or tan(1000x) in a thin window.
- A grammar change must stay backward-compatible, or stored plots show « Graphique vide ».

#### Manual checklist — plots

1. A parabola in an explanation at 400 px:
   - axes through 0 with arrows;
   - one « 0 » at the origin;
   - the label $f$ beside the curve;
   - the x title at the arrow.
2. A v(t) in 3 pieces (`domain`s), unlabelled: one colour, and the x title « $t$ (s) » moves under
   the plot because the last piece ends at the arrow.
3. uₙ as isolated dots from u₁, with whole-number graduations on n.
4. A reading exercise: no coordinates, no guides, and no answer in any title, label or caption. Ask
   Célestin for `show_values` on the exercise and see the tool refuse it.
5. An orthonormal line (a slope read on the grid): equal units and the same step on both axes.
6. Ask for ln(x) in chapter 1: the tool refuses it (`pack_function`), and Célestin stays within the
   course.
7. A function on x from −10 to 1 with the y title $f(x)$ at 400 px: the title sits left of the arrow,
   and the top graduation keeps its label under it.
8. x² + 3 on [−3 ; 3] × [2 ; 12]: « 2 » sits just above the bottom edge, left of the vertical axis,
   not struck through.
9. An exercise « lis les coordonnées du sommet » on x² − x − 2: no caption or label gives
   S(1/2 ; −9/4), and the tool refuses it if Célestin tries.

## What this pipeline deliberately does not do

Recorded in `specs/001-tutor-chat-agent/requirements.md` §4.6, so the gaps are not mistaken for
oversights:

- **No grading.** The exercise card accepts input and does nothing with it. The tutor has no tool
  that issues a verdict, which is the only safe position until a mechanical checker exists.
- **No enforcement of answer withholding.** It is prompt text, verified by the probe script in
  `scripts/probe.py`, not by code. A leak filter needs the checker first. The one exception is a
  drawing, where the tool can see the answer in a form a rule can hold. An exercise's drawing may
  not write its values (`exercise_values`). A flowchart's hidden box may not show elsewhere on the
  card (`hidden_leak`). A plot's texts on an exercise may not state a relation, coordinates or an
  interval (`exercise_text`). A figure's labels never write coordinates or intervals
  (`label_notation`). What Célestin says, and paraphrase, stay prompt rules.
- **No memory beyond the path, in the parcours.** A lesson's transcript does not survive a reload;
  the section progress does. The tutor cannot plan from prior performance. A **discussion's**
  transcript is stored (spec 007, [discussion.md](./discussion.md)) — that mode's whole point is
  that the thread survives.
- **The tutor sees two board interactions.** Picking an option on a check question and pressing
  « Étape suivante » are sent as learner messages (« Ma réponse à la question : … »,
  « Étape suivante. »). Revealing a step stays client-local.
- **Pace is a habit, not a rule.** `propose_next_step` gives the learner the button; the prompt
  tells the tutor never to put a new card up in the same turn as a question and to wait for her
  after proposing. Nothing in code prevents a card from following a card.
