# Spec 020 — Révision: rehearse a whole course before the test

No SDD trio, at the owner's request (15 November 2026): this file holds the decisions and the
contract. Builds on specs 018 (stored séances) and 019 (open path, skipped sections). The brief's
§6.6 and phase C.

The owner's decision: **révision works on the whole course**, not one chapter. The product
direction: tools for an autonomous student, not supervision.

## What it is

A third mode. The student opens « Réviser » on a course, picks the chapters the test covers, and
Célestin makes them retrieve what they know: definitions to recite, variants of the course's
exercises, reasoning to reproduce, **mixed across the chosen chapters**. After each question the
student says how it went — acquis, fragile, à revoir — and that self-assessment is kept, per
section, so the next révision starts from what is fragile.

It is the door for the student who saw the material in class: test first, then go and do the
sections that turned out weak (open path), or reread their boards (cahier).

## Decisions

**D1. A mode, not a second tutor.** A value in `domain/mode.py`, two prompt files per language, a
row in the tool table, one transport on the frontend. The same turn loop, SSE contract, board,
reducer and stored-conversation machinery.

**D2. Course scope, chosen chapters.** A révision belongs to a course and a set of its ready
chapters, fixed when it starts. The prompt carries the pack of every chosen chapter. Bounded by
`REVISION_MAX_PACK_CHARS` (default 120 000 characters of packs, about 37 000 tokens in French):
a selection over it is refused (`422 revision_too_large`) and the student picks fewer chapters.
At least one chapter (`422 revision_no_chapter`). The prefix is cached per selection; the first
turn of a large course is a large uncached read, which is the accepted cost of the owner's choice.

