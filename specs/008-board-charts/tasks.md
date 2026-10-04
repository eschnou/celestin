# 008 — Tasks

Phases are testable increments in dependency order. Each ends with a check the user can run. Requirement ids refer to `requirements.md`, section numbers to `design.md`. Tick tasks as they land; record design deviations in the Deviations section at the end.

Checks for every phase that touches a side: backend `uv run pytest`; frontend `npx tsc --noEmit`, `npm run lint` (0 errors), `npm test`.

Fixtures regenerated **on purpose** in this spec, and only in the task that names them: `tests/fixtures/board_declarations.json` (0.5: the tool schema) and `tests/fixtures/render/system_text_sha.txt` / `system_text_sha_discussion.txt` (2.4: the prompt text; the tool schema is not part of it, so Phase 0 must leave them untouched). Any other golden or sha that moves is a bug.

## Phase 0 — The chart block in the backend

**Goal:** `display_board` accepts a chart in an explanation, a worked example and an exercise, refuses a malformed one with a French message naming the field, and logs both. Nothing is drawn yet. **Done when** every §3.3 rule has a refusal test and a stored card without `drawing` still validates.

- [x] 0.1 `app/domain/chart.py` (§4.1): `Value`, `Coord`, `Label`, `AxisTitle`, `Caption`, `Measure`, `Closed`, `_Counts`, `BarChart`, `StickChart`, `Histogram`, `CumulativePolygon`, `PieChart`, `Box`, `BoxPlot`, `Chart`, `ChartBlock` (the only docstring). Test `unit/test_chart_models.py`: one valid payload per kind; unknown `kind`, negative value, `NaN`/`inf`, 21 categories, 9 sectors, 5 boxes, a 41-character label, each refused.
- [x] 0.2 `app/domain/board.py` (§3.2): `ChartBlock` in `Block`; `drawing: ChartBlock | None = None` on `WorkedExampleCard` and `ExerciseCard`; re-exports in `app/api/schemas/board.py`. Tests in `unit/test_board_models.py`: a chart inside an explanation and as `drawing` on both cards; the existing `VALID` cards (no `drawing`) unchanged.
- [x] 0.3 `app/services/tools/charts.py` (§3.3): `chart_refusal(chart) -> (rule, message) | None` with rules `lengths`, `order`, `repeated`, `integers`, `sum`, `empty`, `box_order`, `layers`, `reference`, `label_math`. Test `unit/test_chart_rules.py`: per rule one refusal (message names the field) and one boundary acceptance — fréquences 0,333 + 0,333 + 0,333 accepted, 0,98 over 2 values refused; 7 bounds for 6 classes accepted, 6 refused; `12.0` accepted as an effectif, `12.5` refused.
- [x] 0.4 `app/services/tools/board.py` (§3.3): `_charts(card)` yields `(path, chart)` in card order (explanation blocks, `drawing`); `per_card` limit of 2 per explanation; `display_board` runs the chart rules after `_definition_refusal`, logs `chart_refused` (`user_id`, `chapter_id`, `mode`, `rule`) before raising and `chart_displayed` (`…`, `kinds`) on success. Tests in `unit/test_registry.py`: dispatch with a chart; a third chart refused; a `\frac` outside `$…$` in a `y_title` refused by the existing check; caplog shows ids, rule and kinds and no label, title or value.
- [x] 0.5 `app/services/tools/registry.py` (§3.4): the `display_board` description clause. Regenerate `tests/fixtures/board_declarations.json`. `test_realtime_declarations_*` pass unchanged.
- [x] 0.6 Replay: a stored discussion entry holding a `display_board` call with a chart restores through `marker_for` and the `StoredEntry` DTO. Test in `unit/test_discussion_schema.py`.

**Verify:** `uv run pytest` green; `uv run python -m app.services.tools.dump_schema | grep -c '"chart"'` is non-zero in both modes; `uv run python -m scripts.smoke` reports a cache hit on turn 2 in both modes (the first run after the change may miss once).

