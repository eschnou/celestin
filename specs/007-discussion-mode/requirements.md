# 007 — Discussion mode: free conversation about a chapter

## 1. Introduction

Today a ready chapter offers one door: « Commencer » / « Reprendre » the parcours, the locked path of sections. That door is the right one for learning the chapter, and the wrong one for the student who has a single question, who wants to go back over a notion the evening before the test, or who has already finished the chapter. Those students leave and open a general chatbot that knows nothing about their teacher's course.

This epic adds **Discussion**, the second of the brief's three modes (§6.1, §6.5): a free conversation about one chapter, with the whiteboard, without a path. Célestin keeps the board and the pack; he loses the section tools, so nothing said in a discussion can move the student's progress. The conversation is kept on the server, so reloading the page does not lose it — the difference from the parcours, where the progress record carried the state and the transcript was disposable.

Vocabulary:

- **Mode** — how Célestin works on a chapter. `parcours` (specs 002–006) and `discussion` (this epic). `révision` (brief §6.6) is a later spec and is not opened here.
- **Parcours** — the existing mode: the locked path of `teach` / `practise` / `synthesis` sections, the section tools, the progress record.
- **Discussion** — this mode: one chapter, no path, no progress write.
- **Conversation** — one stored discussion on one chapter for one student: its transcript, the entries Célestin and the student produced. At most one is live per (student, chapter).
- **Brought statement** (« énoncé apporté ») — an exercise the student puts in front of Célestin that does not come from the pack: their homework, a sheet from class, a past test.

Scope:

- A Discussion mode on any ready chapter, reachable from the course page and from inside the lesson.
- The board tools; no section tool, no progress write, in either channel.
- A discussion prompt layer, written by us, next to the existing tutor and subject layers.
- Conversations stored server-side, restored on reopening, with « Nouvelle conversation ».
- Voice in Discussion, on the existing Realtime machinery.
- The answer-withholding rule extended to brought statements, and measured per mode.

Out of scope:

- **Révision mode** (brief §6.6): testing and rehearsal, with its own state and report. Discussion must not grow into it; NFR 4.1.6 keeps the door open.
- A history screen: past conversations are not listed, searched or reopened. The store is shaped so a later listing is an endpoint, not a migration (NFR 4.1.6).
- A conversation spanning several chapters or a whole course.
- Moving the parcours onto stored conversations (open question 2); the parcours keeps posting its transcript.
- Reading photographed handwritten work (brief §6.4 « Read their work »), in Discussion as in the parcours.
- A mechanical checker: Discussion issues no correctness verdict, exactly as the parcours does not.
- Parent visibility of conversations.

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §6.5 Discussion mode | Delivered: free conversation about the chapter, answered from the pack, with the whiteboard, and no solving of homework on the student's behalf. |
| §2 Engagement is the binding constraint (Oreopoulos & Low) | The parcours is a heavy first step. Discussion is the light one: a question, the evening before the test, on a finished chapter. |
| §4 Job: "I just want to ask questions about this chapter" | The row that reads « Ask a chatbot that ignores the course » today. |
| §5.1 It teaches the student's course | The pack stays Célestin's only source in Discussion; a brought statement is material to work on, never a licence to use a method the course does not contain (R3.3). |
| §5.3 It withholds answers by construction | Extended to the mode where the pressure is highest. The tools that could leak are the board tools, unchanged; the new rule is about brought statements (R3.2). |
| §5.6 It is a lesson, not a chat | Discussion is still led: Célestin opens, proposes, writes on the board. What it drops is the canvas, not the pedagogy. Its entry stays secondary to the parcours (R1.1, NFR 4.5.5). |
| §5.5 It remembers | The conversation survives a reload, which the parcours transcript never did. |
| §8 Privacy | A conversation is private to its student, cascades with the chapter and the account, and never reaches a log. |
| §8 Pasted material is data, not instructions | Extended: a stored conversation, and a brought statement inside it, are data (R8.5). |
| §9 Trust: answer-leak rate below 1% | Measured per mode from the first day (R9.2, R9.4). |
| §10 Risk: tutor leaks answers under pressure | Discussion is where « juste dis-moi » arrives. R3 is the answer, and the probe script is how we know. |

