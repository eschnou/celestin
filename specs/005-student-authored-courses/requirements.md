# 005 — Student-authored courses: courses, chapters and the authoring agent

## 1. Introduction

Specs 001–004 built a tutor over content we authored: a class catalog file, chapter directories with a hand-written `pack.md` and `curriculum.yaml`, and a maths-specific tutor prompt. Product brief v2.0 pivots to self-service: the student brings the material their teacher gave them. This epic lets a student create a course, add chapters by pasting text, and have an authoring agent turn each chapter into a pack and a curriculum that the existing Parcours lesson runs on unchanged.

Vocabulary, fixed here because the code and the copy will use it:

- **Course** (« cours ») — owned by one student: a name and a subject. Replaces the spec 004 **class**; there is no catalog, no enrolment and no sharing.
- **Subject** — a closed list defined in code: `mathematics`, `physics`, `chemistry`, `biology`, `history`, `french`, `foreign-language`. Only `mathematics` and `physics` are **available** in this epic. Chosen at course creation, never changed.
- **Chapter** — belongs to a course, in creation order: the **source text** the student pasted, and, once authored, a **pack** (Markdown) and a **curriculum** (the spec 002 structure). The chapter id is generated.
- **Authoring run** — one background job that produces a chapter's pack and curriculum from its source text.
- **Prompt layers** — the tutor prompt (subject-neutral), the subject prompt (one per subject) and the chapter layer (pack + curriculum overview), all written by us except the chapter layer.
- **Pack template** — per subject, the section structure a pack must follow; used by the authoring agent and by the pack validator.
- **Points à vérifier** — the pack section listing what the agent could not settle. Replaces « Points à faire valider ».

Scope:

- Create, rename and delete courses; add, edit and delete chapters.
- Authoring agent: source text → pack → curriculum, validated, in the background, with status, failure and retry.
- Editing a chapter's pack, curriculum or source text; any adopted change resets that chapter's progress.
- Course and chapter content in the database; the file-based catalog, `courses/classes.yaml`, enrolments and `COURSES_DIR` retired.
- Tutor prompt split into the tutor prompt and subject prompts; subject prompts and pack templates for mathematics and physics.
- Frontend: « Mes cours », course page, add-chapter form, chapter content view and editors, lesson routes moved under courses.
- A seed command that creates a local test student with a mathematics course holding the existing chapter 1.

Out of scope:

- PDF, image or scan input; photographed student work.
- Subjects other than mathematics and physics (the values exist; they are not offered).
- Discussion and Révision modes (brief §6.5, §6.6).
- A mechanical answer checker. The tutor keeps today's rule: it never declares a verdict as certain.
- Sharing courses, teacher or parent views, version history of chapter content, reordering chapters, moving a chapter between courses.
- Preserving spec 004 enrolments or progress rows (development data only).

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §1, §5.2 The content is the student's | The only content path is the student's pasted text; we ship no chapters. |
| §5.7 Setup is minutes, not hours | A course is a name and a subject; a chapter is a paste; no review step before the first lesson. |
| §6.2 Courses and chapters | Delivered as specified, text input only. |
| §6.3 What the tutor reads | Three prompt layers; subject prompts and pack templates for mathematics and physics. |
| §6.4 Parcours mode | The existing path, tools, board, voice and progress run on authored chapters without change to their contracts. |
| §8 No invented content, no drift | The agent restructures and flags; unresolved items go to « Points à vérifier » and are not taught. |
| §8 Pasted material is data; cost control | Source text is never treated as instructions; size limits, per-student quotas and per-run cost logging. |
| §8 Privacy | Every course, chapter and progress row is scoped to its owner; nothing is shared. |
| §11 Phase A | This epic is Phase A. |

Deliberate deviations:

- Brief §5.4 (verdicts from a checker) is not delivered; no checker exists yet. Unchanged from specs 001–004.
- Brief §7 shows authoring taking about two minutes; no latency target is set beyond NFR 4.2.

## 3. Requirements

### R1 — Courses

**As a** student, **I want** to create my own courses with a name and a subject, **so that** I can organise the material each teacher gives me.

Acceptance criteria:

