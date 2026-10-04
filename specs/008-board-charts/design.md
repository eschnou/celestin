# 008 — Charts on the board: design

## 1. Overview

A chart is a new **block** on the board, `{"type": "chart", "chart": {...}}`, where `chart` is a discriminated union on `kind` over six statistical chart shapes. Célestin supplies statistics (categories, values or class bounds, counts, the five numbers of a box plot) and never geometry. The frontend draws each kind with our own SVG components from those statistics. Text inside a chart is React text nodes or KaTeX, so no model output ever becomes markup.

Validation is split as the board already does. The card model holds the structural rules that never change (types, enums, bounds, non-negative values). `display_board` holds the rules that could change (matching lengths, ordering, sums, integers, per-card limits), so stored cards keep replaying (R4.7).

Nothing else moves: one tool, no new SSE event, and the same reducer, whiteboard and voice bridge. The tool declaration grows once, which invalidates the cached prefix once.

### 1.1 Decisions resolving the requirements' open questions

| Q | Decision | Why |
|---|---|---|
| 1 — histogram with unequal amplitudes | **Always area-proportional.** Height = value × `reference_amplitude` / amplitude. `reference_amplitude` is optional and defaults to the smallest amplitude. With equal amplitudes the height is the value. Célestin titles the vertical axis per the pack (« effectif pour une amplitude de 5 »). | Area-proportionality is what a histogram is. The only thing courses vary is the reference amplitude, which is a field. A course that refuses unequal classes simply never gets any. |
| 2 — Recharts or own SVG | **Own SVG for every kind.** Recharts stays installed and unused. No new dependency. | Recharts has no box plot, no unequal-width histogram, and no polygon at class bounds without custom shapes. Two rendering stacks cost more than one. Our own stack controls the ticks, the decimal comma and the entry animation, and it needs no `ResponsiveContainer` measurement dance. What is needed (linear scale, nice ticks, arc paths) is ~60 lines. |
| 3 — building step by step | **Redisplay the card with more data**, as a worked example does today. No field. | Costs nothing new. The entry animation plays on each display (§3.6). |
| 4 — which cards take a chart | `explanation` through its `blocks`. `worked_example` and `exercise` gain one optional field, `drawing: ChartBlock \| None`. | One chart per exercise or worked example is enough. The field is named for the family, so `plot` and `figure` join it as a union later without a new field (NFR 4.1.5). |
| 5 — "only kinds the pack names" in the tool | **Prompt text, measured by the probe.** | Course names vary (« diagramme en bâtons » / « à bâtons » / « diagramme en tiges »). A string check would refuse legitimate charts, and the rule is the pack restriction, which is measured everywhere else. |

## 2. Architecture

```
model ──display_board{card}──▶ registry._parse ── DisplayBoardArgs (pydantic)
                                  │   card model: types, enums, bounds, ≥ 0      app/domain/chart.py
                                  │   _maths_is_delimited (existing)
                                  ▼
                               display_board(args, ctx)                          app/services/tools/board.py
                                  ├─ _definition_refusal (existing)
                                  ├─ chart_refusal(chart) per chart ───────────  app/services/tools/charts.py
                                  │     lengths, order, sums, integers, labels
                                  ├─ log chart_displayed / chart_refused
                                  ▼
                               BoardSet ──board.set event (unchanged)──▶ browser
                                                                           │
    whiteboard.tsx ── ExplanationBoard ─ Blocks ─ BlockView case "chart" ──┤
                   ── WorkedExampleBoard / ExerciseBoard ─ card.drawing ───┤
                                                                           ▼
                                             components/celestin/charts/ChartView
                                               ├─ useWidth (ResizeObserver)
                                               ├─ series.ts  heights, cumulative points, angles, class labels
                                               ├─ scale.ts   linear scale, nice ticks, fr number format
                                               ├─ Bars | Sticks | Histogram | Cumulative | Pie | Box   (SVG)
                                               ├─ axis titles, caption, legend  (RichText, HTML)
                                               └─ <table class="sr-only">  the series, for screen readers
```

## 3. Components and interfaces

### 3.1 Domain — `app/domain/chart.py`, new

Chart models live in their own module. `domain/board.py` imports `ChartBlock` and adds it to `Block`. Models are in §4.1.

### 3.2 `app/domain/board.py`

- `Block` gains `ChartBlock`. `ExplanationCard.blocks` is unchanged (1–12).
- `WorkedExampleCard` and `ExerciseCard` gain `drawing: ChartBlock | None = None`.
- `app/api/schemas/board.py` re-exports the new models.

