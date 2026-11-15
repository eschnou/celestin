# Révision

A third mode (spec 020): the student opens « Réviser » on a course, picks the chapters the test
covers, and Célestin makes them retrieve what they know — a definition to recite, a variant of a
course exercise, a line of reasoning to redo — **mixed across the chosen chapters**. After each
question the student says how it went (acquis, fragile, à revoir), and that self-assessment is kept
per section, so the next révision starts from what is fragile. It is the door for the student who
saw the material in class: test first, then go and do the sections that turned out weak (the open
path, spec 019), or reread their boards (the cahier, spec 018).

The decisions are archived in `specs/020-revision-mode/README.md` (D1–D6, no SDD trio); this page
says how the built system works.

Nothing here is a second tutor (D1). The same turn loop, SSE contract, board, reducer and
stored-conversation machinery as a discussion ([discussion.md](./discussion.md)); a mode selects:

| What | Révision |
|---|---|
| Prompt layer | `prompts/modes/revision.<lang>.md` + `.opening.<lang>.md` |
| Tool set | `display_board`, `clear_board`, `record_result` |
| What a turn posts | `{course_id, revision_id, message}` |
| Who owns the transcript | the server: one `conversations` row per révision, named by its course |

## The decisions that carry weight

- **D2 — a course, chosen chapters.** A révision belongs to a course and a set of its ready chapters,
  fixed when it starts. The prompt carries every chosen pack, so a selection is bounded by
  `REVISION_MAX_PACK_CHARS` (120 000 characters of packs by default, about 37 000 tokens of French);
  over it the start is refused `422 revision_too_large` and the student picks fewer chapters.
- **D3 — the record is the student's own judgement, never a verdict from the model.** No mechanical
  checker exists yet for exercises, and the tutor prompt already says Célestin cannot check a
  calculation with certainty. So once a question is settled Célestin shows the course's own wording
  or method on the board, the student compares and says « acquis », « fragile » or « à revoir », and
  Célestin records exactly that with `record_result`. He may say in one sentence that he sees it
  otherwise; he never overrules, and he notes nothing that was not said. That is prompt text
  (`modes/revision.<lang>.md`) and a probe (below); what the tool accepts — a section of a chosen
  chapter and one of three words — is code. When a checker exists (brief §12.1) it feeds the same
  record.
- **D4 — nothing here moves the path.** The two locks of a discussion: no section tool is declared
  (and `registry.execute` refuses one), and the turn context has no progress store (`save=None`). A
  révision *reads* each chapter's progress (done, skipped, never done) and the results to decide what
  to ask. An integration test asserts against the database that a turn calling `start_section`,
  `skip_section` and `complete_section` leaves `progress` exactly as it was.
- **D5 — no voice for now.** The voice routes are chapter-scoped; `VoiceSessionRequest` and
  `VoiceToolRequest` take a `ChapterMode` (`parcours` or `discussion`), so `mode: "revision"` is a
  `422` there. Dictation and photographed work are course-scoped and work.
