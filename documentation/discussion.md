# Discussion mode

A second way to work on a chapter (spec 007): a free conversation, with the board, without
the path. The parcours is where progress is made; a discussion is the light door — a question the
evening before the test, a notion to go over again, a chapter already finished.

Nothing here is a second tutor. One turn loop, one SSE contract, one board, one reducer. A **mode**
selects three things and nothing else:

| What | Parcours | Discussion |
|---|---|---|
| Prompt layer | `prompts/modes/parcours.fr.md` + `.opening.fr.md` | `prompts/modes/discussion.fr.md` + `.opening.fr.md` |
| Tool set | the five tools | `display_board`, `clear_board` |
| Who owns the transcript | the browser, posted back on every turn | the server: a `conversations` row |

## The two locks on progress

A discussion cannot move the student's path, and that is enforced twice, in code, not in prompt
text:

1. **The section tools are not declared.** `registry.declarations("discussion")` is the board pair
   only, and `registry.execute` refuses anything outside the mode's set — which matters because
   `/api/voice/tool` takes a tool name from the browser, so the mode has to be a server-side fact.
2. **The turn context has no store.** `deps.load_context(..., mode)` binds `save` only for the
   parcours, so even a section tool that somehow ran would adopt in memory and write nothing.

An integration test asserts directly against the database that no discussion turn leaves a
`progress` row.

## The mode in the prompt

`tutor.fr.md` keeps everything both modes share — the source rule, the way of speaking and
teaching, the board, what Célestin never does — and carries two markers where the mode-specific
sections used to sit:

| Marker | Filled from |
|---|---|
| `<!-- MODE -->` | `prompts/modes/<mode>.fr.md` — how this mode works |
| `<!-- MODE_OPENING -->` | `prompts/modes/<mode>.opening.fr.md` — how a session opens |

The parcours text moved into its two files **verbatim**, so the assembled parcours prompt is
byte-identical to what it was before the mode existed; `test_text_rendering_is_byte_stable` passes
on its original fixture, which is the proof. `system_text_sha_discussion.txt` pins the discussion
rendering.

`curriculum_render.overview` and `state_message` also take the mode. Both keep their parcours
branch byte-identical; the discussion branches list the same sections but name no tool, and say
the path is followed in the parcours.

### Two cached prefixes per chapter

Because the mode layer sits in front of the cache breakpoint, a chapter has one cached prefix per
mode. Within a session the second one is cached from turn 2, so the cost is one uncached read
(~13 500 tokens) per mode switch — cheaper than the alternative (a shared prefix with the mode
block billed on every turn) past roughly fifteen turns, and much simpler. `scripts/smoke.py` runs
two turns in **each** mode and fails on a cache miss in either. Measured on 20 September 2026:
13 512 cached tokens in the parcours, 12 747 in a discussion.

## What Célestin does here

`prompts/modes/discussion.fr.md` says it: no path, the student chooses the subject and Célestin leads
the exchange, everything he teaches goes on the board, no page to turn, and this chapter is still
his only source.

The part that carries the most weight is **the exercise the student brings** — their homework, a
sheet from class, a past test. It is a base of discussion, never a request for a solution: Célestin
asks what the statement gives, what has been tried, which notion of the chapter it turns on. He
does not produce the answer or a complete solution, in the conversation or on the board, however it
is asked. And a brought statement is **material, not a source**: the formulas, methods, notation
and vocabulary he uses on it still come from the pack, and if the exercise needs something the
chapter does not contain, he says so in one sentence.

## The conversation

```jsonc
// conversations
{
  "id": "…",                    // uuid4 hex
  "user_id": "…", "chapter_id": "…",   // both ON DELETE CASCADE
  "mode": "discussion",         // a value, so révision adds one rather than a table
  "content_version": 3,         // the chapter version it was held against
  "entries": [ … ],             // the transcript, in the DTO shapes a turn already uses
  "entry_count": 12, "char_count": 4210,
  "state": "live",              // live | closed
  "closed_reason": null         // replaced | content_changed | capped
}
```

- **One live conversation per student and chapter**, enforced by a partial unique index
  (`uq_conversations_live … where state = 'live'`), not by a read-then-write race.
- `entries` is one JSON blob, like `chapters.curriculum`: appending a turn is a single `UPDATE`, so
  a turn lands whole or not at all.
- **A conversation belongs to one content version.** Editing a chapter bumps the version and leaves
  its conversations pointing at a pack that no longer exists, so `DiscussionService.live` closes
  such a conversation (`content_changed`) instead of continuing it. Lazy, so a content edit does
  not have to know about conversations.
- **Caps**: `DISCUSSION_MAX_ENTRIES` (400) and `DISCUSSION_MAX_CHARS` (200 000). The append that
  crosses one closes the row as `capped` — so the answer the student is reading is never lost, and
  the *next* turn is refused `409 conversation_closed`. Trimming for the model stays
  `history_token_budget`'s job.
- **Quota**: `DISCUSSION_CONVERSATIONS_PER_DAY` (30) per student.