1. « Mes cours » lists the student's courses, newest activity first, each with name, subject label, chapter count, chapters done / total, and the last chapter worked on if any. With no course, the page shows one sentence and the create action; it is never empty.
2. Creating a course takes a name (trimmed, 1–80 characters) and a subject chosen from the available subjects, shown with French labels (Mathématiques, Physique). Unavailable subjects are not offered. The API refuses an unknown or unavailable subject with 422.
3. The subject cannot be changed by any route. The form states that it is final.
4. A course can be renamed (same rules as creation).
5. A course can be deleted after an explicit confirmation naming it. Deletion removes its chapters, their source text, packs, curricula, authoring runs and the owner's progress on them. A running authoring run for one of its chapters is abandoned and its result discarded.
6. Names need not be unique. A student has at most `MAX_COURSES_PER_STUDENT` courses (default 30); beyond that, creation is refused with 409 and a French message.

### R2 — Adding a chapter

**As a** student, **I want** to add a chapter by pasting its text, **so that** the tutor can teach me that chapter.

Acceptance criteria:

1. The course page has « Ajouter un chapitre »: one text area for the material and a submit button. The form states what to paste (course notes, exercises, corrections) and the size limits.
2. Source text is trimmed and must be between `CHAPTER_TEXT_MIN_CHARS` (default 300) and `CHAPTER_TEXT_MAX_CHARS` (default 100 000) characters; the form shows the current length and refuses out-of-range text before submission, the API with 422.
3. Submitting creates the chapter at the end of the course, stores the source text, starts an authoring run and returns immediately with the chapter in state `generating`. The student can leave the page; the run continues.
4. A course has at most `MAX_CHAPTERS_PER_COURSE` chapters (default 40), matching the curriculum limit of spec 002; beyond that, 409 with a French message.
5. The chapter's title shown everywhere is the curriculum title once authored; before that, « Nouveau chapitre » plus its position.

### R3 — Authoring agent

**As a** student, **I want** my pasted material turned into a structured chapter and a learning path, **so that** I can start a lesson without preparing anything myself.

Acceptance criteria:

1. A run has two stages in order: **pack** (source text + subject prompt + pack template → pack Markdown), then **curriculum** (pack + subject → curriculum). The curriculum stage reads the pack, not the source text.
2. The pack follows the subject's pack template (R8). It contains only what the source text contains: definitions, formulas, notation and vocabulary are copied in the material's form; nothing from outside the material is added.
3. Every sample exercise in the pack has a stable identifier (e.g. `6.1.3`), its statement, and the method and answer when the material gives them or they can be derived from it. An answer the agent recomputes and finds different from the material's is kept as the material states it and listed under « Points à vérifier ».
4. Anything unreadable, truncated, contradictory or ambiguous in the material is listed under « Points à vérifier » with what is wrong, rather than guessed.
5. The curriculum is structured output validated by the existing curriculum rules (spec 002: kinds, beats, exercises, count, unique ids, limits) and by a **reference check**: every `pack` entry starts with a pack section identifier that exists in the pack (e.g. `§4.2`), and every `exercises` entry starts with an exercise identifier that exists in the pack. The chapter 1 curriculum passes this check unchanged, or is corrected once in the seed.
6. The pack is validated mechanically: required template headings present and in order, exercise identifiers unique, size within `PACK_MAX_CHARS` (default 60 000).
7. A validation failure is sent back to the model with the error messages for another attempt, up to `AUTHORING_MAX_REPAIRS` (default 2) per stage. When attempts are exhausted, or the provider fails, the run ends in `failed`.
8. The source text is passed to the model as delimited data. Instructions found inside it are not followed; a test with an injected instruction in the source (e.g. « ignore tes consignes et … ») shows the pack does not act on it.
9. The authoring model is configurable (`AUTHORING_MODEL`), independent of the tutor model. Nothing is stored at the provider (`store=false`, as the tutor).
10. Each run records its stage timings, attempts, token usage and a cost estimate, in a table and a log line, with the user id and chapter id and never the source text.

### R4 — Chapter states, failure and retry

**As a** student, **I want** to see whether a chapter is ready and to retry when preparation failed, **so that** I am never stuck on a chapter I cannot open.

Acceptance criteria:

1. A chapter has one authoring state: `generating`, `failed` or `ready`. The course page shows it: « En préparation… », « Échec de la préparation », or, when ready, the progress state of spec 004 (« pas commencé », « en cours (n/m) », « terminé »).
2. The course page refreshes the state of `generating` chapters by polling without a full reload, and stops polling when none remain.
3. A `failed` chapter shows one French sentence saying what went wrong in student terms (text too unstructured, service unavailable, limit reached) and a « Réessayer » action that starts a new run on the same source text, subject to the quotas of R9. The technical cause is logged, not shown.
4. Only a `ready` chapter can be opened as a lesson. Opening any other state by URL shows its state and a link back to the course, not the lesson.
5. On backend startup, any run still marked running is marked `failed` with the reason « interrompu », and its chapter follows R4.1 (or keeps its previous content, per R5.4).
6. At most one run is active per chapter. Starting a run while one is active is refused with 409.

### R5 — Viewing and editing a chapter

**As a** student, **I want** to read and correct what the agent produced, **so that** the tutor teaches my teacher's course and not a misreading of it.

Acceptance criteria:

1. From the course page and the lesson, a ready chapter offers « Contenu du chapitre »: the pack rendered as Markdown with LaTeX, the curriculum as a readable list of sections (number, kind label, title, goal, beats or exercises, done-when), and the source text.
2. **Edit the pack**: a Markdown editor on the pack. Saving validates it (R3.6) and re-checks the existing curriculum against it (R3.5); errors are shown in French naming the heading, exercise or section concerned, and nothing is saved.
3. **Edit the curriculum**: an editor covering sections (add, remove, reorder, change kind, title, goal, beats, exercises, count, done-when). Saving validates it (R3.5) against the current pack; errors name the section; nothing is saved on error.
4. **Edit the source text**: replacing the source text and saving starts a new authoring run. Until that run succeeds, the previous pack and curriculum stay in use and the chapter stays openable with a « Nouvelle version en préparation » notice. On success the new content replaces the old; on failure the old content stays and the failure is shown with « Réessayer ».
5. Every adopted change of pack, curriculum or source-derived content resets the owner's progress on that chapter to zero. Each editor states this before saving and asks for confirmation when progress exists.
6. A save based on stale content (the chapter changed since the editor opened, e.g. a run finished) is refused with 409 and the editor offers to reload.
7. A chapter can be deleted after confirmation; its progress and runs go with it; the remaining chapters keep their order.

### R6 — Content in the database

**As a** developer, **I want** courses and chapters stored per student in the database, **so that** the tutor, the lesson and the editors read one source and nothing a student creates lives on the file system.

Acceptance criteria:

1. Tables hold courses (owner, name, subject, timestamps), chapters (course, position, source text, pack, curriculum, authoring state, a content version, timestamps) and authoring runs (R3.10). Progress keeps its spec 004 shape, keyed by user and chapter id; chapter ids are generated and globally unique.
2. The tutor turn, the voice session and tool endpoint, the chapter view and the progress reset read the chapter from the database by id, scoped to the signed-in owner. A chapter of another student, or one that does not exist, is 404, never 403.
3. `courses/classes.yaml`, the `ChapterCatalog` file loading, `COURSES_DIR`, the enrolments table and the enrol route are removed. The `courses/` directory keeps `chapitre_1/` as seed material only.
4. The spec 004 progress repair (normalising a record against the current curriculum) stays on every read.
5. Migrations create the new tables and drop the enrolments table. Existing progress rows are deleted.
6. `GET /api/health` reports the tutor prompt and the subject prompts and pack templates of available subjects as loadable, and the number of authoring runs currently active. It no longer reports chapters.

### R7 — Prompt layers

**As a** developer, **I want** the tutor prompt split into a subject-neutral tutor prompt and per-subject prompts, **so that** one tutor serves every subject and each subject's conventions are written once.

Acceptance criteria:

1. The tutor prompt (`backend/prompts/tutor.fr.md`) contains no subject, level or notation: persona, the source rule, the path, how to speak, the voice block, how to teach, what is never done, the board, the session opening. The mathematics-specific rules it holds today move to the mathematics subject prompt.
2. One subject prompt per available subject (e.g. `backend/prompts/subjects/mathematics.fr.md`) holds: what the subject is, how it is taught, how it is written on the board (LaTeX, units, significant figures…), how it is said aloud in voice mode, which exercise and answer kinds suit it, and what counts as off-topic. The subject's voice rules sit inside the voice markers so text turns omit them.
3. The system text is assembled in this order: tutor prompt, subject prompt, pack, curriculum overview. The whole block is the cached prefix and stays byte-stable for a given chapter content version and prompt files; nothing user-specific enters it. The smoke script proves a cache hit on turn two for an authored chapter.
4. The tutor prompt refers to the student without assuming gender (spec 001–004 prompts say « elle »).
5. « Points à faire valider » becomes « Points à vérifier » in the prompt and templates: the tutor does not teach, cite or set exercises on these points, and tells the student to check them with their teacher.
6. Tool declarations do not vary by subject or chapter (spec 004 R7.4 extended to subjects).
7. The `teach` section label shown to the student becomes « Leçon » (it is « Cours » today), so « cours » means a course only.

