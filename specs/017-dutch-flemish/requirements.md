# 017 — Dutch (Flemish): a third interface and course language

## 1. Introduction

Célestin speaks French and English (specs 010, 011). Flanders is the other half of Belgian secondary education; its students work from material in Dutch. This epic adds **Dutch as written and taught in Flanders** (`nl`) as a third **interface language** and a third **course language**, end to end: a Flemish student registers in Dutch, creates a Dutch course, uploads Dutch material and is taught in Dutch, with the board drawing Flemish notation.

Spec 011 built the structure for this: a language is `by_language` tables, a `*.{lang}.md` prompt set, a message catalog, a formatter and fixtures; no component or route names a language. This epic is that addition, and also the test of that claim: where adding `nl` needs a change outside those places, the epic fixes the structure and says so.

Vocabulary (unchanged from 010 and 011):

- **Interface language** — `users.locale`. Buttons, errors, statuses, accessibility text. Never reaches the model.
- **Course language** — `courses.language`. Immutable. The language of the material, pack, curriculum, Célestin's speech, voice and the board's notation.
- **`nl`** — the code for both. It stands for *Flemish Dutch*: standard Dutch (Standaardnederlands) with the Belgian school vocabulary and the Flemish notation, the way `fr` stands for French-speaking Belgian and not for France. `nl-BE` and `nl-NL` browsers both resolve to `nl` (primary-subtag rule of spec 010).

Scope:

- `nl` in `Locale` and `CourseLanguage` (both sides), the interface catalogs, the settings screen and the create-course form.
- A Dutch prompt set beside the French and English ones, for the four subjects offered.
- Dutch authoring and transcription (markers, pack templates, numbering words, agent words, issue texts).
- Every `by_language` table, tool-rule vocabulary and notation pattern, the board's formatter and learner sentences, voice.
- Dutch fixtures, goldens, probes, and the evals harness flag.
- Documentation, `CLAUDE.md` and the brief updated to say what is now true.

Out of scope:

- Netherlands conventions (`nl-NL`: `⟨a, b⟩`-style intervals, Dutch school vocabulary where it differs). A Dutch-from-the-Netherlands student is served by `nl` as Flemish conventions; no second variant (the structure does not preclude a later `nl-NL`).
- Dialect and *tussentaal*: Célestin writes standard Dutch.
- Frisian, Afrikaans, any fourth language.
- Changing a course's language, translating an existing course or conversation, detecting the material's language.
- Content we author ourselves (brief §11): the work is prompts, templates, rules and fixtures, never course content.
- Right-to-left, time zones, per-region variants other than the Flemish one above.

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §3.1 the student's teacher's language | Widened once more: Flemish students are served in their teachers' language. The first users remain French-speaking Belgian students; Dutch is the other community of the same school system. |
| §5.1 it teaches the student's course; §5.2, §8 nothing invented | Dutch authoring restructures the Dutch material and never translates or adds (R4). |
| §5.3 withholds answers; §5.4 mechanical verdicts | The tool rules recognise Dutch notation and vocabulary, so the same checker and the same leak rules hold in Dutch (R6, R9). |
| §6.8 the interface | Dutch joins French and English at the user's choice (R1). |
| §9 trust: answer-leak rate below 1 %, no formula outside the pack | Reported per course language, Dutch included (R9.3). |

Deviations from the brief, `CLAUDE.md` and the documentation:

1. `specs/product.md` line 17 (« first users are French-speaking Belgian … French or English ») and the `CLAUDE.md` bullets for spec 010, spec 011 and the notation invariant (« French courses are FWB … English courses use the international convention ») gain Dutch: Dutch courses use Flemish notation (R7.1).
2. Documentation that says « French or English » (`i18n.md`, `course-language.md`, `README.md`, `specs/index.md` lines for 010 and 011 stay as history) is updated (R10).

## 3. Requirements

### R1 — Dutch as an interface language

**As a** Flemish user, **I want** the application in Dutch, **so that** I can use it in my own language.