A stored card without `drawing` validates as before. No migration: cards live in the browser (parcours) or in `conversations.entries` JSON (discussion), and both replay through the model.

### 3.3 Tool rules — `app/services/tools/charts.py`, new

```python
def chart_refusal(chart: Chart) -> tuple[str, str] | None:
    """(rule, French message naming the field) or None."""
```

| Rule code | Applies to | Refused when |
|---|---|---|
| `lengths` | bars, pie: `categories`/`values`; sticks: `x`/`values`; histogram, cumulative: `len(bounds) == len(values) + 1` | lengths differ |
| `order` | sticks `x`, histogram/cumulative `bounds` | not strictly increasing |
| `repeated` | bars, pie `categories` | a category repeated (case- and space-insensitive) |
| `exercise_values` | the `drawing` of an `exercise` | `show_values` set: the chart is on the board while the exercise is open (verify pass, tasks D12) |
| `numeric_categories` | bars | every category parses as a number: a discrete variable, to draw as `sticks` (added after the first probe run, tasks D8) |
| `integers` | `measure == "effectif"` | a value not an integer |
| `sum` | `measure == "frequence"` / `"pourcentage"` | sum outside 1 ± 0,005·n / 100 ± 0,5·n (n = number of values: each rounded to its last digit) |
| `empty` | every counting chart | all values zero |
| `box_order` | each box | not minimum ≤ q1 ≤ median ≤ q3 ≤ maximum |
| `layers` | histogram | `bars` false and `polygon == "none"` |
| `reference` | histogram | `reference_amplitude` set while amplitudes are equal (it would silently rescale the bars) |
| `label_math` | `categories`, box `label` | contains `$` (drawn as SVG text, not typeset) |

`charts_refusal` also refuses (rule `per_card`) an `explanation` card with more than 2 chart blocks. Where a block can sit on a card is `card_blocks(card)` in `app/domain/board.py`, shared by the tool and `scripts/probe.py`.

Messages are French and name the path, following `_definition_refusal`: « Le graphique `blocks[2]` : 6 classes demandent 7 bornes, il y en a 6. »

`display_board` becomes:

```python
def display_board(args, ctx):
    if refusal := _definition_refusal(args.card, ctx.pack):
        raise ToolValidationError(refusal)
    charts = list(_charts(args.card))          # (path, Chart) in card order
    if refusal := _chart_refusal(args.card, charts, ctx):   # logs chart_refused
        raise ToolValidationError(refusal)
    if charts:
        log.info("chart_displayed", extra={... "kinds": [c.kind for _, c in charts]})
    return BoardSet(card=args.card, marker=args.card.marker)
```

The existing `_bare_commands` check walks every prose field, so axis titles, captions and categories are covered without change. The enum fields (`kind`, `measure`, `closed`, `direction`, `polygon`) never contain a backslash.

### 3.4 Registry — `app/services/tools/registry.py`

The `display_board` description gains one clause: « … ; un bloc `chart` dessine un graphique statistique à partir de données. » Declaration order and `strict=False` are unchanged. Both `tests/fixtures/board_declarations.json` and the prefix sha fixtures are regenerated once, on purpose.

### 3.5 Prompts

`prompts/tutor.fr.md`, « Le tableau », gains:

- A chart is the `chart` block: Célestin gives the data, never a drawing, and the board computes nothing that the course defines (quartiles, the median or mean of grouped data). Those come from Célestin, following the pack.
- Only representations the pack names, under its name, following its conventions (class closure, reference amplitude, polygon closed or not).
- `show_values` stays false when the student must read the chart. A chart the student must build is not displayed while the exercise is open; it may be shown after the attempt, as the correction.
- To build a chart step by step, redisplay the card with more data.

The `<!-- VOICE -->` block of `tutor.fr.md` gains one line: a chart is not read out value by value; Célestin says what it shows and points at it.

`prompts/templates/mathematics.pack.fr.md` (no new level-2 heading, so every stored pack still validates, R6.4):

- § 3 « Conventions de notation »: the comment adds the graphical representations the course uses, each with its name as the material writes it and its conventions (class closure, what each axis carries, unequal classes and the reference amplitude, polygon closed or open, quartile definition).
- § 4, per notion: « **Représentation graphique** : … », with the chart's data when the material gives them.

`prompts/transcription/transcribe.fr.md` rule 7: a chart's `[figure : …]` keeps its kind, axis titles, categories or classes, and every value that can be read, and still invents none. `prompts/authoring/pack.fr.md`: a figure's values go into the notion's « Représentation graphique ».

