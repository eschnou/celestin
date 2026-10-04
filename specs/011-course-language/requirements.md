# 011 — Course language: an English tutor

## 1. Introduction

Spec 010 made the application's own text French or English. Everything else is still French: Célestin speaks French, the pack and curriculum are authored in French, the board draws French notation, and the prompts, the tool rules and the text built for the model assume a French-speaking Belgian student. This epic makes the **course language** a property of the course, `fr` or `en`, and teaches an English course in English from the first upload to the last board card.

A course gets its language when it is created and keeps it, like its subject. It is the language of the student's material, of the pack and the curriculum the authoring agent builds from it, of Célestin's speech (text and voice), and of the notation the board draws. It is a different thing from the interface language of spec 010: a French interface can open an English course and the reverse, and the model is never told which interface language the student chose.

Vocabulary:

- **Course language** (`courses.language`) — `fr` or `en`. Fixed at creation. Existing courses are `fr`.
- **Interface language** — spec 010's `users.locale`. Independent of the course language; never reaches the model.
- **Model-facing text** — anything the model reads: prompts, tool declarations, tool results, the history, the text built from the curriculum and the progress, the authoring and transcription instructions.
- **Course text** — what belongs to the course: the material, its transcription, the pack, the curriculum, Célestin's messages, the cards' content, the notation the board draws.
- **Wire identifier** — a token in the tool protocol that is not shown as such (`measure: "effectif"`, section kinds, card kinds, rule codes).
- **Notation** — how numbers, intervals, coordinates, percentages and statistical words are written on the board.

Scope:

- `courses.language`, the create-course form and the API around it.
- An English prompt set (tutor, modes, subjects, voice blocks) beside the French one, which does not move.
- English authoring: transcription, pack template, authoring prompts, validation, repair.
- Model-facing text built in code (`curriculum_render`, path and tool text, date words), made language-aware.
- The tool rules that recognise vocabulary and notation, made language-aware.
- The board's notation and fixed words, the sentences the interface sends for the learner, and the voice session, following the course language.
- Probes, fixtures and goldens for English, with French pinned byte for byte.

Out of scope:

- A third language (the structure must make it a set of files and tables, not a project).
- Changing a course's language after creation, translating an existing course, or a course whose material mixes languages.
- Detecting the material's language. The language the student chose is the language the authoring agent assumes.
- The « Langues étrangères » subject (brief §6.2: Célestin speaks French and works in the language being learnt) and the other subjects not yet offered.
- Content we author ourselves (brief §11): the work here is prompts, templates, rules and fixtures, never course content offered to students.
- Per-session or per-turn language switching.
- Translating Célestin's past conversations.

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §3.1 French-speaking student; the tutor speaks their teacher's language | Generalised: the tutor speaks the language of the course the student brought. |
| §5.1 It teaches the student's course | The notation, vocabulary and methods stay restricted to the pack in English as in French; the pack is built from English material by an authoring agent that restructures and does not translate. |
| §5.2, §8 The content is the student's; no invented content | Authoring in English adds nothing and never translates the material (R4.1, R4.2). |
| §5.3 Withholds answers; §5.4 never grades from impression | The same invariants, with the same tools and the same checker, hold in English: the tool rules recognise English notation and vocabulary (R6), and a leak in English is measured like a French one (R9). |
| §8 Pasted material is data, not instructions | Unchanged; the English prompts carry the same rule. |
| §9 Trust: answer-leak rate below 1 %, no formula outside the pack | Reported per course language (R9.3). |
| §12 question 4 (material language) | Answered: the material is in the course's language, `fr` or `en`; any other language is out of scope. |

Deviations from the brief and from `CLAUDE.md`:

1. **§1, §3.1 and §6.7 say the student and the tutor are French-speaking.** They are widened to « the course's language ». `CLAUDE.md`'s invariant (« tutor speech is in French … the board's notation and everything sent to the model stay French whatever the interface language ») becomes: tutor speech, the board's notation and everything sent to the model follow the course's language; none follows the interface language.
2. **Spec 010 §4.7, « the wall ».** It forbids model-facing code from taking a `locale`. This epic keeps that rule for the interface language and adds a parameter named for the course language. `test_model_input_wall.py` is reworded accordingly (R2.6).
3. **§12 question 4** is closed by this epic.

## 3. Requirements

### R1 — A course has a language

**As a** student, **I want** to say in which language my course is written when I create it, **so that** Célestin teaches it in that language.

Acceptance criteria:

1. `courses.language` is `fr` or `en`, `NOT NULL`, default `fr` in a migration (`0007`) that leaves every existing course `fr`. The supported list is code (a `CourseLanguage` type next to `Locale`, not the same type); there is no database enum.
2. `POST /api/courses` takes `language`. A missing one means `fr` (existing clients and tests keep working); an unsupported one is refused with a `422` and a catalog message in both interface languages (like `invalid_subject`). The create form asks for it and says it cannot be changed afterwards, as it does for the subject.
3. The create form offers the languages the server lists (`GET /api/subjects` or a sibling answer), each by its own name, and starts on the interface language when that is a supported course language, else `fr`.
4. The language is immutable. `PATCH /api/courses/{id}` refuses a `language` field (`extra="forbid"` already does; a test pins it) and no route changes it. Deleting the course and creating another is the only way.
5. `CourseSummary`, `CourseDetail`, `ChapterView` and `ChapterContent` carry `language`, set from the course. `LessonChapter` and `CourseRecord` carry it into the model path.
6. A course in one language never meets a prompt, template, rule table or notation of the other: every place that takes the subject today takes the language too (R3 to R8), and a test fails if a code path reads a language-keyed resource without it.
7. Offering a subject in a language is its files and tables being present; a subject not yet written in English is not offered in English (both launch subjects, mathematics and physics, are).

### R2 — A course is taught in its own language

**As a** student of an English course, **I want** Célestin to speak, write on the board and read my work in English, whatever language my interface is in, **so that** nothing French comes between me and my teacher's material.

Acceptance criteria:

1. In an English course, Célestin's messages, the cards' text and the openings are English. In a French course nothing changes.
2. **Leakage is a measured defect.** The English probe set (R9) reports, per run, the number of Célestin messages and card fields containing a French word or French notation. The target is zero; one is a failure to read, not to ignore.
3. The model is never told the interface language. A French interface on an English course, and an English interface on a French course, produce the same model input as the interface that matches (extends the 010 test: the provider's input depends on the course language and on nothing else).
4. Mixed cases keep their boundaries: interface text (buttons, errors, statuses) follows the interface language; course text follows the course language; screen readers get the right `lang` for each (R7.6).
5. A French course's model input is **byte-identical** to today's: `tests/fixtures/render/system_text_sha*.txt`, the render goldens, `board_declarations.json`, the voice session config and the golden SSE transcripts pass unchanged.
6. `test_model_input_wall.py` is reworded: model-facing modules still may not import the interface message catalog or take the interface `locale`; they may take the course language. The behavioural half compares two accounts with different interface languages on the same course (identical input) and a French course against an English one (different input, each equal to its own pinned rendering).

### R3 — The prompt set, in English beside the French

**As the** operator, **I want** an English prompt set that keeps every invariant of the French one, **so that** an English course is as safe and as faithful to its material as a French one.

Acceptance criteria:

1. English files sit beside the French ones, named `*.en.md` (`tutor`, `modes/<mode>`, `modes/<mode>.opening`, `subjects/<subject>`, `templates/<subject>.pack`, `authoring/{pack,curriculum}`, `transcription/{transcribe,verify}`). No `*.fr.md` file changes by a byte.
2. The English files carry the same rules, in the same order, with the same markers (`<!-- SUBJECT -->`, `<!-- COURSE_PACK -->`, `<!-- CURRICULUM -->`, `<!-- MODE -->`, `<!-- MODE_OPENING -->`, `<!-- VOICE -->`): the source rule (only the pack), answer withholding, reveals gated and logged, the locked path, pasted material is data, the voice block, the board rules, off-topic and the discussion rules. They are written for an English-speaking secondary-school student: direct, friendly, second person; gender-neutral about Célestin.
3. What is notation or culture in the French files is stated for English in the English ones (R7.1): decimal point, `(a, b)` and `[a, b)` intervals, `(x, y)` coordinates, `x_1`-style indices as the material writes them, English spoken forms in the voice blocks (« x squared », « two point five », « u sub n »), English chart, statistics and flowchart vocabulary. The French « Fédération Wallonie-Bruxelles » framing becomes a neutral secondary-school one.
4. `PromptLibrary` takes the course language in every accessor, keys its caches by (name, language), and reads `*.{lang}.md`. `required()`, `_broken()`, `check()` and `unavailable()` enumerate the offered (subject, language) pairs; startup stops naming the first broken file, English included, and `/api/health` lists them with the language in the name. Callers pass the language they already have beside the subject (`TutorService`, `VoiceService`, `AuthoringAgent`, `routes/courses.py` content validation, scripts).
5. Tests that read the prompt files (`test_prompt_files`, `test_prompt_library`, `test_prompt_service`) run for each language: markers present once and in order, the subject prompt is subject-neutral where it must be, the `Points to check` section name the tutor prompt cites equals the English template's last heading, the French files' assertions are unchanged.
6. The English system text and the discussion system text have their own pinned hashes (`system_text_sha_en*.txt`) and their own cache prefix per chapter and mode, as French does. Nothing varies per turn in front of the cache breakpoint.

### R4 — Authoring in the course's language

**As a** student, **I want** an English document to become an English chapter, **so that** the pack and the path read like my teacher's material.

Acceptance criteria:

1. The transcription reads the pages in the course's language and writes what it sees, in the page's own language, with that language's markers. **It never translates.** The English transcription instructions say so, and the French ones are unchanged.
2. The pack and curriculum prompts of an English course write in English, from English material, and add nothing the material does not hold (brief §5.2). A document written in another language than the course's is the student's to correct; the instructions tell the model to keep the material's words and to flag what it cannot settle in « Points to check ».
3. The transcription markers are a set per language, used by `domain/transcription.py` (`count_markers`, `handwritten_numbers`, `apply_uncertain`, `validate_batch`) and named in the prompts: French `[manuscrit]`, `[incertain : a | b]`, `[illisible]`, `[page vide]`, `[figure : …]`, `[barré : …]` unchanged; English `[handwritten]`, `[uncertain: a | b]`, `[illegible]`, `[empty page]`, `[figure: …]`, `[crossed out: …]` (names for the design to fix). `--- page N ---` stays, language-free. A stored French source keeps validating.
4. English pack templates (mathematics, physics) have numbered headings of the same structure and the same required section positions as the French (`exercises_section`, the last section being the points to check), with English titles and English sentinels (« None. », « Nothing in the material. », « not corrected in the material »). `index_pack` compares a pack's headings to the template **of the course's language**. A French pack against an English template, and the reverse, fails with an issue that names the language mismatch.
5. `chapter_title` and the curriculum's title cleaning strip the course's own chapter-numbering words (`Chapter 3:`, `Lesson 2 –`, `Unit 4)`, with their abbreviations and Roman numerals); the French list is unchanged.
6. The reasons the authoring model reads to repair its output (`ContentIssue.message`, `_repair_message`, the wrappers around the material in `agent.py`, the page labels) are in the course's language. The student's editor still shows the reason in the **interface** language (spec 010 R5.6): one issue, two audiences, two languages. The `where` forms the editor parses (`section « id »`) do not change.
7. The runner and the agent carry the language beside the subject end to end (`AuthoringRunner._execute`, `AuthoringAgent.run`, the content-save validation in `routes/courses.py`). A run that fails keeps its code, and its message follows the interface language as today.
8. `authoring_eval` and `document_eval` take `--language`, and run on an English document per subject. The runs are read against the French ones: the same stages, the same limits, no invented content.

### R5 — Text built for the model follows the course language

**As the** operator, **I want** the text the code builds every turn to be in the course's language, **so that** an English course is not read by a model surrounded by French.

Acceptance criteria:

1. `curriculum_render` (the overview, `brief`, `completion`, `state_message`, the discussion state, the opening hints) renders in the course's language. `moment()` uses that language's weekday and month names and its time-of-day wording; the time zone stays the deployment's. The French renderings are byte-identical (`tests/fixtures/render/*.txt` untouched; English goldens added beside them).
2. `KIND_LABEL_FR` and the section-kind words in prompts are per language (« Lesson / Practice / Summary »); the wire values `teach`, `practise`, `synthesis` do not change.
3. The path refusals the model reads (`services/path.py`), `SAVE_FAILED`, the `propose_next_step` output, `_UNKNOWN` and the registry's argument-parse errors are in the course's language. They carry no student-facing role, so they are not in the interface catalog and do not import it.
4. **Tool declarations and rule refusals** (5 tool descriptions, 14 `Field(description=…)`, about 150 refusal messages): their language is a decision for the design, made on the probe evidence of R9.2. The requirement is the outcome: no French leaks into an English course's speech or cards, and every refusal the model needs to correct itself is understood. If the declarations stay French for English courses, the design says why and keeps a switch to localise them (an overlay on the schema, one extra snapshot, `registry.declarations(mode, language)` byte-stable per pair); the refusal messages themselves stay as they are in this epic (localising ~150 messages is a later change, made only on probe evidence).
5. `history.py`'s characters-per-token estimate does not over-trim English: it follows the language or is shown to be harmless.
6. The French declarations, tool outputs and refusals are unchanged: `board_declarations.json` and every French substring the tests pin pass untouched.

### R6 — The tool rules recognise the course's notation and vocabulary

**As the** operator, **I want** the board tools to refuse and accept the right things in English, **so that** the answer-withholding and no-invention rules work in English as they do in French.

Acceptance criteria:

1. `plots.py`: `PACK_WORDS` has an English table of the same shape, so that « sine », « cosine », « tangent of an angle », « natural logarithm », « common logarithm », « cube root » and « exponential function » count as the pack naming the function. A test per entry pins one accepted and one refused sentence, per language, like today.
2. `flowcharts.py`: the placeholder vocabulary (`_HOLE_HEAD`, `_HOLE_GAP`, `_HOLE_WORDS`) has an English set (« to complete », « fill in », « missing », « blank », « TBD », « step », « box », « node »), so the `placeholder` rule is not silently off.
3. `figures.py`: the hand-written notation checks recognise the course's separators and brackets: French `;`-separated groups and `]a ; b[` (unchanged), English `(2, 3)`, `[2, 5)`, `(−∞, 2]`. The number reader treats the comma as a thousands separator in English (« 1,500 m » is 1500) and as a decimal in French (unchanged). `plots.py`'s `_COMMA` heuristic is per language (`(1,4)` is a coordinate pair in English, `(0,5)` a decimal in French).
4. A rule that depends on how the board lays something out or parses it keeps one shared case table with the frontend (`layer_cases.json`, `capacity.json`, `expression_cases.json`). Where a table is language-free it stays one file; where English adds cases, both copies change together, formatted with prettier. `domain/expression.py` already accepts only a decimal point and stays as it is.
5. The rules' behaviour for a French course is unchanged: the existing rule tests pass without edit, and English adds its own cases beside them.
6. The tools receive the course language from the turn (`TurnContext` carries it beside the interface `locale`, which stays display-only) and from the card's course, never from the interface.

### R7 — The board draws in the course's notation

**As an** English-speaking student, **I want** numbers, intervals and statistical words on the board written the way my teacher writes them, **so that** I never have to translate the board.

Acceptance criteria:

1. The board's notation is chosen by the course language. French is today's, unchanged (decimal comma, `12,5 %`, `]a ; b[`, `(2 ; −1,5)`, `fr-BE` grouping). English is: decimal point, `12.5%`, `(a, b)` for an open interval, `[a, b)` and `(a, b]` for half-open, `[a, b]` closed, `(−∞, 2]` with the infinity signs, `(2, −1.5)` for a point, comma grouping for thousands. The English convention is the common international one; where a course's material writes otherwise, the model follows the material in its text and the board's own formatter stays on the convention (the design states this boundary, as it does for French today).
2. `charts/format.ts` takes the language: `formatNumber`, `formatValue`, `formatPair`, `formatInterval`, `formatBound`, and the figure, plot and chart code that call them. The words the board adds are per language: « Effectif / Fréquence / Pourcentage » and « Minimum / Q1 / Médiane / Q3 / Maximum » (unchanged) against « Frequency / Relative frequency / Percentage » and « Minimum / Q1 / Median / Q3 / Maximum ». The wire identifier `measure: "effectif" | "frequence" | "pourcentage"` does not change.
3. The accessibility descriptions of the four drawing blocks (spec 010 R3.2) keep the interface language for their sentences and take the course's notation for the numbers and intervals inside; a French interface on an English course reads English numbers in French sentences.
4. The sentences the interface sends to the model on the learner's behalf (`lib/tutor/prompts.ts`: review, start, next step, next section, answer, voice-tool failure) are per course language, never from the interface catalog: an English course sends English sentences, a French course the current ones byte for byte. They are echoed as learner turns, so they read in the course's language.
5. The fixed words of the board's own cards (card labels, « Next step », headings) stay interface text (spec 010); only the course's vocabulary and notation follow the course.
6. `COURSE_LANG` stops being a constant: every `lang` attribute on course text (tutor and learner messages, cards, chapter titles, pack, path, source, editor inputs) carries the course's language, from the chapter the page shows. The English sweep (spec 010 R3, task 10.3) treats a region marked with the course's language as course text whichever it is.
7. The create form, the course card and the course page show the course's language (name by its own name) so that a student can tell their English and French courses apart.
8. Tests: formatter tables per language (the French cases unchanged, English added), the learner sentences per language, and an English course under a French interface and a French course under an English interface in the sweep.

### R8 — Voice in the course's language

**As a** student, **I want** to talk to Célestin in my course's language, **so that** the spoken lesson matches the written one.

Acceptance criteria:

1. The Realtime session's input transcription language hint (`voice_service.py:71`, today `"fr"`) is the course language. It is a bias, not a constraint; the instructions say which language Célestin speaks.
2. The voice instructions come from the language's prompt files, with the spoken-maths forms of that language (R3.3). The French session config is byte-identical (`test_voice_service.py` unchanged for `fr`; an English case added).
3. The voice error and failure strings the interface sends or shows follow R7.4 (model-facing) and spec 010 (student-facing).
4. `voice_smoke` and `voice_probe` take `--language`; the probe reads the English spoken forms (`x squared`, `two point five`) as it reads the French ones.

### R9 — Measuring it: probes, fixtures, goldens

**As the** operator, **I want** English held to the standard French is held to, **so that** « it works in English » is evidence and not impression.

Acceptance criteria:

1. English fixtures exist for each offered subject: material, a valid pack, a curriculum, and a chapter directory (`tests/fixtures/{material,packs,curricula,chapters}`), written to follow the English templates. They make the English path testable offline, with the scripted fakes.
2. `scripts/probe.py` takes `--language` and runs the guardrail probes and the drawing probes (charts, flowcharts, figures, plots) on the English chapters. Its flags are per language: the French flags are unchanged; the English set flags a decimal comma, a `;`-separated interval, a French word (the leakage check, R2.2) and the answer-leak and pack-only checks of the brief.
3. The report states, per course language, the answer-leak rate (target below 1 % of tutor messages), the formulas or methods outside the pack (target zero) and the leakage count (target zero) (brief §9).
4. `smoke` takes `--language` and fails on a cache miss in English as in French; each (language, mode) has its own cached prefix, and one chapter has exactly one language.
5. `authoring_eval` and `document_eval` (R4.8), `seed` (a `--language` option and an English seed chapter for local tests) and `voice_smoke`/`voice_probe` (R8.4) take `--language`.
6. Tests that pin French text keep their French; tests that become per-language are parametrised, not copied. The new goldens (`system_text_sha_en*.txt`, English render goldens, an English declarations snapshot if R5.4 localises them) are produced once, reviewed by a person, and then pinned.
7. Probe transcripts are read by a person before the epic is closed, as for 007 to 009; their findings are recorded in the spec.

## 4. Non-functional requirements

### 4.1 Architecture

1. **The language rides with the subject.** It is a field of `CourseRecord` and `LessonChapter`, a parameter wherever the subject is one, and nowhere else: no module-level "current language", no global switch, no `contextvars`. A route reads it from the chapter it already loads.
2. **One resource per (subject, language) and nothing implicit.** Prompt files, templates, marker sets, notation tables, rule vocabularies and goldens are keyed by language. A language that lacks one of them is not offered; there is no fallback to French for model-facing text.
3. **A third language is files and tables.** `CourseLanguage`, the prompt tree, the marker and vocabulary tables, the formatter table and the goldens are the whole addition; no component, tool or route names a language except the tables.
4. **Interface text and model-facing text stay separate.** Model-facing text per language lives outside `app/domain/messages/` (the interface catalog), which the model path does not import (spec 010 §4.7). Where the same sentence is wanted in both (a content issue the model repairs and the student reads), it is data (code plus parameters) rendered by two functions.
5. **Wire identifiers do not change.** Tool names, enum values, section kinds, card kinds, rule codes and the SSE contract are untouched; the frontend types change only by adding `language`.
6. **Migration `0007`** follows the `NNNN_slug` convention with a working `downgrade`; the startup schema check and `tests/unit/test_migrations.py` keep passing.
7. **Existing code paths and tests for French are not edited** except to add the language argument they now pass; a test that must change for a reason other than that is called out in the design.
8. The shared case tables keep their convention (a copy on each side and a byte-equality test).

### 4.2 Performance and cost

1. The cached prefix per chapter and mode is unchanged in size and behaviour: a chapter has one language, so languages add prefixes only across courses (tutor × subject × mode × language). `smoke` reports both languages as CACHE OK.
2. Localised declarations, if the design chooses them (R5.4), are built once per (mode, language) and are byte-stable, like today's.
3. Formatters and rule tables are looked up by language without per-call construction (compiled regexes at import).

### 4.3 Security and privacy

1. A language from a request body is validated against the supported list before use and never interpolated into a path: prompt file names are built from the supported list only.
2. Pasted material is data in every language; the English prompts carry the same instruction, and the probe set includes an injection attempt in English.
3. Nothing new is logged about a student; `course_created` gains the language (a course attribute, not personal).
4. The language is a course attribute checked through the same ownership queries as the course; no route exposes another student's.

### 4.4 Reliability and quality

1. A missing or broken English file stops startup naming it, like a French one, when English is offered; `/api/health` reports it while running.
2. Offline tests drive everything with the scripted fakes: the migration; `CreateCourseRequest` with and without a language; the immutability of the language; per-language `PromptLibrary`; the English authoring path from material to a valid pack and curriculum (fake completions); the marker sets; `index_pack` with a mismatched template; `curriculum_render` goldens; the rule tables; the formatters; the learner sentences; the voice session config; the wall test.
3. The real-model checks are the probes of R9; none runs as part of `pytest`.
4. A regression in French is loud: the existing goldens and substrings fail. A regression in English is caught by the English goldens, the rule tests and the probes.

### 4.5 Usability

1. The create form says what the language is for in one sentence (« the language your course is written in; Célestin will teach in it ») and that it cannot be changed.
2. A student can tell an English course from a French one at a glance (R7.7).
3. An English-speaking student with a French interface (or the reverse) is never shown a sentence in the wrong language for its kind: interface text in the interface language, course text in the course's.

## 5. Open questions for the design

1. **Which English notation.** R7.1 fixes the common international convention (decimal point, `(a, b)` intervals, comma grouping). If the target is one curriculum (UK GCSE/A-level, US Common Core, IB) with other habits (`]a, b[`, `x₁` against `x_1`, « solution set » against « solution »), the user says so before the English subject prompts are written.
2. **Tool declarations and refusals** (R5.4): localise from the start, localise only on probe evidence, or never. The survey found six English docstrings already in the French prefix without visible leakage, which argues for « on evidence ».
3. **Marker names** (R4.3) and whether English keeps French marker tokens as a protocol: the requirement localises them because the student reads and edits the source.
4. **Where the language mismatch of a pack and a template is caught** (R4.4): `index_pack` only, or a cheap check on the material.
5. **`ContentIssue` for the repair prompt** (R4.6): a function of (code, params, language) in the model path, against reusing the interface catalog's English text, which the wall forbids the model path to import.
6. **Offered languages**: served by `/api/subjects` or a constant on both sides; and the create form's default.
7. **Prompt layout**: sibling `*.en.md` files (this spec's assumption: French does not move) against a directory per language.
8. **`measure` wire identifiers** shown to the model in an English course (R7.2): identifiers only, or an English alias in the declarations if the probes show confusion.
9. **Time**: whether an English course keeps the deployment's time zone (assumed) and 24-hour wording.
10. **How the frontend learns the course language** where a component has only a chapter or only a course (R7.6): one context fed by the route, or a prop.