Acceptance criteria:

1. `nl` is a `Locale` on both sides (`app/domain/locale.py`, `src/lib/locale.ts`, `project.inlang/settings.json`). French stays the base locale and the default.
2. A backend catalog (`app/domain/messages/nl.py`) and a frontend catalog (`messages/nl.json`) hold every key the French ones hold, with the same `{variables}` and plural forms; `test_messages.py`, `npm run i18n:check` and the catalog parity tests fail on a missing or extra key, as for English. Plurals use the inlang selector form with Dutch's one/other rule.
3. `Accept-Language` resolution (spec 010 R2.1) picks `nl` for `nl`, `nl-BE`, `nl-NL`, by quality order then position, on both sides, pinned by the shared `accept_language_cases.json` (both copies gain `nl` cases, including `nl-BE;q=0.8,fr;q=0.9` → `fr`). A signed-out visitor whose browser prefers Dutch now sees Dutch; one whose browser lists no supported language still sees French.
4. The settings screen's language section lists « Français », « English » and « Nederlands », each by its own name, and marks the current one. Registration stores the language the visitor was seeing, as before. Existing accounts keep their language (no data change).
5. `<html lang="nl">` for a Dutch interface; the server-rendered sign-in and registration pages come out Dutch on the first response; `Vary: Accept-Language` and `Cache-Control` behaviour unchanged.
6. `PATCH /api/auth/me` accepts `nl` and still answers `422` for an unsupported value, with a message in the request's language.
7. Every error, status, marker label, content-issue reason and subject label the server writes for the student exists in Dutch (`TutorError.message("nl")`, `render_issue`, `event_of`, `marker_for`).
8. Interface numbers and sizes (`lib/i18n-format.ts`) use `nl-BE`.
9. The product name « Célestin » stays untranslated (`APP_NAME`).
10. The Dutch copy is written by us, in the register of the French and English copy (clear, friendly, `je`/`jij`, no *tussentaal*), and is **reviewed by a Flemish speaker** before the spec is marked Implemented; until then its status says « Dutch copy awaiting review ».

### R2 — A Dutch course is taught in Dutch

**As a** student of a Dutch course, **I want** Célestin to speak, write on the board and read my work in Dutch, whatever my interface language is, **so that** nothing French or English comes between me and my teacher's material.

Acceptance criteria:

1. `nl` is a `CourseLanguage` on both sides. `POST /api/courses` accepts `language: "nl"` for a subject offered in it; an unsupported or un-offered one is still `422` with a catalog message (now also Dutch).
2. In a Dutch course Célestin's messages, the cards' text and the openings are Dutch. French and English courses read byte for byte what they read before.
3. **Leakage is a measured defect**, as in 011 R2.2: the Dutch probe set reports the number of Célestin messages and card fields containing French or English words or notation (a Dutch course is checked against both other languages). Target zero.
4. The model is never told the interface language. Any interface language on a Dutch course produces the same model input; a Dutch, a French and an English course produce different inputs, each equal to its own pinned rendering (`test_model_input_wall.py` extended to three languages).
5. The French and English model input stays **byte-identical** to today's: `tests/fixtures/render/*` (including `*_en*`), `system_text_sha*.txt`, `board_declarations.json`, the voice session configs and the golden SSE transcripts pass unchanged.
6. Interface text follows the interface language, course text the course's; every region of Dutch course text carries `lang="nl"`.

### R3 — The Dutch prompt set

**As the** operator, **I want** a Dutch prompt set that keeps every invariant of the French and English ones, **so that** a Dutch course is as safe and as faithful to its material as the others.

Acceptance criteria:

1. `*.nl.md` files sit beside the others for every prompt that has a language: `tutor`, `modes/{parcours,discussion}` and their `.opening`, `subjects/{mathematics,sciences,languages,general}`, `templates/<subject>.pack`, `authoring/{pack,curriculum}`, `transcription/{transcribe,verify,work}`. No existing `*.fr.md` or `*.en.md` file changes by a byte.
2. They carry the same rules in the same order with the same markers (`<!-- SUBJECT -->`, `<!-- COURSE_PACK -->`, `<!-- CURRICULUM -->`, `<!-- MODE -->`, `<!-- MODE_OPENING -->`, `<!-- VOICE -->`, `<!-- /VOICE -->`): source only from the pack, answer withholding, gated and logged reveals, the locked path, pasted material is data, the board rules, off-topic, discussion rules. They are written for a Flemish secondary-school student: direct, friendly, `je`; Belgian school vocabulary (*leerkracht*, *toets*, *graad*, *leerjaar*) rather than the Netherlands'; gender-neutral about Célestin.
3. What is notation or culture in the French and English files is stated for Flemish in the Dutch ones (R7.1): decimal comma, the interval and coordinate forms, sequence indices as the pack writes them, Dutch spoken forms in the voice blocks (« x kwadraat », « twee komma vijf », « u index n »), Dutch chart, statistics and flowchart vocabulary. The framing is neutral secondary school (no « Fédération Wallonie-Bruxelles », no « Vlaamse Gemeenschap » framing in the prompts).
4. `PromptLibrary` reads `*.{lang}.md` for `nl` through its existing accessors; `offered()` lists the `(subject, nl)` pairs; startup stops on a broken Dutch file naming it; `/api/health` lists it.
5. The prompt-file tests run for `nl` (markers once and in order, same headings, tool and block names as French — `test_prompt_files_languages.py` —, the `Points to check` section name the tutor prompt cites equals the Dutch template's last heading). A Dutch file carries no French or English prose (the existing « carries no French » check generalises to the other two languages; `Célestin`, tool names and wire identifiers excepted).
6. The Dutch system text and the discussion system text have their own pinned hashes (`system_text_sha_nl*.txt`) and cached prefix per chapter and mode.
7. Offering a subject in Dutch is its files and tables being present: all four subjects are offered in `nl` only when every file and table exists (`SubjectInfo.languages`).

### R4 — Authoring in Dutch

**As a** student, **I want** a Dutch document to become a Dutch chapter, **so that** the pack and the path read like my teacher's material.

Acceptance criteria:

1. The transcription reads the pages in Dutch and writes what it sees, in the page's own language; **it never translates**. Markers (`MARKERS` table) in Dutch: `[handgeschreven]`, `[onzeker: a | b]`, `[onleesbaar]`, `[lege pagina]`, `[figuur: …]`, `[doorgestreept: …]` (exact names fixed by the design). `--- page N ---` unchanged. `count_markers`, `handwritten_numbers`, `apply_uncertain`, `validate_batch` work on them; French and English sources keep validating.
2. The pack and curriculum prompts write Dutch from Dutch material and add nothing the material does not hold (brief §5.2).
3. Dutch pack templates for the four subjects have the same numbered structure, required-section positions and sentinels as the French (« Geen. », « Niets in de cursus. », « niet verbeterd in de cursus » or equivalents fixed by the design). `index_pack` compares headings to the template of the course's language; a pack in another language's template than the course's fails with `pack.wrong_language` in all three directions that involve `nl`.
4. `chapter_title` and the curriculum title cleaning strip Dutch chapter-numbering words (`Hoofdstuk 3:`, `Les 2 –`, `Thema 4)`, `Deel`, `Module`, with abbreviations and Roman numerals); other languages unchanged.
5. `AGENT_WORDS`, the repair prompts and `issue_text(issue, "nl")` are Dutch; the student's editor still shows the reason in the **interface** language.
6. `authoring_eval` and `document_eval` take `--language nl` and run on a Dutch document per subject; the runs are read against the French ones.

### R5 — Text built for the model follows the course language

**As the** operator, **I want** what the code builds every turn to be Dutch in a Dutch course, **so that** the model is not surrounded by another language.

Acceptance criteria:

1. `curriculum_render` (overview, brief, completion, state, discussion state, opening hints) renders in Dutch, with Dutch weekday and month names and time-of-day wording, in the deployment's time zone. French and English renderings are byte-identical; Dutch goldens (`tests/fixtures/render/*_nl.txt`) are added, read by a person, then pinned.
2. `KIND_LABELS`, the path refusals (`services/path.py`), `SAVE_FAILED`, `_UNKNOWN`, `_OUTPUT`, registry parse errors, section and pace text have a Dutch row. Wire values (`teach`, `practise`, `synthesis`) do not change. These tables do not import the interface catalog.
3. `CHARS_PER_TOKEN` has a Dutch row (compound words tokenise longer than English; measured or justified in the design) so Dutch history is not over-trimmed.
4. **Tool declarations and rule refusals** stay as for English (011 R5.4): the declarations are the same for the three languages and the refusals stay French until Dutch probe evidence shows leakage; the design keeps the `TOOL_TEXT` overlay switch and says what evidence flips it. The outcome required: no French in a Dutch course's speech or cards.
5. Every `by_language(...)` table in `app/` has a Dutch row; adding `nl` makes each one fail at import until it has it (`test_by_language_tables.py` passes with three languages).

### R6 — The tool rules recognise Flemish notation and vocabulary

**As the** operator, **I want** the board tools to accept and refuse the right things in Dutch, **so that** answer-withholding and no-invention rules work in Dutch as they do in French and English.

Acceptance criteria:

1. `plots.py`: `PACK_WORDS` has a Dutch table so that the Dutch names of the sine, cosine, tangent of an angle, natural logarithm, common logarithm, cube root and exponential function count as the pack naming the function. One accepted and one refused sentence per entry. `COMMA` and `GROUPS` have Dutch rows (decimal comma; `(1,4)` is read as Flemish writes it, per R7.1).
2. `flowcharts.py`: `HOLE_WORDS` has a Dutch set (« aan te vullen », « invullen », « ontbreekt », « leeg », « nog te bepalen », « stap », « vak », and the like) so the `placeholder` rule is not silently off.
3. `figures.py`: `INTERVAL`, `COORDS`, `DEGREES`, `LENGTH` and `_number` recognise Flemish hand-written notation: `]a ; b[` and `]a, b[`, `[a, b]`, `]−∞, 2]`, coordinates with either separator, decimal comma, and the grouping convention of R7.1. `1,5` is 1.5; `1.500` is read according to the convention the design fixes; the existing French and English cases are untouched.
4. The shared case tables (`notation_cases.json`, `layer_cases.json`, `capacity.json`, `expression_cases.json`) gain Dutch cases in both copies, formatted with prettier. `domain/expression.py` keeps accepting only a decimal point.
5. Rules read the language from `ctx.language`; French and English rule tests pass without edit.
6. `test_language_is_passed.py` passes: no call site in the application forgets the language.

### R7 — The board draws in Flemish notation

**As a** Flemish student, **I want** numbers, intervals and statistical words on the board written the way my teacher writes them, **so that** I never translate the board.

Acceptance criteria:

1. **Flemish notation** (the design confirms each item against Flemish textbooks and the user's material; items marked ? are open, §5): decimal comma; percentage `12,5 %` (? space before `%`); intervals in the outward-bracket form `]a ; b[`, `[a ; b[`, `]a ; b]`, `[a ; b]`, `]−∞ ; 2]` (? `;` or `,` as separator); points `(2 ; −1,5)` (?); thousands grouping chosen so that it cannot be read as a decimal point (?). Where a course's material writes otherwise, Célestin follows the material in his text and the board's formatter stays on the convention (the boundary 011 states for French and English).
2. `charts/format.ts` gains a `DUTCH` notation selected by `notationFor("nl")` and read by `useNotation()`; all callers already take it from there. The words the board adds are Dutch (« Frequentie / Relatieve frequentie / Percentage », « Minimum / Q1 / Mediaan / Q3 / Maximum », fixed by the design); wire identifiers (`measure: "effectif" | "frequence" | "pourcentage"`) do not change.
3. Accessibility descriptions of the drawing blocks keep the interface language for the sentences and take the course's notation for the numbers inside.
4. `lib/tutor/prompts.ts`: the sentences the interface sends to the model for the learner (review, start, next step, next section, answer, voice-tool failure) exist in Dutch, never from the interface catalog; French and English byte for byte.
5. The transcription marks the source editor names, the course language badge (« Nederlands » by its autonym), the create-course form's language select and its note, and `CourseLanguageProvider` all handle `nl`; no component names a language except the tables.
6. Tests: formatter tables (French and English cases unchanged, Dutch added to the shared `notation_cases.json`), learner sentences, and the sweeps: a Dutch interface on French and English courses, French and English interfaces on a Dutch course, with no sentence in the wrong language for its kind. The English sweep generalises to a language sweep: every screen rendered in each interface language fails on words of the other two outside a region marked with a different `lang`.

### R8 — Voice in Dutch

**As a** student, **I want** to talk to Célestin in Dutch, **so that** the spoken lesson matches the written one.

Acceptance criteria:

1. The Realtime session's input transcription language hint is `nl` for a Dutch course (a bias, not a constraint); the instructions come from the Dutch prompt files with the Dutch spoken-maths forms.
2. French and English session configs are byte-identical; a Dutch case is added to `test_voice_service.py`.
3. `voice_smoke` and `voice_probe` take `--language nl`; the probe reads the Dutch spoken forms as it reads the others.
4. The admin provider test's voice check names the languages it was run for if it names any (design decides); a provider that cannot hold Dutch speech is reported by the existing live checks, not assumed.

### R9 — Measuring it

**As the** operator, **I want** Dutch held to the standard of French and English, **so that** « it works in Dutch » is evidence.

Acceptance criteria:

1. Dutch fixtures per offered subject: material, valid pack, curriculum, chapter directory, written to the Dutch templates (`tests/fixtures/{material,packs,curricula,chapters}`), so the whole path is testable offline with the scripted fakes.
2. `scripts/probe.py --language nl` runs the guardrail and drawing probes (charts, flowcharts, figures, plots) on the Dutch chapters. Its Dutch flags: a decimal point where the convention is the comma, wrong interval or coordinate notation, French or English words (leakage), answer leaks, formulas outside the pack, an injection attempt in Dutch.
3. The report states, per course language, the answer-leak rate (target below 1 %), formulas or methods outside the pack (target zero) and the leakage count (target zero).
4. `smoke`, `seed`, `authoring_eval`, `document_eval`, `voice_smoke`, `voice_probe` take `--language nl`; `smoke` fails on a cache miss in Dutch; each (language, mode) has its own prefix.
5. `evals/` (the model comparison harness) accepts `nl` wherever it accepts a course language and runs the Dutch chapters; it still reads `backend/` and changes nothing in it.
6. Tests that pin French or English text keep their text; tests that become per-language are parametrised over `COURSE_LANGUAGES`, not copied. New goldens are produced once, read by a person, then pinned.
7. Probe transcripts are read by a person (a Flemish speaker for the Dutch ones) before the epic is closed; findings are recorded in the spec.

### R10 — Documentation

**As a** maintainer, **I want** the documentation to say three languages, **so that** it is true.

Acceptance criteria:

1. `documentation/i18n.md`, `documentation/course-language.md`, `README.md`, `documentation/index.md` (if a file is added), `CLAUDE.md`, `specs/product.md` and `specs/index.md` updated per §2. `course-language.md`'s « Adding things → A language » is checked against what this epic actually needed and corrected where the claim « files and tables » did not hold.
2. The Known limits record: Flemish conventions only (no `nl-NL`), refusals French, Dutch copy and prompts written by us.

## 4. Non-functional requirements

### 4.1 Architecture

1. **No component names a language.** `nl` appears in `Locale`/`CourseLanguage`, the catalogs, `by_language` tables, prompt files, formatter table, autonym list, fixtures and goldens. Any other place the implementation must touch is listed in the design as a defect of the structure and fixed so the next language does not need it.
2. **No fallback.** A language missing a model-facing resource is not offered; no Dutch path falls back to French or English.
3. **The wall holds.** Model-facing modules take the course language, never the interface `locale` nor the catalog.
4. **Wire identifiers do not change**: tool names, enums, section and card kinds, rule codes, `measure` values, the SSE contract. The frontend types change only by gaining `"nl"`.
5. **No migration expected.** `users.locale` and `courses.language` are strings without database enums (specs 010, 011); the design verifies it, and any constraint found is dropped by a migration with a working `downgrade`.
6. **French and English do not move.** Edits to existing tests are limited to the argument a signature gains and to parametrising over `COURSE_LANGUAGES`; no French or English golden is regenerated.

### 4.2 Performance and cost

1. Cached prefix per chapter and mode unchanged in size and behaviour; a chapter has one language. Prefixes grow only across courses.
2. Tables and regexes are built once at import; Paraglide ships all three catalogs in one build, and the bundle growth is reported in the design.

### 4.3 Security and privacy

1. A language from a request is validated against the supported list before use and never interpolated into a path.
2. Pasted material is data in Dutch too; the Dutch prompts carry the instruction and the probes include an injection attempt in Dutch.
3. Nothing new is logged about a student; `course_created` already carries the language.
4. Ownership checks unchanged.

### 4.4 Reliability and quality

1. A missing or broken Dutch file stops startup naming it; `/api/health` reports it while running.
2. Offline tests drive everything with scripted fakes: catalog parity, `Accept-Language` cases, `CreateCourseRequest` with `nl`, per-language `PromptLibrary`, the Dutch authoring path from material to valid pack and curriculum, marker sets, `index_pack` with mismatched templates, render goldens, rule tables, formatters, learner sentences, voice config, the wall test, the table-coverage test.
3. Real-model checks are the probes of R9; none runs under `pytest`.
4. A regression in French or English is loud (existing goldens); one in Dutch is caught by the Dutch goldens, rule tests and probes.

### 4.5 Usability

1. A student tells a Dutch course from the others at a glance (badge with autonym).
2. A user is never shown a sentence in the wrong language for its kind (interface text in the interface language, course text in the course's).
3. At 400 px wide, with Dutch (long compound words) everywhere: no overflow or truncated control. Long words wrap or hyphenate (`lang="nl"` enables hyphenation).

## 5. Open questions for the design (and the user)

1. **Flemish notation (R7.1), to confirm against the user's material before the prompts are written.** Intervals `]a ; b[` against `]a, b[`; point separator `;` against `,`; space before `%`; thousands as a space, a dot, or none under five digits (the dot is the decimal point the expression grammar reads, so a dot grouping is ambiguous); sequences indexed from `u₁` or `u₀`. The searches made for this spec found no authoritative source for Flemish textbooks; the Belgian-French convention is the working assumption.
2. **Is `nl` enough?** One code for Flemish; a Netherlands student gets Flemish notation. If `nl-NL` matters, the structure should allow a variant (a language key such as `nl-NL` against `nl-BE`) before the tables are written.
3. **Unlisted Flemish subject vocabulary.** *Wiskunde* terms differ between curricula (GO!, katholiek onderwijs, OVSG); the pack restricts the vocabulary to the student's material, and the subject prompts should not impose one.
4. **Tool declarations and refusals** (R5.4): evidence-driven, as for English.
5. **Dutch compound words and the model-facing tokenization** (`CHARS_PER_TOKEN`): measured or estimated.
6. **Who reviews the Dutch copy and prompts** (R1.10, R9.7) and when; the status line of the spec depends on it.
7. **Shared sweep.** Generalise the English sweep to a language sweep (R7.6) or add a Dutch one beside it.