The physics template is unchanged: physics graphs are `plot`, a later spec.

### 3.6 Frontend

**Types** — `src/lib/tutor/types.ts` mirrors §4.1: `Chart` (union on `kind`), `ChartBlock`, `Block` gains it, and `WorkedExampleCard` / `ExerciseCard` gain `drawing?: ChartBlock | null`.

**Placement** — `BlockView` gains `case "chart"`. `WorkedExampleBoard` draws `card.drawing` between the statement and the steps; `ExerciseBoard` between the statement and the hint.

**`src/components/celestin/charts/`**, new:

| File | Contents |
|---|---|
| `format.ts` | `formatNumber(n)`: `Intl.NumberFormat("fr-BE", {maximumFractionDigits: 4})`, giving a decimal comma and a narrow no-break space for thousands. `formatValue(n, measure)` adds ` %` for `pourcentage`. `classLabel(a, b, closed)` gives `[a ; b[` or `]a ; b]`. |
| `scale.ts` | `linear(domain, range)`, `niceTicks(min, max, count≈5)` (steps 1, 2, 5 × 10ᵏ, exact decimals, no float noise). |
| `series.ts` | Pure geometry from statistics: `histogramRects(bounds, values, reference?)`, `polygonPoints(…, "open" \| "closed")` (closed adds zero points at the midpoints of the two adjacent virtual classes of the same amplitude as the end classes), `cumulativePoints(bounds, values, direction)`, `pieArcs(values)`, `boxGeometry(box)`. |
| `use-width.ts` | `useWidth(ref)`: `ResizeObserver`, with a 560 px fallback when it is absent (jsdom, SSR). |
| `chart-view.tsx` | `ChartView({block})`: frame, y title above the axis on the left, x title under the axis on the right, caption centred below (all `RichText`), legend (pie, several boxes), `<table className="sr-only">` with the series and its class labels, and `role="img"` + `aria-label` on the SVG. It dispatches on `kind`. |
| `bars.tsx`, `sticks.tsx`, `histogram.tsx`, `cumulative.tsx`, `pie.tsx`, `box.tsx` | One SVG component per kind, drawn at the measured pixel width (not a scaled `viewBox`, so 12 px text stays 12 px at 400 px). Height `clamp(220, width × 0.55, 340)`. |

Drawing rules:

- **Counting charts** (bars, sticks, histogram, cumulative): y axis from 0, nice ticks with horizontal gridlines (reading exercises depend on them, R5.1), values on the marks only when `show_values`.
- **x axis:** sticks tick at each value; histogram and cumulative tick at each bound. Labels that would overlap are thinned to every second one below 28 px spacing.
- **Pie:** starts at 12 o'clock, clockwise. An HTML legend beside it (below it under 480 px) carries category, swatch and value when `show_values`.
- **Box plot:** horizontal, boxes stacked with their labels, a nice-ticked numeric axis, five numbers written only when `show_values`.

**Styling** — `styles.css`:

- Series fill `--chart-1`. Polygon and cumulative stroke `--chart-4` when drawn over bars, `--chart-1` alone. Pie sectors use `--chart-1…8`, so `--chart-6…8` are added: `:root` value, `.dark` value and `@theme inline` registration (the three-edit rule).
- Axes and grid use `--border` and `--muted-foreground`.
- Two utilities: `chart-grow` (bars scale from the axis, 400 ms, `transform-box: fill-box`) and `chart-trace` (lines drawn through `pathLength=1` and `stroke-dashoffset`). Both are disabled under `prefers-reduced-motion`.

No tooltip, no hover state, no event handler on any chart element (R5.3).

## 4. Data models

### 4.1 Chart models — `app/domain/chart.py`