Deviations from the brief:

1. **Phase order.** §11 puts Discussion in Phase B, after Phase A′ (more subjects). This epic moves it ahead of A′: it is less work than a subject, and it serves the metric the brief names as primary (§9, sessions per week) more directly.
2. **§6.5 says "The student talks with the tutor about the chapter … no solving of homework or test exercises on the student's behalf."** This epic makes that concrete and slightly wider: a brought statement is explicitly *allowed as a subject of work* (R3.2), which the brief's wording left open. §6.5 should be updated to say so.
3. **§6.1's mode table** lists Discussion as « Later »; it becomes built for every ready chapter.

## 3. Requirements

### R1 — Opening a discussion

**As a** student, **I want** to talk to Célestin about a chapter without starting its parcours, **so that** one question does not cost me a whole lesson.

Acceptance criteria:

1. A ready chapter on the course page offers a secondary action « Discuter » beside its primary action; the primary action stays the parcours (« Commencer » / « Reprendre » / « Continuer » / « Revoir »), unchanged in label and position.
2. Discussion is available whatever the chapter's state: not started, in progress, or done.
3. From inside the lesson, the student can open a discussion on the same chapter and come back to the lesson. The lesson's session — its transcript, its board, its place in the path — survives the round trip. (The parcours transcript lives in memory only; losing it because the student asked a question would be a regression.)
4. A chapter without content answers `409 chapter_not_ready`, and a chapter the student does not own `404`, exactly as the lesson does. No new way in exists around `owned_chapter`.
5. A discussion is about one chapter. Nothing in the interface offers a conversation across chapters or about a whole course.
6. Leaving a discussion needs no confirmation and loses nothing (R4).

### R2 — What Célestin does in a discussion

**As a** student, **I want** Célestin to explain, show and question about my chapter, **so that** a discussion is worth more than a chat window.

Acceptance criteria:

1. Célestin has the board: `display_board` with the six card kinds and `clear_board`, with the same typed blocks, the same LaTeX rules and the same « nothing becomes HTML » rule as the parcours. What he teaches goes on the board, not into the conversation.
2. **The section tools are not declared.** `start_section`, `complete_section` and `propose_next_step` are absent from the tool set a discussion turn — text or voice — receives. Célestin cannot call them, so no discussion turn can write a progress row (R6.1). There is no « Étape suivante » button: there is no page to turn.
3. The chapter's pack is Célestin's only source, as in the parcours: definitions, formulas, notation, vocabulary and methods come from it and nothing is added. « Points à vérifier » are not taught, not cited and not set as exercises; asked about one, Célestin says it is to be checked with the teacher.
4. Célestin reads the path and the student's stored progress, **read-only**, and uses them to situate the conversation and to point: « ça, c'est la section 4, tu ne l'as pas encore faite ». He cannot open or close a section, and says that the parcours is where that happens. The trailing turn message keeps carrying the date, the time and the path state, as in the parcours.
5. On an empty conversation Célestin opens by himself: a greeting, one sentence on where the student is in the chapter, and two or three concrete openings drawn from the pack and the progress. The student never faces a blank page (brief §6.7).
6. He leads the exchange as in the parcours: one idea at a time, questions rather than statements when the student is stuck, a full explanation for a notion met for the first time, no new card in the same turn as a question.
7. Language, tone and notation are unchanged: French, tutoiement, gender-neutral, the course's own notation, units and vocabulary.
8. Off-topic is redirected in one friendly sentence, on the subject prompt's existing definition. Another chapter is off-topic for this conversation: Célestin says so and names where to go.
9. No correctness verdict from impression: with no checker, Célestin does not declare « c'est juste » or « c'est faux »; he reacts to the reasoning and has the student verify. Unchanged from the parcours.

### R3 — Exercises, and the work the student brings

**As a** student, **I want** to work on the exercise I actually have in front of me, **so that** I do not have to pretend my homework does not exist — **and as** the product, **I want** that never to become a solving service.

Acceptance criteria:

1. Célestin may set an exercise in a discussion, as a variant of the pack's sample exercises, on request or to check something. While that exercise is open the withholding rule applies unchanged: he may question, orient and hint; he may not state the result, write it on the board, or let it be reached by elimination.
2. The student may bring their own statement. Célestin takes it as **a base of discussion, never as a request for a solution**: he asks what the statement gives, what the student has tried, which notion of the chapter it turns on, and works from there. He does not produce the answer or a complete solution, in the conversation or on the board, however the request is phrased.
3. A brought statement is **material, not a source**. The formulas, methods, notation and vocabulary Célestin uses on it come from the pack only. If it needs something the chapter does not contain, he says so in one sentence and says it is beyond what this chapter covers.
4. Insistence is met as in the parcours — « dis-moi juste la réponse », « c'est pour demain », « j'en ai marre »: Célestin holds, kindly, names the frustration if it helps, and offers a smaller question, a hint or a return to the formula. He does not give way.
5. A brought statement from another subject, or from a chapter this course does not contain, is off-topic (R2.8): Célestin redirects rather than working on it.
6. These rules hold identically in voice (R7).

### R4 — The conversation is kept

**As a** student, **I want** to find my discussion where I left it, **so that** closing a tab does not throw away what we said.

Acceptance criteria:

1. A discussion turn is stored on the server as it happens: the student's message, Célestin's text, and his tool calls, in the transcript entry shapes that already exist (`learner`, `tutor`, `tool`).
2. Reopening Discussion on a chapter restores the live conversation: the transcript as it was, and the board showing the last card Célestin displayed, with that conversation's earlier cards behind it.
3. There is at most one live conversation per (student, chapter). Opening Discussion continues it; the student is never asked to pick one.
4. **The stored conversation is the source of truth for what was said.** A turn request names the conversation instead of carrying the transcript; the client cannot rewrite, extend or replay a stored conversation's history. (The parcours keeps its posted-transcript shape; see open question 2.)
5. A conversation too long for the model is trimmed for the model the way a parcours transcript is — whole turns, oldest first, the most recent always kept — while the stored conversation keeps everything up to the cap in R4.6.
6. A conversation has a cap. Reaching it, Célestin says so in one sentence and the student is invited to start a new one; the conversation stays readable and is not continued.
7. Two turns cannot interleave on one conversation: a turn requested while another is in flight on the same conversation is refused with a French message, and the stored transcript is never left interleaved.

### R5 — « Nouvelle conversation »

**As a** student, **I want** to wipe the slate and start again, **so that** a new question is not buried under an old thread.

Acceptance criteria:

1. The Discussion view offers « Nouvelle conversation ». Because the current one becomes unreachable, it asks for confirmation first.
2. It starts an empty conversation on the same chapter: empty board, and Célestin's opening turn as in R2.5.
3. The previous conversation is no longer shown or continued. There is no history screen in this epic: the student sees the live conversation and nothing else.
4. Progress, the path and the course page are untouched by starting a new conversation.
5. Starting conversations is bounded per student, so the action is not an unbounded way to spend model calls (NFR 4.3.5).

### R6 — A discussion never moves the parcours

**As a** student, **I want** my progress to mean what it says, **so that** a section is done only when I actually did it.

Acceptance criteria:

1. No discussion turn writes the `progress` row, in either channel. This follows from R2.2 and is asserted by a test, not by prompt text.
2. A chapter's `done_count`, `state`, `last` and « Reprendre » on the course page are unaffected by any discussion, however long.
3. The Discussion view does not offer the path's actions: no « Commencer », no « Revoir », no « Recommencer le chapitre ». If it shows where the student is, it shows it read-only. The way into a section is the lesson, and the view offers a link back to it.
4. Resetting a chapter's progress from the lesson does not touch its conversations, and a conversation does not touch progress. The two records are independent; only a content change ends a conversation (R8.3).

### R7 — Voice in a discussion

**As a** student, **I want** to talk to Célestin in a discussion as I do in a lesson, **so that** the mode is not a downgrade.

Acceptance criteria:

1. Voice works in Discussion through the existing `/api/voice/*` routes, the same mic and the same bridge, gated the same way: `VOICE_ENABLED`, the per-user mint limit, the session cap and the idle cut-off.
2. The Realtime session is built from the discussion prompt layer and the discussion tool set. No section tool is declared to it either; the text and Realtime declarations for a mode keep agreeing, as a test already enforces for the parcours.
3. The session is seeded from the stored conversation, trimmed to the voice budget. Spoken turns are stored like typed ones, so stopping the call and typing continues the same conversation, and a reload keeps both.
4. R2 and R3 hold identically in voice; the probe of R9.2 covers the spoken phrasing as `voice_probe` does today.

### R8 — Privacy, retention, and what happens when the chapter changes

**As a** student, **I want** my conversations to be mine and to disappear with the chapter, **so that** talking freely costs me nothing.

Acceptance criteria:

1. A conversation belongs to one student and one chapter, and is readable only by that student. Nothing is shared between students; no parent view.
2. Conversations carry foreign keys to the student and the chapter with `ON DELETE CASCADE`, so they go with the chapter, with the course, and with the account when account deletion exists.
3. A change to the chapter's content — an editor save or an adopted authoring run, which bumps `content_version` and deletes progress — **ends the live conversation**: it is not continued, because the pack it was held against no longer exists. The next opening starts a new one, and the view says so in one sentence.
4. No conversation content reaches a log or a client-visible error. Log lines carry ids, counts and timings, as everywhere else.
5. A stored conversation, and any statement the student brought into it, is data and never instructions. Nothing inside one can change Célestin's rules.

### R9 — Measuring the mode

**As the** operator, **I want** to know whether Discussion leaks answers, **so that** the mode does not quietly undo the product's main claim.

Acceptance criteria:

1. Each turn logs its mode alongside the existing `turn_complete` fields (user, chapter, tokens, cached tokens, rounds), so cost and volume are readable per mode.
2. `scripts/probe.py` gains a discussion set, run against the real model as today: a brought homework statement, « donne-moi juste la réponse » with an exercise open, a request for a method the pack does not contain, an off-topic request, and a request to close or start a section. Its transcript is read against the same checklist.
3. The brief's targets are reported per mode: answer-leak rate below 1 % of tutor messages, and zero formulas or methods in transcripts that are not in the pack.
4. The count of conversations and of discussion turns per student is available for the engagement question the mode exists to answer (brief §9).

## 4. Non-functional requirements

### 4.1 Architecture

1. **One turn pipeline.** Discussion reuses `TutorService`, the SSE contract, `tool_events.event_of` and the history mapping. It is not a second loop. The mode selects a prompt layer and a tool set; everything else is shared.
2. **No new SSE event.** The event set stays the nine of the two-sided contract; a discussion turn simply never emits `section.start`, `section.done` or `step.ready`. Adding a mode must not change `frontend/src/lib/tutor/types.ts`.
3. **The tool set becomes a function of the mode.** `registry.declarations()` and `realtime_declarations()` are module-level constants built once and byte-stable by construction; the per-mode lists must keep both properties, keep their fixed order, and keep the realtime list equal to the text list minus `strict`.
4. **The discussion instructions are a prompt file we write**, under `prompts/`, read through `PromptLibrary` with the same startup check and the same `/api/health` reporting as the others. The parts `tutor.fr.md` already states once — the source rule, the way of speaking, the way of teaching, the board, what Célestin never does — are not duplicated into it.
5. **Conversations are a table** with foreign keys to user and chapter, one Alembic migration following the `NNNN_slug` convention with a working `downgrade`, and a repository in `app/db/repositories.py` in the existing synchronous one-session-per-call style, called through `run_in_threadpool`.
6. **Not blocking Révision** (§1 out of scope) **or a history screen.** The mode is a value, not a boolean, so a third mode is a value and a prompt file. The conversation store is keyed by student and chapter with a creation time, so listing past conversations later is an endpoint and a screen, not a migration.
7. **Every new route declares its roles** with `require_roles(...)` and checks ownership through `owned_chapter` / `lesson_chapter` (404, never 403); mutating routes pass the same-origin middleware. The existing route-guard and layering tests must keep passing untouched.
8. **The frontend reuses the session machinery**: `useTutorSession` and its reducer, the whiteboard, the transcript entries. The Discussion view differs in what it mounts around them and in how a turn is started, not in how an event is applied. New routes follow the file-based convention under `_auth`.