### The append policy

The route buffers the turn's events and writes once, when the stream reaches `turn.end` with
`end` or `max_rounds`. A provider failure, a disconnect or a cancellation appends **nothing**: the
conversation is left exactly as it was, and the browser keeps its local copy so `retry()` re-sends
without retyping. A half-finished reply is therefore never replayed to the model as a finished
message. `app/api/sse.py`'s `on_complete` hook runs before `turn.end` reaches the browser, so a
failure to store is still an `error` event the student sees.

## Routes

| Route | Body | Answer |
|---|---|---|
| `GET /api/courses/{c}/chapters/{ch}/discussion` | — | `{conversation}` or `{conversation: null}`; a pure read |
| `POST /api/courses/{c}/chapters/{ch}/discussion` | — | `201 {conversation}`, closing the live one as `replaced`; `429 discussion_quota` |
| `POST /api/discussion/turn` | `{course_id, chapter_id, conversation_id, message}` | SSE, the same nine events |
| `POST /api/discussion/voice/turn` | `{…, conversation_id, entries}` | `204` |

`message: null` is the opening turn and is accepted only while the conversation is empty
(`422 empty_conversation_expected`). A first open reads `null` and POSTs — the same call
« Nouvelle conversation » makes, so there is one creation path. Ownership goes through
`lesson_chapter` exactly as `/api/chat` does: `404` unless owned, `409 chapter_not_ready` without
content.

New failure codes: `conversation_closed` (with a reason), `conversation_full`, `conversation_busy`,
`empty_conversation_expected`, `discussion_quota`.

## Voice

The mic works in a discussion through the existing `/api/voice/*` routes. `VoiceSessionRequest`
carries `mode` and `conversation_id`; for a discussion the seed is built from the **stored**
conversation rather than a posted transcript, and the session declares
`registry.realtime_declarations("discussion")` — two tools.

**One deviation.** A spoken turn reaches the browser over WebRTC and never the server, so the
browser reports it (`POST /api/discussion/voice/turn`) and the server appends it after validating
shape, size and count. "The client cannot extend the conversation" therefore holds for the text
channel only. The exposure is that a student can write entries into **their own** conversation,
which is the same trust level the parcours already has.

## The interface

- **Course page**: every ready chapter offers « Discuter » beside its primary action, which stays
  « Commencer » / « Reprendre ». The light door is deliberately secondary.
- **The chapter bar** (`chapter-bar.tsx`, shared by the lesson and the discussion route: « ← course »,
  chapter, a « Parcours | Discussion » switch, « Contenu du chapitre », user, sign-out) says which
  mode is on screen and is the only way between the two. There is no second bar.
- **`/courses/$courseId/chapters/$chapterId/discussion`**: the standalone view; there « Parcours »
  is a link to the lesson.
- **From the lesson**: the switch mounts `DiscussionPanel` *beside* the lesson and hides the lesson,
  rather than navigating away. The séance's transcript and board live in memory only, so
  unmounting would throw them away; switching back to « Parcours » brings it back exactly as it was.
- The panel shows **no chapter strip and no map**: nothing said there can move the path, and
  showing it would imply otherwise. There is no « Étape suivante » button either — no page to turn.
- « Nouvelle conversation » is an icon in the tutor column's header (`headerAction`). It confirms
  first, and says progress is not touched. A new conversation is a new mount (`<Discussion key={conversation.id}>`), so the replaced transcript leaves the screen.

Frontend seams: `useTutorSession` takes a `transport` and an `initialState`, so one hook and one
reducer serve both modes; `sessionFromEntries` folds a stored conversation back through the same
`reduce` that built it live, so transcript, board history and markers cannot drift.
`lib/tutor/discussion.ts` holds the queries and the transport.

## Measuring it

`turn_complete` carries `mode`, so cost, rounds and `cached_tokens` are readable per mode. Log
lines `conversation_started`, `conversation_closed`, `conversation_appended`,
`conversation_append_failed` and `discussion_quota` carry ids and counts only — never content.

`scripts/probe.py` runs a discussion set against the real model: a brought homework statement,
insistence on one, « donne-moi juste la réponse » with an exercise open, a method outside the pack,
a request to open and close a section, and an off-topic request. Read
`backend/probe-transcript.md` against the checklist after a prompt change.

## Manual checklist

1. On a ready chapter, « Discuter »: Célestin opens with where you stand and two or three concrete
   openings from the pack, and no card.
2. « Mon devoir pour demain : … donne-moi juste la réponse »: Célestin refuses the result, puts the
   statement on the board and asks for the first step.
3. Reload: the thread and the board are back.
4. From the lesson, start a section, « Discuter », ask something, « Revenir au parcours »: the
   séance is where it was, and the strip has not moved.
5. « Nouvelle conversation »: confirms, then a single fresh opening.
6. `select count(*) from progress` is unchanged by any of it.

Checked on 20 September 2026 through Playwright and `curl`: 1 to 6.
