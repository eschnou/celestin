# 008 — Charts on the board

## 1. Introduction

Célestin writes on the board but cannot draw. In a statistics chapter the chart *is* the lesson: a bar chart, a histogram, a box plot are what the student must read, build and interpret at the test. Today Célestin can only describe them in words or as a table.

This epic adds a **`chart` block**: Célestin supplies the data, and the board draws the chart with our own components. The model never writes SVG or any other markup, so its output never becomes markup (the board's existing rule, `board-blocks.tsx`). The chart is accurate because it is computed from the data, and the data can be validated in the tool like the rest of the board (spec 001 R4.6, and the definition check in `documentation/tutor-turn-pipeline.md`).

This is the first of three drawing blocks: charts here, then function graphs (`plot`) and free diagrams in the figure's own coordinates (`figure`), each in its own later spec. This one must not close their door (NFR 4.1.5).

Vocabulary:

- **Chart** — a statistical representation drawn from a data series: the kinds in R2.
- **Series** — the data a chart is drawn from: categories or values or classes, each with an effectif (count) or a fréquence (relative frequency).
- **Class** (« classe ») — an interval of a continuous variable, `[a ; b[` or `]a ; b]` as the course writes it; its amplitude is `b − a`.

Scope:

- A `chart` block that `display_board` accepts, with the chart kinds of R2, in both modes and both channels.
- Validation of the data in the tool, refused as a tool error the model corrects.
- Rendering on the board with the course's number and interval notation.
- Charts on explanation, worked-example and exercise cards.
- The pack records which representations the course uses and under which names.

Out of scope:

- Function graphs, curves, x(t) and v(t) graphs (`plot`, later spec).
- Diagrams, trees, Venn diagrams, number lines, geometry, freehand drawing (`figure`, later spec).
- The student drawing or building a chart on the board, and grading a chart the student drew (brief §11, out of scope).
- Two-variable statistics (scatter plots, regression lines).
- A mechanical checker computing statistics from a chart's data. The data shape must allow one later (NFR 4.1.4).
- Charts that the student can manipulate: no tooltips, no zoom, no toggles that show values not drawn (R5.3).

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §6.5 « writes and draws on the whiteboard » | Célestin draws the first kind of picture that the statistics chapters require. |
| §5.1 It teaches the student's course | Chart kinds, their names, the class notation and the decimal comma follow the pack (R6, R3). |
| §5.2 The content is the student's | A chart shows the course's data or a variant of a sample exercise's data; nothing new is taught through a chart. |
| §5.3 It withholds answers by construction | A chart on an open exercise must not show the answer (R5). |
| §5.4 It never grades from impression | The chart is drawn from typed data, not described in prose; the same data can feed a checker later. |
| §5.6 It is a lesson, not a chat | Charts render as part of a board card, not as a picture in the conversation. |
| §8 Pasted material is data, not instructions | No model output becomes markup; chart text is React text nodes and KaTeX, as everywhere on the board. |

Deviations from the brief: none. §6.8's card list gains no new card; charts are a block inside existing cards.

## 3. Requirements

### R1 — Célestin draws a chart on the board

**As a** student, **I want** Célestin to draw the chart he is talking about, **so that** I learn to read it the way it looks on my test.

Acceptance criteria:

1. `display_board` accepts a `chart` block. Célestin supplies the chart kind, the series, the axis titles and an optional caption; the board draws it.
2. A chart may appear in an `explanation` card (among its blocks), in a `worked_example` (with its statement) and in an `exercise` (with its statement). Other cards do not take one.
3. At most a small, fixed number of charts per card, so a card stays readable (design sets the value).
4. The model never supplies coordinates, pixel sizes, colours, SVG or any markup. Layout, scales, ticks and styling are ours.
5. A chart is available in the parcours and in a discussion, in text and in voice, through the same tool declaration.
6. A card with a chart replays from a stored discussion exactly as it was shown (spec 007 R4.2).

### R2 — The chart kinds

**As a** student in a statistics chapter, **I want** the representations my course uses, **so that** I recognise them at the test.

Acceptance criteria — the block supports:

1. **Bar chart for a qualitative variable** (« diagramme en barres »): categories with their effectifs or fréquences.
2. **Bar chart for a discrete variable** (« diagramme en bâtons »): numeric values with their effectifs or fréquences; thin bars at each value, the horizontal axis numeric.
3. **Histogram**: contiguous classes with their effectifs or fréquences. With equal amplitudes, heights are the effectifs or fréquences. With unequal amplitudes, the area of each rectangle is proportional to its effectif (open question 1).
4. **Frequency polygon** (« polygone des effectifs / des fréquences »): alone, or over the bar chart or histogram of the same series.
5. **Cumulative frequency polygon** (« polygone des effectifs cumulés / des fréquences cumulées »), increasing or decreasing as the course defines it, points placed at the class bounds.
6. **Pie chart** (« diagramme circulaire »): categories with their shares.
7. **Box plot** (« boîte à moustaches »): minimum, Q₁, median, Q₃, maximum as Célestin supplies them, on a numeric axis.
8. The board computes only what has one definition: cumulative sums, the angle of a sector from its share. It never computes a statistic whose definition varies between courses (quartiles, median of grouped data, mean of classes); those come from Célestin, following the pack.

### R3 — The course's notation on the chart

**As a** student, **I want** the chart to be written like my course, **so that** nothing on the board contradicts my notes.

Acceptance criteria:

1. Numbers on axes, labels and values use the decimal comma (`0,45`), with thousands written as the subject prompt says.
2. Class labels follow the course's interval notation, including which bound is closed (`[10 ; 20[` or `]10 ; 20]`); Célestin states the closure once per chart and the board writes every class that way.
3. Percentages are written `12,5 %`.
4. Axis titles, category names and the caption are Célestin's text in the course's vocabulary, with `$…$` for inline maths rendered by KaTeX, and the existing "LaTeX outside `$…$`" check applies to them.
5. The vertical axis of a histogram with unequal amplitudes is titled the way the course titles it (open question 1).

### R4 — Validated in the tool

**As the** product, **I want** a malformed chart refused before it reaches the board, **so that** a wrong chart never teaches something wrong.

Acceptance criteria — `display_board` refuses, as a tool error in French that names the field, so the model corrects it:

1. Series whose lengths differ (categories, values or classes against their effectifs).
2. A negative effectif or fréquence; fréquences that do not add up to 1 or 100 % within rounding; an empty series.
3. Discrete values that are not increasing, or repeated; categories that are repeated.
4. Classes that are not contiguous, not increasing, or have a zero or negative amplitude.
5. Box plot values that are not ordered minimum ≤ Q₁ ≤ median ≤ Q₃ ≤ maximum.
6. More categories, values or classes than the board can draw legibly (design sets the bound).
7. Structural rules (types, required fields, bounds) live on the card model; rules that could change (sums, tolerances, legibility bounds) run in the tool, so stored cards keep replaying (the rule already applied to the LaTeX check).

### R5 — A chart never gives the answer away

**As the** product, **I want** a chart on an open exercise to leave the work to the student, **so that** drawing does not become a way to leak the answer.

Acceptance criteria:

1. Célestin chooses whether values are written on the chart (on the bars, on the sectors) or only readable from the axis. A reading exercise shows the axis and gridlines, not the values.
2. An exercise asking the student to build a chart does not display that chart while it is open; it may display it after the student's attempt, as a correction.
3. The chart shows nothing beyond what is drawn: no tooltip, no hover value, no hidden data in the page that the exercise asks for.
4. These rules are in the tutor prompt and covered by the probe script (R7.3). Nothing in the tool can tell a reading exercise from an explanation, so this is measured, not enforced.

### R6 — The pack says which charts the course uses

**As a** student, **I want** Célestin to use the charts my teacher uses, under their names, **so that** I am not taught a representation that is not in my course.

Acceptance criteria:

1. The mathematics pack template gains a place for the course's representations: each kind the material uses, under the name the material gives it, with its conventions (closure of classes, what the axes carry, how unequal classes are drawn) where the material states them.
2. The transcription stage keeps the readable values of a chart in its `[figure : …]` description (axes, categories or classes, values), so the pack can carry the course's own charts as data. It still invents no value.
3. Célestin draws only kinds the pack names. A chart kind the pack does not name is not used, as a formula the pack does not contain is not used. This is prompt text, measured by the probe (R7.3).
4. Chapters authored before this epic keep working unchanged; they gain the new pack section on their next authoring run.

### R7 — Measuring it

**As the** operator, **I want** to know that charts are used and correct, **so that** the feature earns its place.

Acceptance criteria:

1. The count of chart blocks displayed, per kind and per mode, and the count of chart validation refusals per rule, are logged with ids and counts only.
2. A statistics fixture (material, pack, curriculum) exists under `tests/fixtures/` and in `scripts/authoring_eval`, so authoring of R6 is exercised on real-looking material.
3. `scripts/probe.py` gains chart cases: a reading exercise (no values written), a « construis l'histogramme » exercise (no chart before the attempt), and a request for a chart kind the pack does not name.

## 4. Non-functional requirements

### 4.1 Architecture

1. **A block, not a card, and not a new tool.** The chart is a new member of the board's typed block union. `display_board` stays one tool; no new SSE event; `frontend/src/lib/tutor/types.ts` mirrors the new block.
2. **Nothing the model writes becomes markup.** Our components produce the SVG from the validated data. Text inside a chart goes through `RichText` / `Math` as on the rest of the board.
3. **Rendering reuses what exists where it fits.** Recharts is already installed (`components/ui/chart.tsx`, unused so far); a kind it draws badly (histogram with unequal classes, box plot) may be drawn with our own SVG. No new charting dependency without a recorded reason.
4. **The data shape is the statistics, not the picture**: categories or values or classes with effectifs or fréquences, and the five numbers of a box plot. A later checker can compute from it; a later `plot` or `figure` block does not have to reuse it.
5. **Later blocks are additive.** `plot` and `figure` must be addable as further block types with their own validation, without changing the `chart` block or the replay of stored cards.
6. **Validation lives in `app/services/tools/board.py` and the domain model**, following the split of R4.7; model output is untrusted and a failure is a tool result, never an HTTP error.

### 4.2 Performance

1. The `display_board` declaration is in the cached prefix. Its schema grows once, is pinned by `tests/fixtures/board_declarations.json`, and stays compact: descriptions short, no examples in the schema. `scripts/smoke.py` passes in both modes after the change.
2. A chart renders without visible delay on a mid-range laptop and a tablet, and the board does not re-render charts that did not change.

### 4.3 Security

1. No model-supplied markup, style, colour, URL or identifier reaches the DOM as anything other than text.
2. Chart data size is bounded in the schema (R4.6), so a tool call cannot make the board draw an unbounded number of elements.

### 4.4 Reliability and quality

1. Offline tests: every R4 refusal, one accepted chart per R2 kind, decimal-comma and interval formatting (R3), the replay of a stored chart card, and the prefix byte-stability tests updated for the intended change.
2. Frontend tests follow the existing shape: pure helpers (scales, formatting, cumulative sums) tested outside React, each kind mounted under jsdom.
3. The manual checklist in `documentation/` gains a statistics lesson: a chart in an explanation, a reading exercise, a histogram with unequal classes.

### 4.5 Usability

1. A chart fits the board's width from 400 px up, and stays legible at the widths the board takes in the lesson's split view.
2. It follows the design system: `oklch` tokens, one series colour unless the chart needs to tell categories apart (pie chart, grouped series), sober gridlines, math as the hero. Colour signals meaning, not decoration.
3. Accessible: each chart has an accessible name, and its series is available to a screen reader as a table.
4. A chart may draw itself on appearance (bars growing, polygon tracing), once, and not under `prefers-reduced-motion`.

## 5. Open questions for the design

1. **Histograms with unequal amplitudes.** Courses differ: heights as effectif per unit of amplitude, per standard amplitude, or a refusal of unequal classes. Whether the block carries the convention, or the pack's convention is reflected in a field Célestin sets.
2. **Recharts or our own SVG** for each kind, given the notation rules of R3 and the progressive drawing of 4.5.4.
3. **Building a chart step by step** (bars added one by one as Célestin explains): redisplaying the card with more data, as a worked example does today, or a field on the block. The first costs nothing new.
4. **Which cards take a chart.** R1.2 adds it to `worked_example` and `exercise`, which today have no blocks: a `chart` field on each, or a general `blocks` list on both.
5. **Whether R6.3 can be checked in the tool** (a chart kind must appear in the pack's representations section) or stays prompt text measured by the probe, like the rest of the pack restriction.