### 4.2 Performance

1. **The pack must not be billed uncached on every discussion turn.** The design either shares one cached prefix between the two modes or accepts a second prefix per chapter; either way it states the choice, records the measured `cached_tokens` of a discussion turn, and `scripts/smoke.py` fails on a cache miss in Discussion as it does in Parcours. (Reference point: the chapter 1 prefix is ~13 500 tokens.)
2. Reopening a discussion restores the conversation in one request.
3. Storing a turn must not delay its first byte: the student's message is recorded before the model call, the reply as it completes, without a synchronous write between rounds that the learner would feel.

### 4.3 Security and privacy

1. Owner-scoped like everything else: a conversation belonging to another student, or to a chapter of another course, answers `404`.
2. Conversation ids are uuid4 hex, validated by the same `Id` pattern as course and chapter ids.
3. Conversation text never appears in a log, in a metric, or in a client-visible error message.
4. Stored conversation content reaches the model as transcript, never as instruction, and sits behind the cache breakpoint with the rest of the transcript.
5. Discussion is bounded per student — conversations started and turns taken — reusing the existing rate-limit and quota patterns, so the mode is not an open model-spend surface.

### 4.4 Reliability and quality

1. **A failed turn leaves the conversation consistent.** A stream that dies mid-turn must not leave a half-finished tutor message that is later replayed to the model as a finished one; the stored conversation is either advanced by a complete turn or left as it was. (In the parcours the browser's `retry()` does this; here the server must.)
2. Offline tests, driven by the scripted fake provider as today: a golden SSE transcript for a discussion turn; an assertion that the discussion declarations contain no section tool, in both the text and realtime lists; an assertion that no discussion turn writes a progress row; repository tests for create, append, cap, the content-change rule and the cascades; a migration test; and the existing prefix byte-stability test extended to the new rendering.
3. Frontend tests follow the existing shape: the reducer and any pure helper tested outside React, the view mounted through the route harness.
4. The manual checklists in `documentation/` gain the discussion path, including the round trip from the lesson (R1.3) and the reload (R4.2).

### 4.5 Usability

1. French copy throughout, tutoiement, following the existing vocabulary: « Discussion », « Nouvelle conversation ».
2. The view works at 400 px wide and stacks board-first below `lg`, as the lesson does; keyboard and screen-reader accessible, the new actions being real buttons and links with labels.
3. A restored conversation appears at once, scrolled to the end, without a flash of an empty board.
4. When a conversation has been ended by a content change (R8.3) or by the cap (R4.6), the student reads one plain sentence saying why, not an error.
5. The view says in one line what Discussion is for, and that the parcours is where progress is made — so the lighter door does not quietly become the default way to work.

## 5. Open questions for the design

1. **Where the mode layer sits relative to the cache breakpoint.** A second developer-message prefix per chapter is the simple reading (one uncached ~13 500-token read per mode switch); putting the mode block in the trailing message keeps one shared prefix but bills the block every turn. Break-even is in the order of twenty turns. Decide on a measurement, and record it.
2. **The turn route.** `POST /api/chat` gaining a mode and a conversation id, against a route of its own for Discussion — and whether the parcours should later move to server-held conversations too, which would remove the two shapes.
3. **How Discussion is presented from inside the lesson** (R1.3), given that the lesson's transcript is in memory only: a panel over the board, a second column, or a route that keeps the lesson mounted.
4. **The cap of R4.6**: entries, characters or turns, what value, and what Célestin says when it is reached.
5. **The opening turn of a new conversation** (R2.5): a model call, or a fixed French greeting with openings computed from the path — cheaper, and less alive.
6. **The trailing state message.** It is titled « État du parcours » and shaped for the path. In Discussion it is read-only context; whether it keeps its wording, or gets a discussion variant that says a section cannot be opened from here.
7. **Whether « Points à vérifier » should be surfaced to the student** in the Discussion view, where asking about an uncertain passage is more likely than in a lesson.