```python
Value     = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Coord     = Annotated[float, Field(allow_inf_nan=False)]
Label     = Annotated[str, Field(min_length=1, max_length=40)]
AxisTitle = Annotated[str, Field(min_length=1, max_length=80)]
Caption   = Annotated[str, Field(min_length=1, max_length=200)]
Measure   = Literal["effectif", "frequence", "pourcentage"]
Closed    = Literal["left", "right"]            # [a ; b[  or  ]a ; b]

class _Counts(_Model):                          # every counting chart
    measure: Measure
    show_values: bool = False
    caption: Caption | None = None

class BarChart(_Counts):                        # diagramme en barres (qualitative)
    kind: Literal["bars"] = "bars"
    categories: Annotated[list[Label], Field(min_length=1, max_length=20)]
    values:     Annotated[list[Value], Field(min_length=1, max_length=20)]
    x_title: AxisTitle | None = None
    y_title: AxisTitle

class StickChart(_Counts):                      # diagramme en bâtons (discrete)
    kind: Literal["sticks"] = "sticks"
    x:      Annotated[list[Coord], Field(min_length=1, max_length=20)]
    values: Annotated[list[Value], Field(min_length=1, max_length=20)]
    polygon: bool = False                       # polygone joining the stick tops
    x_title: AxisTitle
    y_title: AxisTitle

class Histogram(_Counts):
    kind: Literal["histogram"] = "histogram"
    bounds: Annotated[list[Coord], Field(min_length=2, max_length=21)]
    values: Annotated[list[Value], Field(min_length=1, max_length=20)]
    closed: Closed
    reference_amplitude: Annotated[float, Field(gt=0)] | None = None
    bars: bool = True
    polygon: Literal["none", "open", "closed"] = "none"
    x_title: AxisTitle
    y_title: AxisTitle

class CumulativePolygon(_Counts):               # polygone des effectifs / fréquences cumulé(e)s
    kind: Literal["cumulative"] = "cumulative"
    bounds: Annotated[list[Coord], Field(min_length=2, max_length=21)]
    values: Annotated[list[Value], Field(min_length=1, max_length=20)]   # per class, not cumulated
    closed: Closed
    direction: Literal["increasing", "decreasing"]
    x_title: AxisTitle
    y_title: AxisTitle

class PieChart(_Counts):                        # diagramme circulaire
    kind: Literal["pie"] = "pie"
    categories: Annotated[list[Label], Field(min_length=1, max_length=8)]
    values:     Annotated[list[Value], Field(min_length=1, max_length=8)]

class Box(_Model):
    label: Label | None = None
    minimum: Coord; q1: Coord; median: Coord; q3: Coord; maximum: Coord

class BoxPlot(_Model):                          # boîte à moustaches
    kind: Literal["box"] = "box"
    boxes: Annotated[list[Box], Field(min_length=1, max_length=4)]
    x_title: AxisTitle | None = None
    show_values: bool = False
    caption: Caption | None = None

Chart = Annotated[Union[BarChart, StickChart, Histogram, CumulativePolygon, PieChart, BoxPlot],
                  Field(discriminator="kind")]

class ChartBlock(_Model):
    """A statistical chart drawn by the board from data. Give statistics, never
    coordinates or drawings."""
    type: Literal["chart"] = "chart"
    chart: Chart
```

The block nests the chart because `Block` is discriminated on `type`, and six members cannot share `type: "chart"`. The docstring is kept to what the model needs, since it becomes schema text in the cached prefix. The other models carry no docstrings.

Frequency polygon alone: `sticks` with `polygon` and its bars hidden is not offered. The discrete polygon is drawn over its sticks, as courses show it. The continuous polygon alone is `histogram` with `bars: false`.

### 4.2 Wire and frontend types

The wire shape is the model dump, as for every card. The TypeScript mirror is §3.6. No DTO, table, migration or SSE event changes.

## 5. Error handling

| Situation | Where | Answer |
|---|---|---|
| Wrong type, unknown `kind`, a bound violated, a negative value, a non-finite number | `registry._parse` (pydantic) | `ToolValidationError("Arguments invalides. …")` naming the field, as today |
| A §3.3 rule | `display_board` → `chart_refusal` | `ToolValidationError` with the French message, logged `chart_refused` |
| A stored card whose chart was accepted when displayed | replay through the model | Validates: only structural rules live on the model |
| A malformed chart reaching the browser anyway (a hand-edited stored conversation, a future model drift) | `ChartView` | Defensive: lengths are truncated to the shortest, non-finite and negative values drawn as 0, an empty or all-zero series draws the axes and a « Graphique vide » note. It never throws, and the rest of the card still renders. |
| `ResizeObserver` missing | `useWidth` | 560 px fallback |

A refusal is a tool result the model reads and corrects, never an HTTP error or an `error` event (spec 001 R4.6).

## 6. Testing strategy

**Backend, offline.**

