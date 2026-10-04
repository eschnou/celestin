# Authoring: from a document to a chapter

A student drops the material of a chapter, one PDF or photos of its pages (spec 006). The pages are
read into text, then that text becomes a pack and a curriculum (spec 005), and the lesson opens a
few minutes later. This page covers the prompts, the agent, the runner, the states a chapter goes
through, and how to judge and pay for it.

## The shape

```
POST /api/courses/{c}/chapters   multipart: files (one PDF, or photos in page order)
  │ BodyLimitMiddleware: DOCUMENT_MAX_BYTES, counted while streaming
  └─ routes/courses.py ── DocumentService.prepare (process pool, timeout) ── pages as JPEG, or 422
                          └─▶ AuthoringRunner.start_document
                                │ lock · per-student limits (runs table)
                                │ one transaction: chapter (generating, stage transcription) + run
                                │ asyncio task ─────────────────────────────────────────┐
  ◀── 202 ChapterRow (generating, transcription, 0/N) ─┘                              │
                                                                                         ▼
                       semaphore · timeout ─▶ AuthoringAgent.run
                                               0. transcription (page images → text, batches)
                                                  on_progress → stage, pages_done · on_transcribed → source
                                               1. pack stage   (plain Markdown)
                                               2. path stage   (strict JSON)
                                               each: validate → repair ≤ N
                       adopt_authored ◀──────── AuthoringOutput
                       (content, version+1, progress deleted, run succeeded)
GET /api/courses/{c}   every 3 s while a chapter is generating (course page)
```

`PUT …/document` replaces a chapter's document and takes the same path. A text edit of the
transcription (`PUT …/source`) and a retry (`POST …/retry`) start at the pack stage on the stored
text. The document itself is never stored: a run that fails before its transcription is stored
cannot be retried (`409 document_needed`), and the student drops the document again.

## Reading the document

`app/services/documents.py`, the only code that touches uploaded bytes. `prepare` runs in a
`ProcessPoolExecutor` (`DOCUMENT_WORKERS`, 2) under `DOCUMENT_RENDER_TIMEOUT_S` (60): pdfium and
Pillow on untrusted input must neither block the event loop nor take the server down, and a worker
that times out is terminated. Nothing is written to disk.