**Verified** (2026-09-28): 774 passed; the prompt-text sha fixtures untouched, `board_declarations.json` regenerated on purpose (8 393 → 16 099 characters, ≈ 2 k tokens: above §7's 1–1,5 k estimate, see Deviations D5); `dump_schema` shows `chart` in both the parcours (5 tools) and discussion (2 tools) sets; `scripts.smoke` CACHE OK, 17 347 cached tokens on the parcours turn 2 and 16 619 in discussion.

## Phase 1 — Drawing the charts

**Goal:** every chart kind renders on the board from its data, in the course's notation, at 400 px and at desktop width, light and dark, with an accessible table and no tooltip. **Done when** each kind mounts in a card and the pure helpers are covered.

- [x] 1.1 `src/lib/tutor/types.ts` (§3.6): `Measure`, `BarChart`, `StickChart`, `Histogram`, `CumulativePolygon`, `PieChart`, `Box`, `BoxPlot`, `Chart`, `ChartBlock`; `Block` gains it; `drawing?: ChartBlock | null` on `WorkedExampleCard` and `ExerciseCard`. `npx tsc --noEmit` clean.
- [x] 1.2 `components/celestin/charts/format.ts`: `formatNumber`, `formatValue`, `classLabel`. Test `charts/__tests__/format.test.ts`: `0,45`, `12,5 %`, `1 234` (narrow no-break space), `[10 ; 20[`, `]10 ; 20]`, `0.1 + 0.2` → `0,3`.
- [x] 1.3 `charts/scale.ts`: `linear`, `niceTicks`. Test `scale.test.ts`: `niceTicks(0, 37)` → `0, 10, 20, 30, 40`; `(0, 0.37)` → steps of `0,1`; a flat domain `(5, 5)` gives a usable range; no float noise in any tick.
- [x] 1.4 `charts/series.ts`: `histogramRects`, `polygonPoints` (open, closed), `cumulativePoints` (increasing, decreasing), `pieArcs`, `boxGeometry`, and the defensive `sanitise` of §5 (truncate to the shortest list, clamp non-finite or negative to 0). Test `series.test.ts`: equal amplitudes → heights are the values; `[0;10[`, `[10;30[` with 10 and 10 → heights 10 and 5; explicit `reference_amplitude`; closed polygon adds the two outer zero points; cumulative increasing starts at 0 on the first bound, decreasing ends at 0 on the last; pie angles sum to 2π; mismatched lengths truncated.
- [x] 1.5 `charts/use-width.ts`: `ResizeObserver` with the 560 px fallback. Covered through 1.7 under jsdom (no observer).
- [x] 1.6 `charts/bars.tsx`, `sticks.tsx`, `histogram.tsx`, `cumulative.tsx`, `pie.tsx`, `box.tsx` (§3.6 drawing rules): pixel-width SVG, height `clamp(220, w × 0.55, 340)`, y from 0 with nice ticks and gridlines, bound ticks thinned below 28 px, values drawn only when `show_values`, no handlers, no `<title>`.
- [x] 1.7 `charts/chart-view.tsx`: frame, y title above-left, x title below-right, caption, legend (pie; several boxes), `role="img"` + `aria-label`, `<table className="sr-only">` with class labels from `classLabel`, memoised on the block. Test `charts/__tests__/chart-view.test.tsx` (jsdom): each kind mounts; with `show_values: false` no value string appears in the SVG text; the sr-only table lists the series with `[10 ; 20[`; no element carries an `on*` prop or a `<title>`; a malformed series renders « Graphique vide » or truncated data without throwing.
- [x] 1.8 Placement: `BlockView` `case "chart"`; `WorkedExampleBoard` draws `card.drawing` between statement and steps; `ExerciseBoard` between statement and hint. Tests in `whiteboard.test.tsx`: a chart in each of the three cards.
- [x] 1.9 `styles.css`: `--chart-6…8` (`:root`, `.dark`, `@theme inline`); `chart-grow` and `chart-trace` utilities, off under `prefers-reduced-motion`. Pie colours from `--chart-1…8`.

**Verify:** with the dev server running, a temporary route (created for the check, deleted after, never committed) mounting one card per kind — screenshots at 1200 px and 400 px, light and dark: decimal commas, bounds on the histogram axis, legend under the pie at 400 px, nothing overflows. Then in a real lesson, ask Célestin « dessine-moi un diagramme en bâtons de 2, 5, 3 élèves pour les notes 12, 14, 16 » and see the chart (the schema already offers it).

**Verified** (2026-09-28): 282 frontend tests, `tsc` clean, lint 0 errors (`axes.tsx` adds `only-export-components` warnings, 5 after the simplify pass, of the kind `board-blocks.tsx` already has). A temporary `/zz-charts` route (deleted, never committed) showed every kind in its card at 1200 px and 400 px: decimal commas and `%`, bounds on the histogram axis with the unequal classes at the right areas, closed polygon, rotated category labels and thinned bounds at 400 px, the pie legend wrapping below the pie, no horizontal scroll. The first capture caught box-plot numbers colliding (« 10,5 » / « 11 »); fixed with three label lanes (`lanes` in `axes.tsx`, tested) and a taller row when values are shown. The dark check does not apply (D7). The real-lesson check (« dessine-moi un diagramme en bâtons… ») needs a signed-in student and is left to the user.

## Phase 2 — Célestin uses charts, and packs carry them

**Goal:** Célestin draws the course's representations at the right moments, keeps values hidden on reading exercises, and new packs record the course's charts. **Done when** a real lesson on the statistics fixture chapter produces charts and the prefix fixtures are regenerated once.

- [x] 2.1 `prompts/tutor.fr.md` « Le tableau » (§3.5): the four chart rules; `<!-- VOICE -->` block: the one line on charts in speech. `test_prompt_files.py` (neutral, marker-free) passes.
- [x] 2.2 `prompts/templates/mathematics.pack.fr.md` (§3.5, D3): § 3 comment gains the representations bullet; § 4 comment gains « **Représentation graphique** ». No level-2 heading changes. Test in `unit/test_pack.py`: `parse_template` yields the same headings as before; `tests/fixtures/packs/maths_valid.md` still indexes clean.
- [x] 2.3 `prompts/transcription/transcribe.fr.md` rule 7 and `prompts/authoring/pack.fr.md` (§3.5): chart values kept in `[figure : …]`, carried into « Représentation graphique », nothing invented.
- [x] 2.4 Regenerate `system_text_sha.txt` and `system_text_sha_discussion.txt`.
- [x] 2.5 Statistics fixtures (§6): `tests/fixtures/material/maths_statistique.txt` (a discrete series, a grouped series with unequal classes, a box plot, figures written as the transcription writes them) added to `scripts/authoring_eval.py` FIXTURES; `tests/fixtures/chapters/statistique/pack.md` and `curriculum.yaml`, hand-checked, in the `courses/chapitre_1` format. Test: the fixture pack indexes clean against the template and the curriculum's references resolve (reuse the helpers `scripts/chapter_files.py` uses).

**Verify:** `uv run python -m scripts.smoke --chapter-dir tests/fixtures/chapters/statistique` passes in both modes; in the app, a statistics chapter's lesson shows a chart in an explanation and a reading exercise without values on the chart.

**Verified** (2026-09-28): 776 passed; only the two prefix sha tests moved before 2.4 regenerated them. The maths template's headings are pinned unchanged (`test_pack.py`), so stored packs keep validating (D3). The fixture chapter validates like an editor save (`test_chapter_files.py`). Writing the material, a hand check of every answer caught three errors in my own draft (a mean of 962/25, not 960/25; Q₁ = 38 by the course's definition; an ambiguous « classe modale » with unequal classes), fixed before the pack was written from it. `scripts.smoke --chapter-dir tests/fixtures/chapters/statistique`: CACHE OK in both modes (11 117 / 10 464 cached tokens on turn 2). Its two turns open the lesson and stop at the title card, so chart behaviour is measured by the Phase 3 probes; seeing a chart in a real statistics lesson is left to the user.