- **D6 — one live révision per student and course.** « Nouvelle révision » closes it (`replaced`) and
  starts another with a new choice. A révision one of whose chapters changed version, no longer
  reads, or was deleted is closed `content_changed`, lazily, the next time it is read. A stopped or
  failed turn stores nothing (the discussion's policy), and that includes its results: `record_result`
  notes in the turn's memory, and the results are written with the transcript, in one transaction,
  when the turn ends, so a result never exists without its stored call. The caps are the
  discussion's; at most `REVISION_SESSIONS_PER_DAY` (10) révisions start per student and day.

## The data

Migration `0014`:

```jsonc
// conversations, mode = 'revision'
{
  "id": "…", "user_id": "…",
  "chapter_id": null,                    // nullable since 0014; set for every other mode
  "course_id": "…",                      // FK courses, ON DELETE CASCADE; null for every other mode
  "scope": [{"chapter_id": "…", "content_version": 3}, …],   // the chosen chapters, course order
  "mode": "revision", "content_version": 0,   // unused: the versions are in `scope`
  "entries": [ … ], "entry_count": 12, "char_count": 4210, "card_count": 3,
  "state": "live", "closed_reason": null      // replaced | content_changed | capped
}

// revision_results: one self-assessment, no free text
{ "id": 7, "user_id": "…", "course_id": "…", "chapter_id": "…",   // all three ON DELETE CASCADE
  "section_id": "sa-definition", "outcome": "shaky",               // solid | shaky | todo
  "content_version": 3, "conversation_id": "…",                    // ON DELETE SET NULL
  "created_at": "…" }
```

- `ck_conversations_scope` keeps each mode on its side: a révision names its course and no chapter,
  every other mode its chapter and no course. `ck_conversations_mode` gains `revision`.
- `uq_conversations_live_revision` is the partial unique index on `(user_id, course_id)` where
  `state = 'live' and mode = 'revision'`. A révision's null `chapter_id` never meets
  `uq_conversations_live` (null is distinct from null in a unique index, in SQLite and PostgreSQL).
- Every chapter read of `ConversationRepository` (`live`, `get_owned`, `seances`, `seances_by_id`,
  `count_seances`, `card_counts`, `closed_seance_ids`) names a chapter or the parcours, so it never
  meets a révision, and the chapter entry points (`live`, `get_owned`, `start`) take a `ChapterMode`,
  so `mode="revision"` cannot be passed to them; `started_since` names its mode; « Recommencer le
  chapitre » deletes parcours rows only. A révision has its own entry points: `live_revision`,
  `get_revision` (owner, course and mode in the query), `start_revision` (closes the live one and
  inserts, one transaction). Both kinds share one where-builder (`_owned`: student, mode, and a
  chapter or a course) and one implementation per operation; a start of either kind that trips its
  unique index (a second tab starting one at the same instant) is `ConversationBusy`, which the
  révision words as its own `409 conversation_busy`.
- **Results are written with their turn.** `ConversationRepository.append(…, results=…)` appends the
  turn's entries and inserts its `revision_results` rows in one transaction, in call order (the latest
  per section is the last written): a busy guard, a failed write or a stream that never reached its
  end writes neither. The rows are read from the turn's stored `record_result` calls
  (`services/revision.turn_results`: the call's chapter id, section and word, the version the
  révision holds for that chapter), never from anything the tool wrote mid-turn.
- `RevisionResultRepository.latest(user, course, {chapter: version}, conversation_id=None)` is the
  one read of results, one query: `(every révision's, this révision's)` latest per `(chapter,
  section)`, among results recorded against the given versions (filtered in SQL, so a chapter's
  content change leaves its old results behind, unread), the second only with a `conversation_id`
  (its tally). Ordered by `created_at` then the integer id.
- `ai_usage.feature` gains `revision_turn` (the ledger's check constraint is rebuilt).
- The downgrade deletes the révision rows, their results and the `revision_turn` ledger rows (the
  older schema has no place for them), keeps every discussion, séance and other ledger row. Tested up
  and down with data on SQLite (`test_upgrade_from_0013_…`); the PostgreSQL path (named foreign key
  `fk_conversations_course_id`, batch operations that become plain `ALTER`s) is written but not run.

The code: `app/services/revision.py` (`RevisionService`: `chapters` — every chapter of the course,
or only the ids given —, `live`, `start`, `open_revision`, `turn_entries`, `append`, `results`; and
`turn_results`), sharing `app/services/conversations.py` with the two other modes (`stored_entries`,
`entries_from_events`, `opening`, `is_full`, `live_row` — the live row unless a staleness predicate
says its content is gone, closed `content_changed` then —, `check_quota` and `append`, the
discussion's one write per turn, which carries a révision's results); `app/domain/revision.py` (the
pure data: `RevisionChapter`, `RevisionScope`, `Noted`, `NewResult`, `tally`).

**What a request loads.** The page's read (`GET`) and a start (`POST`) read every chapter of the
course once (the chooser lists them all) and the latest results once. A turn reads only the
révision's chapters (`with_content(course, ids)`, their progress, a chapter of the scope missing
from the answer reading as deleted, so the révision closes `content_changed`), and both sets of
results — every révision's and this one's — in one query.

## What the model reads

`TutorService.build_revision_input(subject, entries, ctx)` (the scope is `ctx.scope`) →
`prompt_service.build_revision`, in the order every mode keeps:

1. The developer message with the cache breakpoint: `tutor.<lang>.md` and the subject prompt,
   unchanged; at `<!-- COURSE_PACK -->` the chosen packs in course order, each under a one-line header
   naming its number (its position in the course) and title (« # Chapitre 2 — Statistique descriptive
   à une variable », « # Chapter 2 — … », « # Hoofdstuk 2 — … »), so Célestin can say where a notion
   lives (`curriculum_render.revision_packs`); at `<!-- CURRICULUM -->` one read-only overview per
   chapter, its number, title and sections with id, kind, title and goal, naming no tool
   (`revision_overview`); the révision's two mode files at `<!-- MODE -->` and `<!-- MODE_OPENING -->`.
2. The declarations: `display_board`, `clear_board`, `record_result`.
3. The stored révision, then the learner's message (`history.to_provider_input`, trimmed by
   `HISTORY_TOKEN_BUDGET`; no brief to keep).
4. The trailing state message (`revision_state`): the date and time; per chosen chapter its done,
   skipped (« passées, jamais travaillées avec toi ») and never-done sections (an active section that
   is not done counts as never done); the latest self-assessment per section with its date, from
   every révision of the course at the current content versions; this révision's tally.

The French rendering is the reference (`modes/revision.fr.md` follows the spec's text, with « ton
élève » for the student throughout); the English and Dutch files say the same in their register, with
the words `solid` / `shaky` / `to review` and `gekend` / `wankel` / `te herhalen`. What the model
reads takes the course language only: `tests/integration/test_revision_input_wall.py` proves a
French, an English and a Dutch account on the same course hand the provider identical input, and
three course languages three different ones. The parcours and discussion renderings did not move
(their pins pass unchanged).

### Cost per selection

The prefix depends on the selection only, so a selection is one cached prefix: the first turn of a
large selection is a large uncached read (the accepted cost of D2), the next ones are cached. The
fixture révision (sequences and statistics, two chapters, about 14 500 characters of packs) renders a
33 000-character developer message in French. The pins are `tests/fixtures/render/system_text_sha_revision.txt`,
`system_text_sha_en_revision.txt` and `system_text_sha_nl_revision.txt` (`tests/unit/test_revision_rendering.py`,
written on first run like the English and Dutch ones: delete one and rerun after an intended change).
`scripts/smoke.py` runs two turns in the révision too, on its own fixtures — the fixture révision of
the course language, read as mathematics (`REVISION_SUBJECT`) whatever `--chapter-dir` and
`--subject` the other modes run on, and loaded before the first paid call — prints each mode's
verdict as soon as its second turn ends, and fails on a cache miss.

### The turn context

`TurnContext` was one chapter's; a révision's context (`deps.revision_context`) has no `curriculum`, an
empty `progress` nobody reads, `chapter_id` None, and instead:

- `revision`: the `RevisionScope` — the chosen chapters (`RevisionChapter`: number, id, title,
  version, pack, curriculum, progress, read only) and what was noted before;
- `noted`: what this révision noted so far, latest per `(chapter, section)`; replaced, never mutated,
  by `ctx.note`, so a second call in the same turn sees the new tally. That is all `note` does: there
  is no results store on the context, the route writes the turn's results with its transcript (D6);
- `pack`: every chosen pack joined, so the board's « a definition must quote the pack » rule and the
  plots' `pack_function` read the chosen packs (a definition may quote any of them, and only them).

A context checks itself when it is built (`__post_init__`): a parcours or discussion context has its
chapter's curriculum and no scope, a révision's has its scope and no curriculum, so a mis-built one
fails where it is built, never inside a tool. Code reads the two through `ctx.chapter_path` (the
section tools, `build_input`, the voice session) and `ctx.scope` (`record_result`,
`build_revision_input`), which never answer None.

`registry.replay_output` replays a tool the turn's mode does not offer as a bare success, so a section
tool's replay (which reads a chapter's path) can never run on a révision's context.

## The tool

`record_result(chapter, section_id, outcome)` (`app/services/tools/result.py`), strict, révision only,
declared after every other tool so their declarations keep their bytes:

- `chapter`: the chapter's number as the prompt shows it (1–999);
- `section_id`: a section of that chapter's path (1–40 characters);
- `outcome`: `solid` (acquis), `shaky` (fragile) or `todo` (à revoir).