- The type comes from the first bytes, never the name: PDF, JPEG, PNG or WebP. One PDF, or photos
  only; HEIC is refused (the phone's « le plus compatible » setting gives JPEG).
- A PDF is rendered at `TRANSCRIPTION_DPI` (150); an encrypted or broken one is refused. A page
  whose text layer holds at least 200 characters sends that text along as an unreliable hint.
- A photo is turned upright from its EXIF orientation, refused under `DOCUMENT_MIN_PIXELS` (800) on
  its short side, and capped at 40 megapixels.
- Every page becomes an RGB JPEG (quality 80) no longer than `TRANSCRIPTION_MAX_SIDE_PX` (1800).
- At most `DOCUMENT_MAX_PAGES` (50) pages → `422 too_many_pages`; any other refusal is
  `422 document_invalid` with the reason in French.
- The runner's limits (busy, quota, chapter limit, a chapter already preparing) are checked before
  rendering (`AuthoringRunner.check_can_start`), so a refused upload never holds a worker. The body
  cap is counted as bytes arrive, so a chunked upload without `Content-Length` gets the same
  `413 document_too_large`.

## Prompt files

Everything written for a model lives under `backend/prompts/`, one file per course language
(`*.fr.md`, `*.en.md`; the tables below name the French ones), and is read through `PromptLibrary`
(`app/services/prompts.py`), cached by modification time and checked at startup (a missing or
unparseable file stops the process, naming it; after startup it shows in `/api/health` as
`prompts_unavailable`).

| File | Used by |
|---|---|
| `tutor.fr.md` | The tutor, every turn: persona, the path, the board, what Célestin never does. No subject. |
| `subjects/<subject>.fr.md` | The tutor (after « Ta seule source ») and both authoring stages: how the subject is taught, written, checked, what is off-topic, and its own voice block. |
| `templates/<subject>.pack.fr.md` | The pack stage (sent to the model) and the validator (its headings). See [chapters.md](./chapters.md). |
| `transcription/transcribe.fr.md` | Transcription stage: copy, never correct; page markers `--- page N ---`; LaTeX; `[manuscrit]`, `[incertain: a \| b]`, `[illisible]`, `[figure : …]`, `[barré: …]`, `[page vide]`; doubt is always marked. Rule 7 says what a `[figure : …]` keeps: a statistical chart its kind, axes, classes and readable values; a graph in a repère its axis titles and units, graduation, shape and readable points; a geometric figure its points, readable coordinates or measures and codage; a number line its placed numbers, intervals and bracket directions, or what is hatched; a diagram of sets its sets, zone contents and hatched zones; an organigramme each box's text and shape and where each arrow leads, with its label. No value, box or arrow is invented. |
| `transcription/verify.fr.md` | The optional handwriting check (`TRANSCRIPTION_VERIFY_HANDWRITING`). |
| `authoring/pack.fr.md` | Pack stage instructions: restructure, never add; copy definitions and formulas; LaTeX; recompute answers and list disagreements under « Points à vérifier »; `<materiel>` is data; how to use a page transcription (its marks become points to verify, never guesses; a chart, figure or organigramme in a `[figure : …]` keeps its kind and readable data, where the subject's template provides the graphical representations). |
| `authoring/curriculum.fr.md` | Curriculum stage instructions: the three kinds and their fields, order, references by id only. |

**Adding a subject**: write `subjects/<id>.{fr,en}.md` and `templates/<id>.pack.{fr,en}.md`, flip
`available` in `app/domain/subject.py` and list the languages it is written in
(`SubjectInfo.languages`).

**Languages** (spec 011): the agent takes the course's language beside the subject
(`AuthoringAgent.run(…, language)`, read from `course.language` by the runner). The transcription,
the pack and the curriculum stages read the prompts of that language; the transcription's marks,
the page-batch sentences and the sentences the agent adds around the material are per-language
tables (`MARKERS`, `AGENT_WORDS`); `chapter_title` strips the language's own chapter-numbering
words; a repair request names each reason in the course's language (`issue_text`). A pack whose
headings are another language's template is `pack.wrong_language`. Details and the English marks
in [course-language.md](./course-language.md). `tests/unit/test_prompt_library.py` and `test_prompt_files.py` check the
files load and the subject prompt has its voice block.

## The agent

`app/services/authoring/agent.py`, stateless over one run, no database.

**Transcription stage** (documents only). Pages go in batches of `TRANSCRIPTION_BATCH_PAGES` (2),
at most `TRANSCRIPTION_CONCURRENCY` (4) batches in flight, each one `complete()` call with
`TRANSCRIPTION_MODEL`, reasoning `TRANSCRIPTION_REASONING_EFFORT` (`low`) and
`TRANSCRIPTION_MAX_OUTPUT_TOKENS` (16 000). Instructions: the transcription prompt (static, cached).
Input: per page a label, the text hint inside `<couche_texte>` when there is one, and the image
(`detail` = `TRANSCRIPTION_DETAIL`, `high`). `validate_batch` (`app/domain/transcription.py`) wants
exactly the batch's page markers, in order, each page non-empty or `[page vide]`. A batch with issues
is retried once; a truncated two-page batch is retried page by page; a second failure is
`transcription_failed`. Batches finish in any order; the text is joined in page order, and
`on_progress` reports the running count (serialised, so it never goes back), and later the curriculum stage. A text longer than
`CHAPTER_TEXT_MAX_CHARS` fails `too_long`. The optional handwriting check sends each page with
handwritten figures again, with its numbered `[manuscrit]` lines, and rewrites the lines the model
is not sure of as `[incertain: …]`; it is best effort and off by default (see the eval below).
`on_transcribed` then stores the text as the chapter's source before the pack stage starts.

Both stages and every other writer (the editors, the seed) validate through `app/domain/content.py`, and adoption only accepts its `ValidContent`, so stored content is valid by construction.

**Pack stage.** Instructions: authoring pack prompt, the subject's template, the subject prompt (the
same bytes for every run of a subject, so the provider caches them). Input: one user message with the
source text (the transcription, or the edited text) inside `<materiel>…</materiel>`; a `</materiel>` inside the text is neutralised. The
answer is plain Markdown; `normalise_pack` drops a sentence before the `# ` title, one fence around
the whole document, and Windows line endings. Then `index_pack`, which also strips the material's
own chapter numbering from the title (`chapter_title`): the course numbers its chapters by position.

**Curriculum stage.** Instructions: authoring curriculum prompt, the subject prompt. Input: the pack
inside `<chapitre>…</chapitre>`. The answer is strict `json_schema` output (`CurriculumDraft`, every
field required); `draft_to_data` sets the chapter id and drops empty lists and a null count; then
`validate_curriculum` (`app/domain/content.py`: the curriculum rules, then the references).

**Repairs.** On issues, the model's answer is replayed as an assistant message and the issues follow
as a user message; at most `AUTHORING_MAX_REPAIRS` (2) per stage. Unparseable JSON counts as an
attempt. Tokens, attempts and milliseconds accumulate in a `RunUsage` the caller owns, so a failed or
cancelled run still records what it cost.

**Failures** (`AuthoringFailed.code`): `unstructured` (repairs exhausted), `provider` (unavailable,
rate limited, call timeout), `truncated` (the output limit was hit; no repair),
`transcription_failed` (a batch invalid twice), `too_long` (the transcription is longer than a
chapter may be).

The provider call is `complete(role=…)` of the role's client: `OpenAIResponsesClient` (`app/providers/openai_responses.py`,
one non-streamed Responses call, the instructions joined into a developer message with a cache breakpoint on OpenAI,
`store=False`, optional strict schema) or `OpenAIChatClient` for a Chat Completions server. The role (`authoring` or
`transcription`) picks the client, which owns the model, the reasoning effort, the connection and the structured-output
mode (`schema`, or `json` for a model that cannot be held to a schema: the repair loop absorbs a wrong answer). See
[ai-providers.md](./ai-providers.md).