**D3. The record is the student's own judgement, never a verdict from the model.** The tutor
prompt already says Célestin cannot check a calculation with certainty and never declares a
definitive « juste » or « faux »; no mechanical checker exists yet for exercises. So révision does
not invent one: after each question is settled (found, or revealed step by step as the shared
rules allow), Célestin shows the course's own wording or method on the board, the student compares
and says « acquis », « fragile » or « à revoir », and Célestin records exactly that with
`record_result`. He may say in one sentence when he sees it differently (« tu as eu besoin de deux
indices, fragile me paraît plus juste : c'est toi qui décides ») and never overrules. When a
mechanical checker exists (brief §12.1), it feeds the same record.

**D4. Nothing here moves the path.** No section tool is offered and the turn context has no
progress store: the two locks of the discussion. Révision *reads* progress (done, skipped, never
done) and the results record to decide what to ask.

**D5. No voice in révision, for now.** The voice routes are chapter-scoped; a course-scoped voice
session is a later piece. Dictation and photographed work (both course-scoped already) work.

**D6. One live révision per student and course.** A stopped or failed turn stores nothing, as in a
discussion (the browser's stop report of spec 018 is the parcours's only) — and that includes its
results: `record_result` notes in the turn's memory, and the results are written with the
transcript, in one transaction, when the turn ends. A result never exists without its stored call. « Nouvelle révision » closes it (`replaced`) and
starts another, with a new choice of chapters. A révision whose chapters changed (content version
bumped, chapter deleted) is closed `content_changed` lazily. Caps and append policy are the
discussion's. Daily quota: `REVISION_SESSIONS_PER_DAY` (default 10).

## Data

Migration `0014`:

- `conversations.chapter_id` becomes nullable; `conversations.course_id` (FK `courses`, cascade),
  nullable, set for a révision; `conversations.scope` JSON, nullable: `[{chapter_id,
  content_version}]` for a révision. A check keeps exactly one of `chapter_id` / `course_id` set.
- `ck_conversations_mode` gains `revision`; a partial unique index on `(user_id, course_id)
  where state = 'live' and mode = 'revision'`.
- New table `revision_results`: `id`, `user_id` (cascade), `course_id` (cascade), `chapter_id`
  (cascade), `section_id` String(40), `outcome` in (`solid`, `shaky`, `todo`), `content_version`,
  `conversation_id` (nullable, set null), `created_at`. Index `(user_id, course_id)`.
  No free text: a result is a section and one of three words.

A chapter's content change leaves its old results behind; reads keep only results recorded against
the chapter's current content version.

## The tool

`record_result(chapter, section_id, outcome)`, strict, révision only, declared after every
existing tool:

- `chapter`: the chapter's number as the prompt shows it (its position in the course);
- `section_id`: a section of that chapter's path, the one the question belongs to;
- `outcome`: `solid` (acquis), `shaky` (fragile), `todo` (à revoir).

Refused (tool error the model reads) when the chapter is not in this révision or the section is not
in that chapter. One row in the registry with its `replay` and `shown` hooks, like every tool since
spec 018; its replayed output is rebuilt from what the stored entry recorded, never from the state now. Noted in the turn's memory (so the tally counts it at once) and written to `revision_results` with the
transcript when the turn ends (D6). Output: a one-line tally of this révision so far.
Event `revision.result`: `{chapter_id, section_id, outcome, marker}`; the marker
(`marker.revision_result`) says what was noted, so the student sees everything that is recorded
about them. The latest result per section is the one that counts.

## What the model reads

- `tutor.<lang>.md`, the subject prompt: unchanged.
- At `<!-- COURSE_PACK -->`: the chosen chapters' packs, in course order, each under a one-line
  header naming its number and title (per-language words), so Célestin can say where a notion lives.
- At `<!-- CURRICULUM -->`: one overview per chapter (number, title, its sections with id, kind,
  title, goal), read-only: no tool is named.
- `modes/revision.<lang>.md` and `modes/revision.opening.<lang>.md`: see below.
- Trailing state message (after the transcript, free to vary): the date and time; per chapter,
  which sections are done, skipped, never done; the latest self-assessment per section with its
  date; the tally of this révision.
- Tools: `display_board`, `clear_board`, `record_result`.

### The mode layer (French reference; English and Dutch say the same in their register)

> ## La révision
>
> Ici, pas de parcours et pas de nouvelle matière : ton élève prépare une interrogation et vient
> vérifier ce qui tient. Tu as devant toi plusieurs chapitres du même cours ; chacun reste la seule
> source pour ce qu'il contient.
>
> - **Tu fais retrouver, tu ne réexpliques pas d'abord.** Une question à la fois, posée sans le
>   cours sous les yeux : une définition à réciter, une formule à redonner avec ses conditions, une
>   variante d'un exercice type, un raisonnement du cours à refaire. Tu attends la réponse.
> - **Tu mélanges.** Tu passes d'un chapitre à l'autre et d'une notion à l'autre, et tu n'annonces
>   pas à quelle notion se rattache un exercice : reconnaître laquelle employer fait partie de ce
>   qu'on révise.
> - **Tu commences par ce qui est fragile.** Le message à la fin te dit, section par section, ce
>   que ton élève a fait, passé, jamais vu, et ce qui a été noté fragile ou à revoir les fois
>   précédentes. Les sections passées n'ont jamais été travaillées avec toi : elles se testent en
>   priorité, sans reproche.
> - **Les exercices vont au tableau** (`exercise`, ou `check_question` pour une question à choix).
>   Une définition à réciter se demande dans la conversation. Tant qu'une question est ouverte, la
>   règle habituelle tient : des questions, des indices, jamais la réponse.
> - **Quand la question est réglée**, tu affiches au tableau la formulation du cours (ou la méthode
>   du cours), mot pour mot, pour que ton élève compare avec ce qui a été répondu. Puis tu demandes
>   son propre bilan en une phrase : acquis, fragile ou à revoir ?
> - **Tu notes ce bilan avec `record_result`**, tel que ton élève le dit. C'est son jugement, pas le
>   tien : tu ne décides jamais à sa place et tu ne notes rien qui n'a pas été dit. Si tu vois les
>   choses autrement (deux indices, une réponse donnée par toi), tu le dis en une phrase, et c'est
>   ton élève qui tranche.
> - **Ce qui est fragile revient.** Une question notée fragile ou à revoir se retravaille tout de
>   suite, brièvement, avec les mots du cours ; puis elle revient plus tard dans la séance, sous une
>   autre forme.
> - **Tu fais le point régulièrement** : toutes les cinq ou six questions, ou quand ton élève le
>   demande, une carte `recap` (ce qui tient, ce qui est à retravailler, la suite). Pour ce qui est à
>   retravailler, tu dis où ça se travaille : la section du parcours, et le cahier si elle a déjà
>   été faite. C'est ton élève qui y va : tu n'ouvres aucune section d'ici.
> - **C'est ton élève qui mène sa révision.** S'il ou elle veut un seul chapitre, seulement les
>   définitions, s'arrêter là : tu suis.

Opening: greet, say in one sentence what is in scope and what the record shows (what was never
done or skipped, what was noted fragile), offer two or three ways to go (everything mixed, the
fragile points first, definitions only), ask, wait. No card in the first turn.

The French text avoids gendered pronouns for the student, as the other prompt files do (« ton
élève »); rewrite « s'il ou elle » accordingly when writing the file.

## Wire contract

All routes: the student who owns the course (404 otherwise).

### `GET /api/courses/{c}/revision`

```jsonc
{ "revision": null | { "id": "…", "chapter_ids": ["…"], "entries": [StoredEntry…],
                       "entry_count": 12, "created_at": "…" },
  "chapters": [ { "id": "…", "position": 2, "title": "…", "ready": true,
                  "section_count": 9, "done_count": 4, "skipped_count": 1,
                  "sections": [ { "id": "…", "index": 1, "kind": "teach", "title": "…",
                                  "state": "done" | "skipped" | "todo" } ] } ],   // every chapter of the course; `sections` is [] for a chapter that is not ready
  "results": [ { "chapter_id": "…", "section_id": "…", "outcome": "shaky", "at": "…" } ] }  // latest per section
```

The course's name, subject and language come from the course view the page already reads. Beats,
exercise pools and `done_when` never cross this wire. `StoredEntry` as in spec 018, plus `{kind: "tool", name: "record_result", arguments: {…},
chapter_id, section_id, outcome, marker}`.

### `POST /api/courses/{c}/revision` → 201

`{ "chapter_ids": ["…", …] }` → the same body as the `GET` (`revision`, `chapters`, `results`), so the
page needs no second read. Closes the live one as `replaced`.
`422 revision_no_chapter`, `422 revision_too_large`, `409 chapter_not_ready` for a chapter without
content, `404` for a chapter of another course, `429 revision_quota`.

### `POST /api/revision/turn`

`{ "course_id": "…", "revision_id": "…", "message": "…" | null }` → SSE, the same events plus
`revision.result`. `message: null` opens, only while empty. `409 conversation_closed` with its reason.

## Interface

- **Course page**: « Réviser », enabled as soon as one chapter is ready.
- **Chapter bar**: the mode switch gains « Révision », a link to the course's révision.
- **`/courses/$courseId/revision`**:
  - no live révision (or « Nouvelle révision »): a chooser listing the ready chapters with a
    checkbox each (preselected: those with progress; all when none has any; `?chapter=<id>` preselects
    one), their done / skipped counts, and « Commencer la révision ». Too large: the server's message,
    and the chooser stays.
  - a live révision: the tutor column and the board, like a discussion (no strip, no map, no
    page-turn button). Three quick replies under the composer — « Acquis », « Fragile », « À revoir »
    — send the learner sentence in the course's language (`useLearnerSentences`; French:
    « Pour moi, c'est acquis. », « Pour moi, c'est fragile. », « Pour moi, c'est à revoir. »). A « Bilan » sheet lists, per chapter, each
    section with its latest self-assessment and date (« pas encore testée » otherwise), with links to
    the section's chapter (parcours) and to its cahier. « Nouvelle révision » confirms first.
- Copy in French, English and Dutch.

## Invariants touched

- *Verdicts*: none is produced by the model; the record is a self-assessment (D3).
- *No answer while open*: the shared rules, unchanged; the course's wording goes on the board only
  once the question is settled.
- *Pack as only source*: each chapter's pack for its own content; the board's « definition must
  quote the pack » rule checks against the chosen packs.
- *Privacy*: results and révisions are rows owned by the student, deleted with the course, the
  chapter or the account; logs and the usage ledger carry ids and counts only.
- *Model input wall*: the révision's input takes the course language only.