## Phase 3 — Measurement, documentation and hand-off

**Goal:** the chart guardrails are measured and the repository describes the system as built. **Done when** the probe transcript reads clean against the §6 checklist and every check passes.

- [x] 3.1 `scripts/probe.py` (R7.3): a chart probe set in both modes, selected by `--charts` and run with `--chapter-dir tests/fixtures/chapters/statistique` (the existing sets stay on chapter 1) — a reading exercise, « construis l'histogramme », a chart kind absent from the pack. Flags printed per probe: `show_values` true on an open exercise's chart; a histogram displayed before the attempt; a kind the pack does not name drawn anyway.
- [x] 3.2 Run `uv run python -m scripts.probe --charts --chapter-dir tests/fixtures/chapters/statistique` (costs money; ask first) and `uv run python -m scripts.authoring_eval --file tests/fixtures/material/maths_statistique.txt`; read the transcript and the produced pack; record results under `## Probe runs`.
- [x] 3.3 `documentation/tutor-turn-pipeline.md` (the chart block, the validation split, the rules table, the logs); `documentation/chapters.md` (the pack's representations); `documentation/authoring.md` (figures keep their values); a manual checklist for a statistics lesson (R4.4.3) in the most fitting existing doc; `documentation/index.md` if a file is added.
- [x] 3.4 `frontend/CLAUDE.md` (`charts/`, the new tokens and utilities; Recharts still unused); `backend/CLAUDE.md` if the tools paragraph needs the chart rules.
- [x] 3.5 `specs/index.md` → Implemented. Run: `cd backend && uv run pytest && uv run python -m scripts.smoke`; `cd frontend && npx tsc --noEmit && npm run lint && npm test`.

**Verify:** every command in 3.5 exits 0; the probe transcript shows no chart values on an open reading exercise, no histogram before the attempt, and no chart kind outside the pack.

**Verified** (2026-09-28): 780 backend and 282 frontend tests, `tsc` clean, lint 0 errors. Probe and authoring results under « Probe runs ». `.gitignore` now covers `backend/probe-transcript*.md`.

## Simplify pass

Four review agents (reuse, simplification, efficiency, altitude) over the whole diff; applied:

**Depth** — `card_blocks(card)` in `app/domain/board.py` is now the one statement of where a block sits on a card; the tool's chart and definition rules and the probe's flags all read it (the probe had its own dict walk, which a new `drawing` slot would have silently escaped). The chart rules are one `match` per kind in `charts.py`, so which rules a kind gets, and in what order, reads in one place; the per-card limit moved beside them (`charts_refusal`). On the frontend, `sanitise` cleans a chart once in `ChartView` and every component assumes clean data (the defence had been spread over ten call sites, and 1.4's promised `sanitise` did not exist); `entries` is the one labelled series the table, the legend, `drawable` and `Bars` read. A test now imports every `scripts/*.py`, the root cause of D9.

**Simplification** — `valueFrame` + `CartesianSvg` hold the shell the four counting charts shared line for line; `Frame` lost its redundant `width`, `frame` its dead null branch, and `Box` builds its frame through it instead of re-hardcoding the margins. The box row with values is derived from the lane constants (`LANES`, `LANE_HEIGHT`). Chart fields share bases on both sides (`_Shown`, `_Counts`, `_Classes` / `Shown`, `Counts`, `Classes`). `drawing` renders through `BlockView`. `Ticks.step` went (only a test read it). Test payloads come from one `VALID` (backend) and one `fixtures.ts` (frontend, typed with `satisfies`, so the `as never` casts went).

**Efficiency** — `useWidth` measures before paint, so a chart no longer paints once at the 560 px fallback; `_definition_refusal` folds the pack only when a card has a definition. The step-by-step prompt line is bounded to two or three redisplays, since every redisplayed card stays in the transcript sent on each later turn. The registry's stale « ~2 ms » comment now says ~7 ms.

**Probe harness** — `ChartProbe` carries its section and builds its priors per mode, instead of padding tuples and filtering `start_section` back out; the reading flag looks at every chart of the turn, not only the exercise's; `PACK_CHART_NAMES` is tested against the fixture pack's own words.

**Skipped, with reasons** — stripping pydantic's generated `title` keys (and the `discriminator` maps) from the tool schema, ≈ 20 % of `display_board`'s bytes: a model-facing change to every tool that wants its own eval run (follow-up to D5); one `board_refused` log for definition and chart refusals alike, which would rename §9's log events and reach into the previous change's code.

**Re-verified after the pass**: 789 backend and 285 frontend tests, `tsc` clean, lint 0 errors; the temporary preview route (deleted) at 400 px shows every kind unchanged, box-plot numbers in their lanes.

## Verify pass fixes

From the `/sdd:verify` report (code review + spec compliance), applied:

- **`values` for classes is now told to the model** (the one high finding): a description on `values` and `reference_amplitude` in the schema, and a line in `tutor.fr.md` — per-class counts, never the pack's bar heights or cumulated points; the board computes those. `probe --charts` gained the course's histogram and cumulative polygon, with a `data` flag that catches either wrong shape (tested).
- **Years print as `2018`**: `useGrouping: "min2"`, a space between thousands only from five digits on.
- **`exercise_values`**: an exercise's chart may not write its values (D12), logged like the other rules.
- **Schema-level chart refusals are counted**: a `Tool.on_invalid` hook logs `chart_refused` with `rule: schema.<type>` when the card model refuses a chart, so R7.1's per-rule counts are whole.
- **Box plot on a phone**: label room capped at 30 % of the width, longer labels shortened with « … » (`fitLabel`, tested); the table keeps them whole.
- **Screen-reader table**: the value column is named after the measure (no more two « Valeur » columns for sticks); a cumulative polygon lists its points as drawn, cumulated.
- **Percentage axes** write their ticks with ` %`.
- **`probe --charts`** defaults to the statistics fixture chapter.
- **`spaced`** moved to a neutral `services/tools/text.py`.
- D10–D12 recorded; doc slips fixed (lint count, `authoring_eval` cost, « axis titles »).

Deferred, as the report recommended: raw LaTeX in the accessible label (#12), a total `sanitise` / error boundary for hand-edited stored charts (#13), `numeric_categories` refusing year bar charts (#11; `sticks` is the right fallback), the frontend half of the replay test (#15).

**Re-verified**: 794 backend and 289 frontend tests, `tsc` clean, lint 0 errors; prefix fixtures regenerated for the prompt and schema lines.

## Deviations

- **D4 — §9 `turn_id` on the chart logs.** `chart_displayed` / `chart_refused` carry `user_id`, `chapter_id`, `mode` and the kinds or rule, but no `turn_id`: the handler only sees `TurnContext`, which has no turn id, and adding one for a log field is not worth a context change. The turn is still recoverable from `turn_complete` (same user, chapter and time).
- **D5 — §7 prefix size.** The `display_board` schema grew by ≈ 2 k tokens, not 1–1,5 k: pydantic writes a `title` for every property. Cached after the first turn, so accepted as is; dropping the generated titles would shrink the whole schema and is a separate change.
- **D6 — §3.6 the screen-reader table.** It lists the categories, values or classes, but writes the counts **only when `show_values` is set**, as the chart does. Otherwise a reading exercise would carry its answers in the DOM for anyone to read (R5.3 wins over R4.5.3 there). The chart's data still reaches the browser inside the `board.set` event, as a check question's `correct_option_id` already does; hiding it from the client is out of scope.
- **D7 — Phase 1 « light and dark ».** The app never enables dark mode (nothing sets `.dark`, and `board`, `paper` and `quote` have no dark values), so charts were checked in light only. `--chart-6…8` still got their `.dark` values, per the three-edit rule.
- **D8 — §3.3 an eleventh rule, `numeric_categories`.** The first chart probe run caught Célestin drawing a discrete variable (number of siblings, categories `"0"`…`"4"`) as a qualitative `bars` chart while calling it a « diagramme en bâtons ». A `bars` chart whose categories all parse as numbers is now refused with a message pointing to `sticks`: mechanical, so it belongs in the tool rather than the prompt.
- **D9 — `scripts/authoring_eval.py` was broken on `main`.** It imported `points_a_verifier` from the runner and read `output.pack` / `output.title`, both gone since the agent returns `AuthoringOutput(content, usage)`; it failed on import before spending anything. Fixed minimally (`content.pack`, `content.title`, `content.index.to_verify`) so 3.2 could run.
- **D10 — R3.4, maths in category labels.** R3.4 allows `$…$` in category names; the tool refuses it (`label_math`) because categories and box labels are SVG text, which KaTeX cannot typeset. Axis titles and captions keep `$…$`.
- **D11 — §5 and §3.6, three small drifts.** An empty chart shows « Graphique vide » without axes; several boxes are labelled on their rows, not in a legend; the accessible name sits on the drawing's wrapper (`role="img"`), not on the SVG. Each is simpler and reads the same.
- **D12 — R5.1, part of it moved into the tool.** The verify pass noted that an exercise's `drawing` is by definition on the board while the exercise is open: `show_values` there is now refused (`exercise_values`). Charts in other cards keep the prompt rule and the probe.

## Probe runs

**2026-09-28, `probe --charts`, gpt-5.6-terra, statistics fixture chapter.**

- Run 1 — 7 of 8 clean, 1 flagged. Reading exercises kept `show_values: false` in both modes; « construis l'histogramme » set the exercise with `drawing: null` in both modes; a « diagramme en barres » request got the course's diagramme circulaire (a worked example in the parcours, a sentence in discussion). **Flagged:** in discussion, a discrete variable (number of siblings) drawn as `bars` with categories `"0"`…`"4"` and captioned « Diagramme en bâtons ». Fixed in the tool (D8), not the prompt.
- Run 2, after D8 — 8 of 8 clean. Both reading exercises now `sticks` with `show_values: false`; no histogram before an attempt; no kind outside the pack. In the parcours, « montre-moi le diagramme en bâtons » drew the course's notes (10 → 1 … 16 → 2) with its polygon, values shown, which is right for an explanation.
- Not a failure, noted: in run 1 the parcours answered the same request with the section's title card and « passe à l'étape suivante » first — the title-card pacing of the previous change working as intended.

**2026-09-28, `authoring_eval --file tests/fixtures/material/maths_statistique.txt`.** OK on the first attempt of both stages, 14 sections, 0 « Points à vérifier », 0,209 USD. The pack's § 3 lists the six representations with their conventions; five notions carry a « **Représentation graphique** » with the chart's axes and every value from the material (the histogram's heights 4 ; 12 ; 15 ; 5 ; 1,25 included). R6.1–R6.2 hold on real output.

**2026-09-28, run 3 (after the verify fixes), `probe --charts`, 6 probes × 2 modes.** 10 of 12 clean. In discussion, both new `data` probes drew the course's charts with the right shape: the histogram with per-class counts 8 ; 12 ; 15 ; 10 ; 5 and `reference_amplitude: 5` (not the pack's heights), the cumulative polygon with per-class percentages 16 ; 24 ; 30 ; 20 ; 10 (not the pack's cumulated points). The two parcours flags are the probe's, not the data's: in the locked lesson Célestin follows the section's beats — the title card and « passe à l'étape suivante », or the first beat (the pie chart) — instead of jumping to the histogram, so no grouped chart reached the board to check. Reading and « construis » probes stayed clean in both modes.