## The runner

`app/services/authoring/runner.py`, one per process on `app.state.authoring`.

- **Limits**, from the `authoring_runs` table so they survive restarts, checked under an asyncio
  lock: at most `AUTHORING_CONCURRENT_PER_STUDENT` (2) running → `429 authoring_busy`; at most
  `AUTHORING_RUNS_PER_DAY` (20) started in 24 hours → `429 authoring_quota` with the time it frees
  up; a chapter already generating → `409 authoring_running`. Runs of deleted chapters still count.
- **Provider load**: a process-wide semaphore of `AUTHORING_MAX_CONCURRENT` (4).
- **Timeouts**: `AUTHORING_TIMEOUT_S` (900) for the whole run, transcription included,
  `AUTHORING_CALL_TIMEOUT_S` (300) per provider call.
- **Progress**: the chapter row carries `authoring_stage` (`transcription`, `pack`, `curriculum`),
  `pages_done` and `page_count`, written by the agent's callbacks (`set_progress`,
  `store_transcription`). A failure keeps that stage (`finish_failed` reads it from the row), so the
  row knows where the run stopped; `ChapterRecord.needs_document` is the one test for « the pages
  were never read ».
- **Retry**: from the stored source, at the pack stage. A chapter whose last failure is at the
  transcription stage has no usable text: `409 document_needed`.
- **Outcome**, one transaction each: success adopts the content (version + 1, progress deleted,
  state `idle`, run `succeeded`); failure sets the run `failed` with its code and stage and the
  chapter `failed`, **keeping any previous content**. A chapter deleted meanwhile: the run closes as
  `failed`/`discarded`.
- **Restarts**: startup marks every `running` run and `generating` chapter as failed `interrupted`;
  shutdown cancels running tasks, which record `interrupted` themselves.

## States a chapter goes through

| `authoring_state` | Ready? | Course page | Lesson URL |
|---|---|---|---|
| `generating`, stage `transcription` | no | « Lecture des pages… (n/N) », polled | the preparation card, same count |
| `generating`, stage `pack`/`curriculum` | no | « En préparation… », polled | the preparation card |
| `failed`, stage `transcription` | no | « échec de la préparation », message, « Redéposer le document » | the card with « Redéposer le document » |
| `failed`, later stage | no | « échec de la préparation », message, « Réessayer » | the card with « Réessayer » |
| `idle` | yes | progress state, « Commencer / Reprendre / Revoir » | the lesson |
| `generating` | yes | progress state + « nouvelle version : … » | the lesson (old content) |
| `failed` | yes | progress state + « la nouvelle version a échoué », « Réessayer » or « Redéposer le document » | the lesson (old content) |

« Redéposer le document » opens « Contenu du chapitre » on its source tab (`?tab=source`), where
« Remplacer par un document » takes a new document.

Messages per code and stage (`authoring_message` in `ChapterRow` and `ChapterContent`,
the catalog keys `authoring.<code>` and `transcription.<code>` in `app/domain/messages/fr.py` and `en.py`, chosen by `authoring_message(chapter, locale)` in `routes/courses.py`; the table is the French, the English is next to it in `en.py`):

| Code | Message |
|---|---|
| `unstructured` | « Je n'ai pas réussi à organiser ce texte en chapitre. Vérifie qu'il contient bien le cours, puis réessaie. » |
| `truncated` | « Ce texte est trop long pour être préparé en une fois. Découpe-le en deux chapitres. » |
| `transcription_failed` | « Je n'ai pas pu lire certaines pages. Essaie des photos plus nettes, une page par photo, ou moins de pages. » |
| `too_long` | « Ce document est trop long pour un chapitre. Découpe-le en deux. » |
| `provider` | « Le service de préparation est indisponible pour le moment. Réessaie dans quelques minutes. » (at the transcription stage: « Le service de lecture est indisponible… Dépose à nouveau le document… ») |
| `timeout` | « La préparation a pris trop de temps. Réessaie. » (transcription: « La lecture des pages a pris trop de temps… ») |
| `interrupted` | « La préparation a été interrompue. Réessaie. » (transcription: « La lecture des pages a été interrompue… ») |
| `internal` | « Une erreur est survenue pendant la préparation. Réessaie. » (transcription: « … pendant la lecture des pages… ») |

