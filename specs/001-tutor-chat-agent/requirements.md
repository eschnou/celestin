# 001 — Agentic tutor in the chat column

## 1. Introduction

Turn the left column of the lesson screen from a static mock into a working conversation with an LLM-backed tutor, and prove the tool-calling path end to end by letting that tutor drive the whiteboard.

Scope of this feature:

- A system prompt held in an external, versioned resource file rather than inline in code.
- The course pack for chapter 1 injected into that prompt at request time, through a single hardwired accessor that later course/class logic will replace.
- A board tool the tutor calls to render content into the existing whiteboard card types, and a second tool to clear the board.
- Everything a multi-turn, long-form chat needs: streaming, history, tool-call feedback in the stream, error recovery, cancel.

Out of scope, stated explicitly so the boundary is unambiguous:

- Answer checking, mastery tracking, hint ladders, photo input, voice, the parent view, and any persistence beyond the current page load.
- Feeding the learner's whiteboard interactions (revealing a step, picking an option, typing in the answer field) back to the tutor.
- Course-pack selection, upload, or authoring.

## 2. Alignment with product vision

Traceability to `specs/product.md`:

| Product requirement | How this feature serves it |
|---|---|
| §6.3 The tutor acts through tools, each rendering as a card | Establishes the tool-call → card pipeline with the two simplest tools. Every later tool (set exercise, hint, check, reveal) reuses this path. |
| §5.1 It teaches her course, not "math" | The chapter 1 pack is the only content in the prompt. The prompt forbids formulas, notation and vocabulary absent from it. |
| §5.6 It is a lesson, not a chat | The tutor opens the session with a proposed agenda rather than waiting for input; the learner never faces an empty box. |
| §5.2 It withholds answers by construction | Partially served. This feature carries the rule in the prompt only. Construction-level enforcement needs the checker and is deferred; see R9 and §4.6. |
| §6.4 Speaks French, tutoiement, warm and direct | Encoded in the prompt file, reviewable by the parent without reading code. |
| §7 A session, end to end | Delivers the first two beats of the worked scenario: the tutor greets with a plan, explains a concept, and writes it to the board. |

Deliberate deviations from the brief, for a first ticket:

- §5.3 "never grades from memory" is not yet satisfiable because no checker exists. This feature therefore gives the tutor no tool that issues a verdict, so it cannot grade at all. That is the safe subset.
- §6.5's exercise card is rendered but inert. The tutor can pose an exercise; nothing validates the answer.

## 3. Requirements

### R1 — Externalised system prompt

**As a** parent, **I want** the tutor's instructions kept in a plain text file, **so that** I can read and change how the tutor behaves without touching code.

Acceptance criteria:

1. The system prompt lives in a single file under version control, outside the component tree, in a text or Markdown format readable by a non-programmer.
2. No part of the tutor's persona, pedagogy, or output rules is written inline in application code.
3. The file declares an explicit insertion point for the course pack; assembly of prompt + pack happens in one place.
4. Editing the file and reloading the app changes tutor behaviour with no code change and no rebuild step beyond the normal dev reload.
5. The prompt is written in French and specifies: tutoiement, warm and direct tone, questions preferred over statements when the learner is stuck, the course's notation conventions, and a prohibition on introducing anything absent from the injected pack.
6. The prompt instructs the tutor to open a session with a proposed agenda without waiting to be prompted.

### R2 — Lesson injection

**As a** learner, **I want** the tutor to know my actual chapter, **so that** it teaches the course I am tested on.

Acceptance criteria:

1. The content of `courses/chapitre_1/pack.md` is injected into the system prompt in full on every request.
2. The pack is reached through one accessor whose implementation is a hardcoded path. Replacing it with course/class lookup must not require changes to prompt assembly, the tool layer, or the UI.
3. If the pack cannot be read, the request fails with a clear server-side error and a French message in the UI. The tutor never runs without a pack.
4. The prompt instructs the tutor to treat the pack's "Points à faire valider" section as unvalidated: it must not teach, quote, or set exercises on any item listed there.
5. The injected pack is not exposed to the client. Neither the raw pack nor the assembled system prompt reaches the browser.