### R8 — Subject pack templates

**As a** developer, **I want** one pack template per available subject, **so that** the agent's output has a predictable structure the validator, the tutor and the curriculum references rely on.

Acceptance criteria:

1. A template is a file per subject in the repository defining the required headings in order, their identifiers (`§1`, `§4.2`, exercise ids), and a one-line instruction per heading for the agent.
2. Mathematics: chapter goal and what the test expects; prerequisites; notation conventions; concepts in teaching order (definition as written, formulas verbatim with conditions, examples, derivation if given, common errors); vocabulary; sample exercises (id, statement, method, answer); points à vérifier. It is the structure of the existing chapter 1 pack, minus page provenance, which pasted text does not have.
3. Physics: chapter goal and what the test expects; prerequisites; quantities, symbols and units; concepts in teaching order (definitions, laws and formulas verbatim with conditions and units, experiments or observations described in the material, examples, common errors); vocabulary; sample exercises (id, statement, data, method, answer with unit); points à vérifier.
4. The seeded chapter 1 pack is adapted once to the mathematics template and passes the validator.
5. Adding a subject is a subject prompt, a pack template and flipping its availability; no other code change. A test proves every available subject has both files and that they load.

### R9 — Limits and cost control

**As the** operator, **I want** authoring bounded per student, **so that** one account cannot run up unbounded model cost.

Acceptance criteria:

1. At most `AUTHORING_CONCURRENT_PER_STUDENT` runs (default 2) are active per student; a further start (add, retry, source edit) is refused with 429 and a French message.
2. At most `AUTHORING_RUNS_PER_DAY` runs (default 20) start per student per rolling 24 hours, counted from the runs table so the limit survives restarts; beyond it, 429 with a French message stating when it frees up.
3. A run has an overall timeout `AUTHORING_TIMEOUT_S` (default 600); exceeding it ends the run in `failed`.
4. All limits are configuration, listed in `.env.example` and the documentation.

### R10 — Frontend routes and screens

**As a** student, **I want** the app organised around my courses, **so that** getting from sign-in to the next lesson or to adding a chapter is short.

Acceptance criteria:

1. Routes: `/courses` (« Mes cours »), `/courses/$courseId` (course page), `/courses/$courseId/chapters/$chapterId` (lesson), `/courses/$courseId/chapters/$chapterId/content` (view and edit). `/` redirects to `/courses` when signed in. `/classes` routes are removed.
2. The course page lists chapters in order with state (R4.1), marks the last chapter worked on with « Reprendre », and offers add chapter, rename course and delete course.
3. The lesson screen is the spec 002–004 screen with the course name and a way back to the course; strip, map, board, composer and voice are unchanged apart from R7.7.
4. Every new screen is in French, tutoiement, and usable at 400 px wide. Forms show one error per field under the field.
5. Changes to the frontend stay within its existing conventions (TanStack Router file routes, React Query, the component library already in use).

### R11 — Seed

**As a** developer, **I want** one command that creates a local test student with the existing chapter, **so that** I can open a working lesson without going through registration and authoring.

Acceptance criteria:

1. A backend command creates, or updates if present, a student account from configured or prompted credentials, a « Mathématiques 5e » course with subject mathematics, and a ready chapter whose pack and curriculum come from `courses/chapitre_1/`, without calling the model.
2. Running it twice leaves one user, one course and one chapter; it refreshes the chapter's content from the files and resets its progress.
3. The command refuses to run against a non-SQLite `DATABASE_URL` unless given an explicit override flag.
4. `documentation/running-locally.md` documents it.

## 4. Non-functional requirements

### 4.1 Architecture