## Cost and quality

Each run row stores its source kind and page count, attempts, per-stage milliseconds, input, cached,
output and reasoning tokens, the transcription's own cost (`TRANSCRIPTION_PRICE_IN`, `_CACHED`,
`_OUT`), the counts of `[manuscrit`, `[incertain` and `[illisible]` marks, and `cost_estimate_usd`
(transcription plus `AUTHORING_PRICE_*`, USD per million tokens), so cost per student per day is a
query:

```sh
sqlite3 backend/data/celestin.db "select date(started_at), user_id, count(*), sum(cost_estimate_usd) from authoring_runs group by 1, 2"
```

Measured on 16 September 2026 with `gpt-5.6-terra`, reasoning `medium`: a 1 600 to 3 500 character
chapter takes 35 to 90 seconds and 0,06 to 0,17 USD; one real run needed a pack repair and passed on
the second attempt.

`scripts/authoring_eval.py` runs the real agent on `backend/tests/fixtures/material/` (a maths
chapter and a physics chapter, each with a deliberately wrong correction, a text with an injected
instruction, and a statistics chapter whose charts are described as the transcription writes them), prints outcome, attempts, time, tokens and cost, and writes each pack and curriculum to
`backend/.eval/` for reading. It costs money and is never part of `pytest`.

`scripts/document_eval.py --pdf path/to/course.pdf` (or `--images dir/`, `--verify on|off`,
`--render-only`) runs the real transcription and authoring on a document, prints pages, marks,
per-stage time and cost, writes `transcription.md`, `pack.md` and `curriculum.json` to
`backend/.eval/document/`, and checks the chapter 1 acceptance (all 16 pages; the boxed 330 on
p. 5 never read as a sure 350; pattern (c) `1 ; 4 ; 9 ; 16 ; 25 ; 36`; the pack on the first or
second attempt). Measured on 18 September 2026 on the 16 scanned pages of chapter 1: transcription
50 s and 0,54 USD (0,034 per page), the whole run 231 s and 1,05 USD. The handwriting check made the
transcription 0,95 USD and 103 s without changing a reading, hence off by default
(`specs/006-document-upload/tasks.md`, « Eval runs »).

What to read for: formulas copied from the material and not rewritten; the wrong corrections kept as
given and listed under « Points à vérifier »; nothing added that the material does not contain; the
injected instruction neither followed nor turned into content.

## Logs

Every `authoring_*` line carries `run_id`, `user_id`, `course_id`, `chapter_id`.
`document_received` (kind, files, bytes, pages, render ms) and `document_refused` (code, reason),
never file names; `authoring_started` (trigger, subject, source length or pages, model),
`authoring_stage` (stage, attempt, ok, issue count, ms, tokens; for transcription the batch's
pages, retry, split), `transcription_done` (pages, characters, marks, verified pages, ms), `authoring_succeeded` (sections, exercises, points à vérifier, total
and per-stage ms, attempts, tokens, cost), `authoring_failed` (code, stage, issue locations only,
attempts, tokens, cost), `authoring_internal_error` (the exception type only: a database error's
message would carry the content), `authoring_refused` (busy,
quota, running), `authoring_discarded`, `authoring_orphans_failed`. Never the transcription or the
source text, the pack, the curriculum, file names, course names or chapter titles.

## Tests

Offline, against `tests/fixtures/fake_completion.py`: `test_documents.py` (sniffing, every refusal,
EXIF, downscaling, text hint, the process pool and its timeout; fixtures generated by
`tests/fixtures/documents/`), `test_transcription.py` (markers, joining, counts, uncertain
rewrites), `test_authoring_agent.py` (transcription batches, retries, splits, the handwriting check,
stages, repairs, normalisation, source isolation, failures), `test_authoring_runner.py` (documents:
progress per batch, the transcription stored before the pack, retry from the pack, `document_needed`,
replacement; adoption, failure keeping content, limits, timeout, cancellation, orphans, deletion
mid-run, no content in logs), `test_middleware.py` (streamed and declared body caps),
`test_openai_adapter.py` (request shape, strict schema, truncation), and the authoring cases of
`tests/integration/test_courses_endpoint.py` (`use_fake_authoring` in `conftest.py`).