- `test_chart_models.py`: one valid payload per kind; structural refusals (unknown kind, negative value, `NaN`, too many categories, a label over 40 characters); `ChartBlock` inside an explanation and as `drawing` on a worked example and an exercise; cards without `drawing` still validate.
- `test_chart_rules.py`: each rule code of §3.3, one refusal and one boundary acceptance (frequencies summing to 0,999 with 3 values accepted; 0,98 refused; 7 bounds for 6 classes accepted).
- `test_registry.py`: `display_board` with a chart dispatches; the per-card limit; a LaTeX command outside `$…$` in a `y_title` is refused by the existing check.
- Logging: `chart_displayed` carries kinds and `chart_refused` carries the rule, both with ids only and no values or labels (caplog).
- Fixtures regenerated on purpose: `board_declarations.json`, `system_text_sha.txt`, `system_text_sha_discussion.txt`. `test_realtime_declarations_*` pass unchanged (derived).
- A discussion replay: a stored `display_board` entry with a chart restores through `marker_for` and `sessionFromEntries`.

**Frontend, vitest.**

- `format.ts`: `0,45`, `12,5 %`, `1 234`, `[10 ; 20[`, `]10 ; 20]`, no `0.30000000000000004`.
- `scale.ts`: `niceTicks(0, 37)` → `0, 10, 20, 30, 40`; small decimals; a flat domain.
- `series.ts`: histogram heights with equal and unequal amplitudes and an explicit reference; open and closed polygons; increasing and decreasing cumulative points; pie angles summing to 2π; box geometry.
- `chart-view.test.tsx` (jsdom): each kind mounts; `show_values` false writes no value into the SVG text; the sr-only table carries the series with class labels; no element has an event handler or `title` child (no tooltip); a malformed series renders without throwing.
- `whiteboard.test.tsx`: a chart in an explanation, a worked example and an exercise.

**Live scripts.**

- `tests/fixtures/material/maths_statistique.txt` (one-variable descriptive statistics with a discrete and a grouped series, figures described as the transcription writes them) added to `scripts/authoring_eval` FIXTURES.
- `tests/fixtures/chapters/statistique/` (`pack.md`, `curriculum.yaml`, hand-checked, in the `courses/chapitre_1` format) for `scripts/probe.py --chapter-dir` and `scripts/smoke.py`.
- `scripts/probe.py` gains the R7.3 cases, in both modes: a reading exercise (flag: `show_values` true on an open exercise's chart), « construis l'histogramme » (flag: a histogram displayed before the student's attempt), a chart kind absent from the pack (flag: it is drawn anyway).
- `scripts/smoke.py` passes in both modes after the schema change (cache warm on the second turn).

## 7. Performance

- **Prefix.** The schema adds roughly 1–1,5 k tokens to the cached prefix, once per mode and chapter. The first turn after the deploy misses the cache for every chapter; after that it is cached as before. `smoke` confirms.
- **Rendering.** Six small SVGs, at most ~40 marks each. `ChartView` is memoised on the block, and cards in the history strip are not rendered, as today. `useWidth` updates only on real size changes.
- **No new dependency**, so the bundle does not grow beyond our components.

## 8. Security

- Chart text (titles, captions, categories) is rendered as React text or through `RichText` → KaTeX `trust: false`. Categories are SVG `<text>` children, which React escapes. No `dangerouslySetInnerHTML` outside `Math`.
- The model supplies no colour, class, style, URL, id or path data: every visual attribute comes from our tokens and geometry.
- Sizes are bounded in the schema (20 classes, 8 sectors, 4 boxes, label lengths, 2 charts per explanation), so a tool call cannot make the board draw an unbounded number of elements.
- Non-finite numbers are refused by the model (`allow_inf_nan=False`), and the renderer clamps defensively (§5).

## 9. Monitoring and observability

- `chart_displayed`: `turn_id` when in a text turn, `user_id`, `chapter_id`, `mode`, `kinds`. Emitted by the handler, so both channels (text turn and `/api/voice/tool`) are covered.
- `chart_refused`: the same ids plus `rule` (a §3.3 code). Structural refusals keep showing as `display_board:invalid` in `turn_complete.tools`.
- No value, label or title is ever logged.
- The probe transcripts are read against the checklist of §6. The R5 and R6.3 rates are reported per mode with the existing leak figures.

## 10. Deviations from the requirements

- **D1 — R2.4 « frequency polygon alone ».** Offered for continuous series (`histogram` with `bars: false`). For a discrete series the polygon is always drawn over its sticks, which is how courses present it.
- **D2 — R3.2 class labels.** The chart's x axis carries the bounds as numbers, as a histogram is drawn. The interval notation (`[10 ; 20[`) appears in the accessible table and in any value Célestin writes in the caption. Class labels are not printed under each bar.
- **D3 — R6.1 « a place for the course's representations ».** A bullet in § 3 and a line per notion in § 4, not a new level-2 heading, so that every stored pack keeps validating against the template (R6.4).