Refused, as a tool error in the course language: a chapter not in this révision (« Le chapitre 3 ne
fait pas partie de cette révision. Chapitres de la révision : 1, 2. »), a section not in that chapter
(the message lists the chapter's ids); invalid arguments as every tool's are. The tool writes
nothing: it notes in the turn's memory, and the turn's end writes the result with its stored call
(D6). The latest result per section counts,
within a révision (the tally) and across them (the state message, the page).

What it answers is this révision's tally, one line from the counts alone: « Bilan noté. Cette
révision : 1 acquis, 2 fragile(s), 0 à revoir (3 section(s) notée(s)). »

- **Event** `revision.result`: `{chapter_id, section_id, outcome, marker}`. The marker is
  `marker.revision_result.<outcome>` in the reader's interface language: « noté : fragile · 2. Les
  suites arithmétiques », « noted: shaky · … », « genoteerd: wankel · … » — the student sees
  everything recorded about them. The event model also holds the call's `chapter` number and the
  `tally` it answered, excluded from the wire, so the stored entry can record them.
- **Stored entry**: `{kind: "tool", name: "record_result", arguments: {chapter, section_id, outcome},
  ok, error, chapter_id, tally}`. `chapter_id` and `tally` are `ToolEntry` fields allowed on this tool
  only and left out of every other entry, whose stored bytes do not change.
- **Replay** (`replay_record`): the tally the entry recorded, so a later turn reads exactly what the
  call answered live, whatever was noted since (spec 019's review found the bug of recomputing from
  the state now in `skip_section`; this one cannot have it). Tested byte for byte after later results.
- **Shown** (`shown_record`): when the révision is read back, the marker (the section's label in the
  chapter's current path, its id if it is gone) and the wire fields `chapter_id`, `section_id`,
  `outcome`, beside `arguments`.

## Routes

All three require the signed-in student who owns the course (`owned_course`: `404`, never `403`).

| Route | Body | Answer |
|---|---|---|
| `GET /api/courses/{c}/revision` | — | `{revision, chapters, results}`; `Cache-Control: no-store`; a pure read apart from the lazy `content_changed` close |
| `POST /api/courses/{c}/revision` | `{chapter_ids}` | `201 {revision, chapters, results}`, the GET's body with the new révision, built from the chapters the start read; closes the live one as `replaced` |
| `POST /api/revision/turn` | `{course_id, revision_id, message}` | SSE: the same events plus `revision.result`; `AiReady` (`503 ai_not_configured` without a provider) |

```jsonc
// GET
{ "revision": null | { "id": "…", "chapter_ids": ["…"],          // course order
                       "entries": [StoredEntry…], "entry_count": 12, "created_at": "…" },
  "chapters": [ { "id": "…", "position": 2, "title": "…" | null,
                  "ready": true,            // has content that reads; `sections` is [] otherwise
                  "section_count": 9, "done_count": 4, "skipped_count": 1,
                  "sections": [ { "id": "…", "index": 1, "kind": "teach", "title": "…",
                                  "state": "done" | "skipped" | "todo" } ] } ],   // every chapter, course order
  "results": [ { "chapter_id": "…", "section_id": "…", "outcome": "shaky", "at": "…" } ] }
```

A section's beats, exercise pools, goal and `done_when` never cross this wire (a test sweeps the body).

Failures:

| When | Answer |
|---|---|
| `chapter_ids` empty | `422 revision_no_chapter` |
| a chapter not in the course (another course's, another student's, unknown) | `404 not_found` |
| a chosen chapter without content | `409 chapter_not_ready` |
| the chosen packs over `REVISION_MAX_PACK_CHARS` | `422 revision_too_large` (nothing is replaced) |
| past `REVISION_SESSIONS_PER_DAY` | `429 revision_quota` |
| a turn naming an unknown révision, another student's, another course's, or a discussion | `404` |
| a closed révision (replaced, capped, a chapter changed or deleted) | `409 conversation_closed`, worded for a révision |
| `message: null` on a révision that holds something | `422 empty_conversation_expected` (« Cette révision a déjà commencé. ») |
| a second tab's turn stored first | `409 conversation_busy` (in-stream `error` once the stream is open) |

The codes are the discussion's where the wire names them; the messages are the révision's own
(`revision_closed.<reason>`, `revision_full`, `revision_busy`, `revision_started`), in French, English
and Dutch.

## Limits

| Setting | Default | |
|---|---|---|
| `REVISION_MAX_PACK_CHARS` | 120 000 | characters of chosen packs |
| `REVISION_SESSIONS_PER_DAY` | 10 | révisions started per student in 24 hours (discussions count apart) |
| `DISCUSSION_MAX_ENTRIES`, `DISCUSSION_MAX_CHARS` | 400, 200 000 | the caps, shared: the append that crosses one closes the row `capped` |

## Log lines and measuring

`revision_started` (révision, user, course, chapter count, pack characters), `revision_closed`
(`content_changed`), `revision_too_large`, `revision_quota`, `revision_result` (one per result written,
after its turn's append: user, course, chapter, section, outcome; the three words are the record
itself, no text), and the shared `conversation_appended` / `conversation_append_failed` (a failed
append loses the turn's results with its entries). `turn_complete` carries `mode`
(`revision`) and `course_id`, with `chapter_id` null, so cost, rounds and `cached_tokens` are readable
per mode. The usage ledger records each round as `role tutor`, `feature revision_turn`, the course and
no chapter (`tests/integration/test_revision_ledger.py` also sweeps rows, results, logs and the admin's
answers for content).

`scripts/probe.py --revision [--language en|nl] [--dry-run]` runs four probes on the fixture révision
of the course language: the opening; « donne-moi juste la réponse » while a question is open (the
answer `62` must not appear); « ok, question suivante » after a settled question (no `record_result`
may run: the student gave no self-assessment); and a request to open a section (the answer must send
to the parcours). It writes `probe-transcript-revision[-en|-nl].md`; `--dry-run` is free.

## The interface

A révision has its own page, `/courses/$courseId/revision` (`routes/_auth/courses/$courseId/revision.tsx`). It reads the course view for the name, the subject and the language, and `GET /api/courses/{c}/revision` (`revisionQuery` in `lib/tutor/revision.ts`). The route's loader reads the course only; the révision is read by the panel, once per mount (with its loading state), like a discussion's conversation: that read also closes a changed révision, and a prefetch nobody held (`gcTime: 0`) could be dropped before the panel subscribed and read a second time (a test counts the reads on page load). The live transcript belongs to the session hook from then on. Two doors lead there. The course page has « Réviser », a link once one chapter is ready and a disabled button before. The chapter bar's mode switch has « Révision » beside « Parcours » and « Discussion », in the lesson and in the discussion, on a phone as a third segment. It is always a link, never a mode switched in place, because the révision belongs to the course; it carries `?chapter=<id>`.

**The chooser.** It shows when there is no live révision, or after « Nouvelle révision ». It lists every chapter of the course in order (`components/celestin/revision/revision-chooser.tsx`). A ready chapter has a checkbox and its counts, written as on the course page (« 3 faites sur 9 · 2 passées », or « 9 sections » before any work). A chapter that is not ready is listed, disabled, as « pas encore prêt ». The first selection is `preselected`: only the `?chapter` chapter when it is ready; otherwise the ready chapters with any done or skipped section; otherwise every ready chapter. « Commencer la révision » posts the ticked chapters in course order and is disabled with nothing ticked; the server answers with the body of the `GET` (the new révision, the chapters, the results the closed one noted), which `startRevision` returns and the panel sets as the query's data, reading nothing again. A refusal from the server (`revision_too_large`, `revision_no_chapter`, `chapter_not_ready`, `revision_quota`) shows the server's message above the list, and the selection stays as it was. When the last read had a live révision, « Revenir à la révision en cours » goes back to it without starting anything, by reading `GET …/revision` again (a loading line meanwhile) and mounting the révision from that answer: the cached read is the page load's, without the turns made since (and empty for a révision started on this page, which would open a second time), and the server may have closed it. When the answer has no live révision, the chooser stays, without the way back.

**The live révision.** It is a discussion's screen (`conversation-screen.tsx`, shared with `discussion-panel.tsx`): the tutor column and the board, no strip, no map, no page-turn button. The stored entries are folded back through `sessionFromEntries`, so a restored révision shows its transcript and board and does not open again; an empty one asks Célestin to speak first (`message: null`). The session runs on `revisionTransport`, which posts `{course_id, revision_id, message}` to `/api/revision/turn`: `useTutorSession`'s transport-scoped shape (a discussion's too), which has no chapter, no stop report and no `resetProgress`; only the parcours shape names a chapter and can reset it.

There is no voice (D5). The voice hook is not mounted, and the tutor column, given no `voice`, draws no telephone. Dictation and the photo of written work stay, because both are course-scoped.

Three quick replies sit in a row under the composer: « Acquis », « Fragile », « À revoir ». Their labels are interface text. Each sends the learner sentence `assess(outcome)` from `lib/tutor/prompts.ts` in the course's language (« Pour moi, c'est fragile. », "I'd say it's shaky.", "Voor mij is dat wankel."), and all three are disabled while a turn streams.

The tutor header holds « Bilan » and « Nouvelle révision ». The latter confirms first, saying the current révision will be closed and the results kept, then returns to the chooser; the POST that closes the old révision (`replaced`) happens only when the new one starts. A turn refused with `409 conversation_closed` (a chapter's content changed, say) shows the server's message in a banner with « Nouvelle révision » (« Cette révision est close. » when the server gave no words); the banner is looked for only once a turn has failed, walking back to the transcript's last error.

**The record, live.** The SSE event `revision.result` (`{chapter_id, section_id, outcome, marker}`) goes through the shared reducer. It appends the server's marker to the transcript, so the student sees everything recorded about them, and adds the result to the session's `results`. A stored `record_result` entry carries the same three fields beside the model's own `arguments`, and `sessionFromEntries` replays it through the same reducer, so a restored révision and a live one show the same transcript and board; the restored session's `results` start empty, since the stored ones are in the server's read, and hold only what is noted live.

**The « Bilan ».** A sheet (`revision-bilan.tsx`), opening from the right on a computer and from the bottom on a phone. A first line says these are the student's own assessments. Then, per chapter of the révision (number, title in the course's language), each section shows:

- its number and kind badge (`SectionLabel`) and its title;
- its latest self-assessment as a chip (acquis green, fragile amber, à revoir red, always with the word) and « noté le <date> », or « pas encore testée »;
- where its path stands when that helps: « passée » for a skipped section, « pas encore faite » for one never done;
- a link to the chapter's parcours and, once the section is done, a link to its cahier at `…/notebook#<section_id>`.

The latest result per section is `latestResults`: the server's `results` with the session's `results` (what was noted on this page since) laid over it, dated today. A result therefore shows the moment Célestin records it, and the sheet never recomputes or interprets one.

Known gap, shared with the section markers of the parcours: a transcript marker is interface-language text without a `lang` attribute, and « noté : fragile · 2. Titre » embeds the section's title, which is in the course's language.

Checked in a browser against the real model on 15 November 2026 (the seeded one-chapter course, a scratch database, two sections skipped beforehand): « Réviser » on the course page, the chooser, the opening (Célestin says what was skipped and never done and offers three ways to go, no card); « teste d'abord les sections passées » (an exercise on the board, a variant of the course's); a wrong answer (no result given away, a question back); the right answer (no verdict: the course's wording on the board, then « acquis, fragile ou à revoir ? »); the « Fragile » quick reply (`record_result`, the marker « noté : fragile · 1. Suites numériques », a new variant straight away); the « Bilan » (the result with its date, the other sections « pas encore testée », « passée » where skipped); a reload (transcript, board and markers back, no second opening). Not checked: several chapters at once, the English and Dutch prompts, the cached prefix (`scripts/smoke.py`).

## Manual checklist

1. On a course with two ready chapters, « Réviser »: the chooser lists the ready chapters; start with
   both. Célestin greets, says in one sentence what is covered and what the record shows, offers two
   or three ways to go, and shows no card.
2. Answer a question, ask for the course's wording, say « Pour moi, c'est fragile. »: a
   `revision.result` marker « noté : fragile · … » appears; the « Bilan » lists it with its date.
3. « Donne-moi juste la réponse » with a question open: refused, with a question or a hint.
4. « Ouvre la section sur les quartiles »: Célestin says it is worked in the parcours, opens nothing.
5. Reload: the révision and the board are back.
6. Edit a chosen chapter's pack: the révision is closed; a new one starts from the chooser, and the
   results of the old content are gone from the « Bilan ».
7. `select count(*) from progress` and its rows are unchanged by all of it; `select * from
   revision_results` holds the sections and words noted, nothing else.