1. The turn pipeline, the tool set, the SSE contract, the board cards and the voice bridge keep their contracts. What changes is where the chapter comes from (database instead of files) and how the system text is assembled (R7.3).
2. A chapter source abstraction offers what `ChapterSource` offers today (pack text, parsed curriculum, id) plus subject and content version, so the tutor, voice and routes change at their edges only.
3. The authoring agent is a service behind the existing provider seam: the `openai` import stays confined to `app/providers/`. The curriculum stage uses structured output with a JSON schema derived from the curriculum model.
4. Authoring runs in-process as background tasks, with state persisted after each stage transition, so a restart loses at most the running stage and is detected (R4.5). A job queue is not required in this epic; the design keeps the runner replaceable.
5. Ownership is checked in one dependency (replacing `require_enrolled`): course and chapter loaded by id and owner in the query.
6. Prompts and templates are files in the repository, read with the mtime cache; student content is never on the file system.
7. Schema changes go through Alembic migrations with portable types, as in spec 004.

### 4.2 Performance

1. A tutor turn adds at most one query to spec 004's (load chapter content with the ownership check). Parsed curricula are cached by chapter id and content version.
2. « Mes cours » and the course page answer in one or two queries each and under 200 ms locally with 30 courses of 40 chapters.
3. Authoring a 30 000-character chapter completes, in the common case, within 5 minutes end to end; the stage timings of R3.10 measure it.
4. Polling of chapter state (R4.2) is no more frequent than every 3 seconds and stops when no chapter is generating.

### 4.3 Security and privacy

1. Every course, chapter, run and progress route is scoped to the signed-in owner by the query. Tests prove student A cannot read, edit, delete, retry or open a lesson on student B's course or chapter by id.
2. All new routes declare roles (`student`) through `require_roles`; the spec 004 route-guard test covers them. Mutating routes pass the existing same-origin check.
3. Pack Markdown and source text are rendered without raw HTML; LaTeX rendering does not execute scripts. A test renders a pack containing `<script>` and an `onerror` attribute and proves nothing executes.
4. Source text, packs and curricula never appear in logs, errors or metrics; logs carry user id, course id, chapter id and run id only.
5. Request bodies are capped server-side to the chapter text and pack limits plus a margin, before parsing.
6. Deleting a course or chapter deletes its student content from the database in the same transaction; nothing is soft-deleted.

### 4.4 Reliability

1. A run's outcome is atomic: pack and curriculum are adopted together, with the content version incremented and progress reset in the same transaction, or not at all.
2. A provider failure, timeout or validation exhaustion never leaves a chapter without a state, nor a ready chapter without valid content.
3. A chapter's stored curriculum or pack that fails validation on read (e.g. rules tightened later) makes that chapter unavailable with a French message and a log line; other chapters and courses are unaffected.
4. Authoring is testable without the network: a fake provider drives both stages, repairs and failures, as `fake_llm.py` does for the tutor.
5. A live evaluation script runs authoring on sample material fixtures for mathematics and physics (committed under `backend/tests/fixtures/`) and reports validation results, attempts, timings and cost, for manual quality review of the output.

### 4.5 Usability

1. French copy throughout, tutoiement, no technical terms (« pack », « curriculum », « YAML ») in student-facing text: « Contenu du chapitre », « Parcours », « Points à vérifier ».
2. Destructive actions (delete course, delete chapter, save an edit that resets progress) require confirmation naming what is lost.
3. From sign-in, the common case (resume the last chapter) is two clicks: « Mes cours » → « Reprendre » on the course, or directly from the course card.
4. Forms, editors and the chapter state are keyboard-reachable and labelled; state changes of a generating chapter are announced to screen readers.

### 4.6 Known limitations carried forward

1. No mechanical answer checker; the tutor does not declare verdicts as certain.
2. No PDF or image input; pasting from a PDF loses figures and tables, which the agent flags as it can.
3. Mathematics and physics only.
4. Transcripts do not persist (spec 004).
5. No password reset, email verification, data export or account deletion (spec 004).
6. In-process authoring: runs do not survive a restart and do not scale across backend processes.

## 5. Open questions for the design

1. Curriculum editor form: a structured form per section, or a validated text editor on a readable format. The requirement (R5.3) is the capability and French errors, not the widget.
2. Whether the curriculum stage should receive the source text as well as the pack, if evaluation shows the path quality suffers without it (R3.1 says pack only).
3. Whether the pack is produced as Markdown directly or as structured output rendered to Markdown by code; the validator of R3.6 applies either way.
4. How much a subject prompt may shape the curriculum stage (e.g. physics favouring worked examples with units before practice) without per-subject section kinds, which stay out of scope.