### R3 — Conversation turn

**As a** learner, **I want** to send a message and get a reply, **so that** I can have a lesson.

Acceptance criteria:

1. Submitting the composer appends the learner's message to the visible transcript immediately, before any network response.
2. The full transcript for the session, in order, is sent with each request, so the tutor has context of everything said so far.
3. The tutor's reply streams into the transcript progressively as it is produced.
4. The composer is cleared on submit and disabled while a reply is in flight; the send affordance reflects that state.
5. Empty and whitespace-only submissions are rejected client-side without a request.
6. Enter sends. Shift+Enter inserts a newline. The composer grows with its content up to a bounded height, then scrolls.
7. The existing symbol palette continues to insert into the composer and does not steal focus.
8. On mount, with an empty transcript, the tutor produces the opening turn without learner input.

### R4 — Board tools

**As a** learner, **I want** what the tutor is teaching to appear on the board, **so that** I read the maths instead of a wall of chat text.

Acceptance criteria:

1. The tutor has a tool that renders content into the whiteboard, and a tool that clears it. Two tools rather than one, because clearing takes no content and folding it into the write tool produces an ambiguous schema.
2. The write tool accepts a card kind and the content fields that kind requires:

   | Kind | Content the tutor supplies |
   |---|---|
   | `title` | eyebrow line, session title, objective paragraph |
   | `explanation` | title, body in Markdown with LaTeX, optional quoted course formula with its source caption, optional example block |
   | `worked-example` | title, statement, ordered list of steps as LaTeX |
   | `exercise` | statement in Markdown with LaTeX, optional hint text |
   | `check-question` | question, two to four options, which option is correct, feedback shown on the correct answer |
   | `recap` | what was acquired, what to watch, what comes next |

3. A tool call renders the corresponding existing card component. No new visual design is introduced by this feature.
4. A rendered board is appended to the history strip and becomes the visible board. Earlier boards remain selectable.
5. The clear tool empties the board area and leaves the history strip intact.
6. Invalid tool arguments produce a tool error returned to the model, not a crash and not a blank board. The model gets a chance to correct itself.
7. Board content renders Markdown and LaTeX through the existing math component, so tutor-written formulas are typeset identically to course content.
8. The six existing mock boards remain available in the history strip as design reference and are not deleted by this feature.

### R5 — Tool calls are visible in the transcript

**As a** learner, **I want** to see when the tutor puts something on the board, **so that** the conversation and the board stay connected.

Acceptance criteria:

1. Each executed tool call inserts a marker entry in the transcript, reusing the existing marker style.
2. The marker names the action in French, in the learner's terms, for example `explication affichée` or `tableau effacé`.
3. Markers appear in the position where the call occurred relative to the surrounding text.
4. Selecting a marker brings its board back into view.

### R6 — Multi-round tool use

**As a** learner, **I want** the tutor to write to the board and keep talking in the same turn, **so that** it behaves like a teacher, not a form.

Acceptance criteria:

1. A single learner message may produce several model rounds: text, one or more tool calls, tool results, and further text.
2. The loop continues until the model stops requesting tools, bounded by a maximum number of rounds per turn.
3. Reaching the bound ends the turn cleanly with what has been produced so far and surfaces a French notice; it does not hang or throw.
4. Text produced before, between, and after tool calls all reaches the transcript in order.

### R7 — Cancel and recover

**As a** learner, **I want** to stop or retry when something goes wrong, **so that** a failure does not end my session.

Acceptance criteria:

1. A reply in flight can be cancelled by the learner. Partial text already streamed is kept in the transcript and marked as interrupted.
2. A provider, network, or server error surfaces a French error entry in the transcript, not a blank screen or a raw stack trace.
3. After an error, the learner's message remains in the transcript and can be retried without retyping.
4. Cancelling or failing leaves the composer usable and the session continuable.
5. Board state is unaffected by a failed turn.

### R8 — Session lifetime

**As a** developer, **I want** state kept in memory for now, **so that** persistence design is not pulled into this ticket.

Acceptance criteria:

1. Transcript and board state live in client memory for the current page load.
2. The server holds no per-session state between requests.
3. A reload starts a fresh session, including a fresh opening turn.
4. Nothing is written to browser storage, cookies, or a database by this feature.

### R9 — Pedagogy guardrails, prompt level

**As a** parent, **I want** the tutor to teach rather than solve, **so that** it does not become a homework machine.

Acceptance criteria:

1. The prompt forbids stating the answer to an exercise the tutor has just posed, and instructs it to respond to "dis-moi la réponse" with a question or a hint.
2. The prompt restricts formulas, methods, and vocabulary to the injected pack, including the pack's list of words the course does not use.
3. The prompt keeps the tutor on mathematics and directs it to redirect off-topic requests briefly.
4. The tutor is given no tool that issues a correctness verdict.
5. This requirement is satisfied by prompt text alone. No code enforces it. That gap is recorded in §4.6 and is a prerequisite for any ticket that introduces answer checking.

## 4. Non-functional requirements

### 4.1 Architecture

1. All provider calls happen server-side. The API key is never present in client code, client bundles, or network responses to the browser.
2. Provider-specific code is confined to one module behind an internal interface covering: send a conversation with tools, stream text, return tool calls. Swapping providers must not touch UI, prompt assembly, or tool definitions.
3. Tool definitions and their handlers are declared in one place, and the schema the model sees is derived from the same source as the runtime validation. A new tool must be addable without editing the streaming transport or the UI.
4. Prompt assembly is a pure function of (prompt file, course pack, transcript). It has no other inputs, so it can be unit-tested and reviewed.
5. The feature does not introduce a database, a queue, or a session store.

### 4.2 Performance

1. Responses stream. The first visible token arrives without waiting for the complete reply.
2. The transcript keeps up with the stream without visible stutter on a laptop, and does not re-render the whole conversation on each chunk.
3. The injected pack is the dominant input cost each turn. Prompt assembly must not read the pack from disk more than once per request.
4. Long transcripts must not grow unbounded into the provider's context limit. Bound the number of turns sent, or the assembled input size, and document the strategy chosen.

### 4.3 Security

1. `.env` is gitignored and never committed. The repository carries an example file listing required variable names with empty values.
2. A missing key fails at startup or on first request with an explicit server-side message, never a silent fallback or a leaked key fragment.
3. The learner's message length is capped server-side. Oversized input is rejected before reaching the provider.
4. Server function endpoints stay behind the existing CSRF middleware.
5. Tool arguments coming from the model are validated before use and treated as untrusted input.
6. No key material, full prompt, or pack content appears in client-visible errors or in browser console output.

### 4.4 Reliability

1. Provider rate limits and transient failures surface as the recoverable error path in R7 rather than an unhandled rejection.
2. An aborted stream leaves no dangling request and no locked UI state.
3. A malformed or unknown tool name from the model is handled as a tool error, not a crash.
4. A tool call that fails does not discard the text already streamed in that turn.

### 4.5 Usability

1. All learner-facing text is French, tutoiement, consistent with the existing interface copy.
2. The transcript follows the newest message, and stops following when the learner scrolls up.
3. A visible indicator distinguishes "the tutor is thinking" from "the tutor has stopped".
4. The streaming region is announced to assistive technology without re-reading the whole transcript on each chunk.
5. The composer, send, and cancel controls are keyboard reachable and correctly labelled.
6. The existing responsive behaviour is preserved: side-by-side on large screens, whiteboard above chat below on small ones.

### 4.6 Known limitations carried forward

Recorded so later tickets can close them, and so the gap is not mistaken for an oversight:

1. **No enforcement of answer withholding.** R9 is prompt-only. A leak filter and a checker-issued verdict are required before the product claim in `specs/product.md` §5.2 and §8 holds.
2. **No grading.** The exercise card accepts input and does nothing with it.
3. **No mastery record.** Nothing is remembered between sessions, so the tutor cannot plan from prior performance as §6.3 requires.
4. **Board interactions are invisible to the tutor.** It does not learn that the learner revealed a step or answered a check question.
5. **Unverified pack items.** Seven items in the chapter 1 pack await parent validation. The prompt routes around them; it does not resolve them.
