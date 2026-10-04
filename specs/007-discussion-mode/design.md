# 007 — Discussion mode: design

## 1. Overview

Discussion is a second **mode** on the machinery specs 001–006 already built. One turn loop, one SSE contract, one board, one reducer. A mode selects three things and nothing else:

1. **A prompt layer** — `prompts/modes/<mode>.fr.md` and `prompts/modes/<mode>.opening.fr.md`, substituted into `tutor.fr.md` at two new markers.
2. **A tool set** — `registry.declarations(mode)`. Discussion gets the two board tools; the three path tools are not declared.
3. **A transcript owner** — the parcours keeps posting its transcript (`POST /api/chat`); a discussion's transcript is a database row (`conversations`) and the turn request names it.

Everything else — `TutorService.run_turn`, `tool_events.event_of`, `history.to_provider_input`, the nine SSE events, `useTutorSession`'s reducer, the whiteboard, the voice bridge — is reused unchanged or with a parameter added.

Two locks keep a discussion off the progress record: the section tools are not declared to the model, and the turn's `TurnContext` is built with `save=None`, so even a tool that somehow ran could not persist.

### 1.1 Decisions resolving the requirements' open questions

| Q | Decision | Why |
|---|---|---|
| 1 — mode layer vs. the cache breakpoint | **Two prefixes per chapter.** The mode layer sits in the developer message, in front of the breakpoint. | The curriculum overview already names `start_section` / `complete_section` in the cached text; sharing one prefix would mean either telling Célestin about tools he does not have, or moving the mode block behind the breakpoint and paying ~700 tokens every turn. Within a session the second prefix is cached from turn 2, so the real cost is one uncached read (~13 500 tokens, ~0,054 USD) per mode switch — cheaper than the trailing-block option past ~15 turns, and far simpler. |
| 2 — the turn route | **Separate routes** under `/api/discussion`, sharing the SSE framing helper with `/api/chat`. The parcours is untouched. | The bodies genuinely differ (client-held vs server-held transcript). One route with both `history` and `conversation_id` optional would let a client send both. |
| 3 — Discussion from inside the lesson | **One component, two hosts.** `DiscussionPanel` is mounted alone by `/…/discussion`, and mounted *alongside* `LessonScreen` in the lesson route, toggled by visibility (never unmounted once opened). | R1.3: the lesson's transcript is in memory only; unmounting it to show a discussion would destroy the séance. |
| 4 — the cap | `DISCUSSION_MAX_ENTRIES` (400) and `DISCUSSION_MAX_CHARS` (200 000). Reaching either closes the conversation; the next turn is refused `409 conversation_full`. | Mirrors `max_history_entries`. The message is the product's, not a model turn (deviation D3). |
| 5 — the opening turn | **A model call**, as in the parcours. | Célestin's opening has to read the pack and the progress to be worth anything ("on a fini les suites arithmétiques, tu veux revenir sur la somme ?"). A canned greeting would be the blank page R2.5 exists to avoid. |
| 6 — the trailing state message | `state_message(..., mode)`. The parcours branch is byte-identical to today; the discussion branch drops the `start_section("…")` instructions and says the path is the parcours's business. | The current text instructs the model to call tools Discussion does not have. |
| 7 — « Points à vérifier » in the view | **No.** Célestin already raises them in conversation (R2.3); a panel would be a second content surface to maintain. | Out of scope; the chapter's content page already shows the pack. |

## 2. Architecture

```
browser                                        backend                                   SQLite
───────                                        ───────                                   ──────
/courses/$c/chapters/$ch            ┌────────────────────────────────────────┐
  LessonScreen ──POST /api/chat────▶│ chat.py       mode=parcours            │──▶ progress
  DiscussionPanel (toggled, kept)   │   history from the request             │
        │                           │                                        │
/courses/$c/chapters/$ch/discussion │                                        │
  DiscussionPanel                   │                                        │
   ├─ GET  …/discussion ───────────▶│ discussion.py  live conversation       │◀── conversations
   ├─ POST …/discussion ───────────▶│                new conversation        │──▶ conversations
   └─ POST /api/discussion/turn ───▶│ DiscussionService                      │
                                    │   load entries ─┐                      │
                                    │                 ▼                      │
                                    │        TutorService.build_input(mode)  │
                                    │          PromptService  tutor+subject  │
                                    │            +pack+overview(mode)        │
                                    │            +modes/<mode>.fr.md         │
                                    │        TutorService.run_turn(mode)     │
                                    │          registry.declarations(mode)   │
                                    │          TurnContext(save=None)        │
                                    │                 │                      │
                                    │   entries_from_events ◀── TurnEvent    │
                                    │        append on turn.end ─────────────┼──▶ conversations
  ◀──────── text/event-stream ──────┤                                        │
                                    └────────────────────────────────────────┘
  useTutorSession(transport)  ── same reduce(), same board, same markers
  useVoiceSession ── /api/voice/session {mode, conversation_id}
                  ── /api/voice/tool  {mode, …}
                  ── POST /api/discussion/voice/turn  (the browser reports a spoken turn)
```

## 3. Components and interfaces

### 3.1 `Mode`

`app/domain/mode.py`, new:

```python
Mode = Literal["parcours", "discussion"]
MODES: tuple[Mode, ...] = ("parcours", "discussion")
DEFAULT_MODE: Mode = "parcours"
```

Depended on by `services` and `api/schemas`; depends on nothing. A third mode (Révision) is a value here, a pair of prompt files and a row in the tool table.

### 3.2 Prompt layers — `app/services/prompts.py`, `prompt_service.py`

`tutor.fr.md` loses two sections and gains two markers, placed exactly where the removed text sat so the assembled parcours text stays **byte-identical**:

| Marker | Replaced by | Today's content moved there |
|---|---|---|
| `<!-- MODE -->` | `prompts/modes/<mode>.fr.md` | the whole `## Le parcours` section → `modes/parcours.fr.md`, verbatim |
| `<!-- MODE_OPENING -->` | `prompts/modes/<mode>.opening.fr.md` | the whole `## Le début d'une séance` section → `modes/parcours.opening.fr.md`, verbatim |

Two files per mode rather than one with an internal delimiter: no new parsing, and `test_text_rendering_is_byte_stable` passes **unchanged** for the parcours, which is the proof the refactor changed nothing.

```python
# PromptLibrary
def mode(self, mode: Mode) -> str: ...            # prompts/modes/<mode>.fr.md
def mode_opening(self, mode: Mode) -> str: ...    # prompts/modes/<mode>.opening.fr.md
```

Both are mtime-cached, checked at startup and reported by `/api/health` like every other prompt file (a missing one stops the process naming it).

```python
# prompt_service
def render_system_text(
    tutor_text, subject_text, pack_text, overview_text,
    mode_text: str, opening_text: str, *, voice: bool = False,
) -> str: ...

def build(
    tutor_text, subject_text, pack_text, curriculum, progress, history_items,
    mode_text: str, opening_text: str, mode: Mode, now=None,
) -> list[dict[str, Any]]: ...
```

`build` is otherwise unchanged: one developer message ending in the explicit cache breakpoint, the transcript, then the trailing state message — now `curriculum_render.state_message(curriculum, progress, now, mode)`.

The marker substitution keeps its single-pass rule: a `<!-- MODE -->` string appearing inside a student's pack is left as text, never substituted.

### 3.3 `prompts/modes/discussion.fr.md` — content

Written in the voice and register of `tutor.fr.md`; it does not repeat the shared sections (the source rule, the way of speaking, the way of teaching, the board, what Célestin never does). It states:

- **No path here.** The chapter's sections are the parcours; Célestin can situate the student in them and point at one, and cannot open or close one. If the student wants to work a section, they go to the parcours.
- **The student leads the subject, Célestin leads the exchange**: he asks what they want to look at, proposes when they do not know, works one idea at a time, and writes on the board whenever he teaches.
- **A statement the student brings** is a base of discussion, never a request for a solution (R3.2): what does the statement give, what have you tried, which notion of the chapter does it turn on. He does not produce the answer or a complete solution, in the conversation or on the board, however it is asked.
- **A brought statement is material, not a source** (R3.3): formulas, methods, notation and vocabulary still come from the pack only; if it needs something the chapter does not contain, he says so in one sentence.
- **The exercise he sets himself** stays under the withholding rule (R3.1); there is no « Étape suivante » button to hand over.
- **Off-topic** and another chapter are redirected in one sentence (R2.8).

`discussion.opening.fr.md`: on an empty conversation Célestin opens by himself — greeting, one sentence on where the student stands in the chapter (from the trailing state message), two or three concrete openings drawn from the pack, then he waits.

### 3.4 `curriculum_render`

```python
def overview(curriculum: Curriculum, mode: Mode = "parcours") -> str: ...
def state_message(curriculum, progress, now=None, mode: Mode = "parcours") -> str: ...
```

Both keep their parcours branch byte-identical. The discussion branches:

- `overview`: same numbered section list; the paragraph naming `start_section` / `complete_section` is replaced by one saying the sections are the chapter's parcours, that they are followed there, and that they cannot be opened from a discussion.
- `state_message`: keeps the date/time line and the « n section(s) faite(s) sur N » line; drops every `start_section("…")` instruction and the « Commence-la avec … » sentence; adds that the student can be pointed at the next section but must go to the parcours to work it.

### 3.5 Tool registry — `app/services/tools/registry.py`

`_TOOLS` and the per-tool declarations are unchanged. What becomes mode-aware is which of them are offered:

```python
_MODE_TOOLS: dict[Mode, tuple[str, ...]] = {
    "parcours": ("display_board", "clear_board", "start_section", "complete_section", "propose_next_step"),
    "discussion": ("display_board", "clear_board"),
}

# Built once per mode, as _DECLARATIONS is today: byte-stable by construction.
_DECLARATIONS: dict[Mode, list[dict[str, Any]]]
_REALTIME_DECLARATIONS: dict[Mode, list[dict[str, Any]]]

def declarations(mode: Mode = "parcours") -> list[dict[str, Any]]: ...
def realtime_declarations(mode: Mode = "parcours") -> list[dict[str, Any]]: ...
```

Declaration **order** within a mode follows `_TOOLS`' order, so the parcours list is byte-identical to today and the discussion list is a prefix of it — the board declarations' bytes do not move.

`execute` gains the mode gate, taken from the context:

```python
def execute(name: str, arguments_json: str, ctx: TurnContext) -> ToolOutcome:
    tool = _TOOLS.get(name)
    if tool is None or tool.name not in _MODE_TOOLS[ctx.mode]:
        raise ToolValidationError(
            f"L'outil '{name}' n'est pas disponible ici. Outils disponibles : "
            f"{', '.join(_MODE_TOOLS[ctx.mode])}."
        )
    return tool.handler(_parse(tool, arguments_json), ctx)
```

This matters because `/api/voice/tool` takes a tool name from the browser: the gate is what makes the mode a server-side fact rather than a prompt-level hope.

### 3.6 `TurnContext`

Gains `mode: Mode = "parcours"`. `from_progress` gains the keyword. In a discussion the controller builds it with `save=None`, so `commit` adopts in memory and never writes — the second lock behind the undeclared tools.

### 3.7 `TutorService`

```python
def build_input(self, chapter, entries, ctx, mode: Mode = "parcours") -> list[dict[str, Any]]: ...
async def run_turn(self, items, ctx) -> AsyncIterator[TurnEvent]: ...   # uses registry.declarations(ctx.mode)
```

`run_turn` reads the mode from `ctx`, so its signature is unchanged. `_log_turn` gains `"mode": ctx.mode`.

### 3.8 `DiscussionService` — `app/services/discussion.py`, new

```python
class DiscussionService:
    def __init__(self, repos: Repositories, settings: Settings) -> None: ...

    def live(self, user_id: str, chapter: LessonChapter) -> Conversation | None:
        """The live conversation for this student and chapter, or None. Closes and
        returns None if it was held against an older content version (R8.3)."""

    def start(self, user_id: str, chapter: LessonChapter) -> Conversation:
        """Close any live one as `replaced`, insert a new empty one. Rate-limited."""

    def turn_entries(self, conversation: Conversation, message: str | None) -> list[Entry]:
        """Stored entries plus the learner message; raises ConversationFull / EmptyTurn."""

    def append(self, conversation: Conversation, new_entries: list[Entry]) -> None:
        """One UPDATE: entries += new_entries, counters, updated_at; closes the
        conversation as `capped` if a limit is crossed."""


def entries_from_events(events: list[TurnEvent]) -> list[Entry]:
    """The turn's events as transcript entries, mirroring what the browser records:
    one TutorEntry per text block, one ToolEntry per successful tool call.
    Refused calls emit no event and are not recorded, as in the browser."""
```

`entries_from_events` maps `TextDeltaEvent` (grouped by `block_id`, in order) → `TutorEntry`, `BoardSetEvent` → `ToolEntry(name="display_board", arguments={"card": …})`, `BoardClearEvent` → `ToolEntry(name="clear_board")`. The three section events cannot occur in a discussion.

**Append policy (NFR 4.4.1).** The route buffers the turn's events and appends `[learner, *produced]` in **one** write, only when the stream reaches `turn.end` with reason `end` or `max_rounds`. A provider failure, a disconnect or a cancellation appends nothing: the conversation is left exactly as it was, and the browser keeps its local copy so `retry()` re-sends without retyping. A half-finished reply is therefore never replayed to the model as a finished message.

### 3.9 Routes

New module `app/api/routes/discussion.py`, mounted under `/api` after `chat`.

| Route | Roles | Body | Answer |
|---|---|---|---|
| `GET /api/courses/{c}/chapters/{ch}/discussion` | owner | — | `200 {conversation: Conversation \| null}`; `404`; `409 chapter_not_ready` |
| `POST /api/courses/{c}/chapters/{ch}/discussion` | owner | — | `201 {conversation}` — closes the live one as `replaced`; `429 discussion_quota` |
| `POST /api/discussion/turn` | owner | `{course_id, chapter_id, conversation_id, message}` | SSE, the same nine events |
| `POST /api/discussion/voice/turn` | owner | `{course_id, chapter_id, conversation_id, entries}` | `204` |

`GET` is a pure read: it creates nothing. A first open sees `null` and calls `POST` — the same call the « Nouvelle conversation » button makes, so there is one creation path. `message` is `str | None`; `null` means the opening turn and is accepted only on an empty conversation (`422 empty_conversation_expected` otherwise).

The SSE framing (`_stream`, heartbeats, `SSE_HEADERS`, the after-first-byte error rule) moves from `chat.py` into `app/api/sse.py` and is shared by both turn routes. `chat.py`'s behaviour is unchanged.

Ownership goes through `lesson_chapter` exactly as `/api/chat` does: `404` unless owned, `409 chapter_not_ready` without content. A `conversation_id` belonging to another student, another chapter, or a closed conversation is `404` / `409 conversation_closed`.

### 3.10 Voice

- `VoiceSessionRequest` gains `mode: Mode = "parcours"` and `conversation_id: Id | None`. For `discussion`, the seed is built from the stored conversation instead of a posted `history`; `VoiceService` uses `registry.realtime_declarations(mode)` and `render_system_text(..., mode_text, opening_text, voice=True)`.
- `VoiceToolRequest` gains `mode: Mode = "parcours"`. `/api/voice/tool` builds its `TurnContext` with that mode and `save=None` for a discussion, so `registry.execute`'s gate refuses a section tool whatever the browser sends.
- **`POST /api/discussion/voice/turn`** is how a spoken turn reaches the store. The browser reports the entries it observed; the server validates shape and size and appends them under the same cap. See deviation D1.

### 3.11 Frontend

**Transport seam.** `useTutorSession` gains a transport so one hook, one `reduce` and one board serve both modes:

```ts
export type TurnInput = { history: HistoryEntry[]; message: string | null };
export type TurnTransport = (input: TurnInput, signal: AbortSignal) => AsyncGenerator<TutorEvent>;

export type TutorSessionOptions = LessonScope & {
  initialProgress: Progress;
  transport?: TurnTransport;      // default: the parcours transport (POST /api/chat)
  initialState?: SessionState;    // default: EMPTY_SESSION
  autoOpen?: boolean;             // default: true
};
```

`run(input)` replaces `run(history)` and keeps the input in a ref so `retry()` re-sends the same message. `send` builds `{history: stateRef.current.history, message: trimmed}`; the opening turn is `{history: [], message: null}`. The parcours transport ignores `message`, the discussion transport ignores `history` — neither shape can be sent to the wrong route.

**Restoring a conversation.** `sessionFromEntries(entries: StoredEntry[]): SessionState` — a pure function next to `reduce`, synthesising the events the entries came from and folding them through `reduce`, so transcript, `boards`, `board` and markers are rebuilt by the same code that built them live. Markers come from the server (`StoredEntry.marker`), because the backend owns their wording.

**Components.**

- `src/components/celestin/discussion-panel.tsx` — `DiscussionPanel({ chapter, user, hidden })`: loads the live conversation, creates one if `null`, builds `initialState` with `sessionFromEntries`, mounts `TutorColumn` + `Whiteboard` in the same resizable layout as the lesson, and owns the « Nouvelle conversation » action behind a `ConfirmDialog`.
- `src/routes/_auth/courses/$courseId/chapters/$chapterId/discussion.tsx` — the standalone entry; same loader shape as the lesson route.
- `lesson.tsx` — a « Discuter » toggle in `LessonBar`; `DiscussionPanel` is mounted on first open and thereafter kept mounted with `hidden`, so neither session is ever torn down (R1.3).
- `chapter-row.tsx` — a secondary « Discuter » link on every ready chapter, beside the unchanged primary action.
- `lib/tutor/discussion.ts` — the three queries/mutations and the discussion transport.

`TutorColumn` takes the chapter strip and map as optional: `DiscussionPanel` passes neither (R6.3), and shows instead a link back to the parcours. No new SSE event, no change to `types.ts`'s event union.

## 4. Data models

### 4.1 `conversations`

```python
class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False, default="discussion")
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(8), nullable=False, default="live")
    closed_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("state in ('live','closed')", name="ck_conversations_state"),
        CheckConstraint("mode in ('discussion')", name="ck_conversations_mode"),
        Index("ix_conversations_user_chapter", "user_id", "chapter_id"),
        Index(
            "uq_conversations_live", "user_id", "chapter_id", unique=True,
            sqlite_where=text("state = 'live'"), postgresql_where=text("state = 'live'"),
        ),
    )
```

`CONVERSATION_STATES = ("live", "closed")`, `CLOSED_REASONS = ("replaced", "content_changed", "capped")`.

- `mode` is stored although only `discussion` is written today: Révision will add a value, not a table (NFR 4.1.6). The check constraint widens with it.
- `content_version` is the chapter version the conversation was held against. `DiscussionService.live` closes a conversation whose version no longer matches and returns `None` (R8.3) — a lazy rule, so a content edit does not have to know about conversations.
- The partial unique index enforces "at most one live conversation per (student, chapter)" in the database, portably.
- `entries` is a JSON array of the existing `Entry` shapes, the same discriminated union the transcript already uses. One blob, like `chapters.curriculum`: an append is one `UPDATE` and therefore atomic, which is what NFR 4.4.1 asks for. `char_count` makes the cap a comparison rather than a re-measure.

Types are portable (`String`, `Integer`, `JSON`, `DateTime(timezone=True)`), as the models' docstring requires.

Migration `0005_discussion_conversations.py`, `down_revision = "0004"`, with a working `downgrade` that drops the table.

### 4.2 Repository

```python
@dataclass(frozen=True)
class ConversationRecord:
    id: str
    user_id: str
    chapter_id: str
    content_version: int
    entries: list[dict[str, Any]]
    entry_count: int
    char_count: int
    state: str
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime


class ConversationRepository(_Repo):
    def live(self, user_id: str, chapter_id: str) -> ConversationRecord | None: ...
    def get_owned(self, user_id: str, chapter_id: str, conversation_id: str) -> ConversationRecord | None: ...
    def start(self, user_id: str, chapter_id: str, content_version: int) -> ConversationRecord: ...
    def close(self, conversation_id: str, reason: str) -> None: ...
    def append(self, conversation_id: str, entries: list[dict], *, expected_count: int,
               close_reason: str | None = None) -> ConversationRecord: ...
    def started_since(self, user_id: str, since: datetime) -> int: ...
```

Synchronous, one short session per call, added to `Repositories` — the existing style. `append` takes `expected_count` as an optimistic guard: a mismatch means another turn appended first, and raises `ConversationBusy` (R4.7). `start` closes any live row and inserts in one transaction.

### 4.3 DTOs — `app/api/schemas/discussion.py`

```python
class StoredEntry(_Model):
    """A stored entry as the browser reads it back. `marker` is the French label the
    transcript shows for a tool call; the backend owns its wording."""
    kind: Literal["learner", "tutor", "tool"]
    text: str | None = None
    name: str | None = None
    arguments: dict[str, Any] | None = None
    marker: str | None = None


class ConversationDTO(_Model):
    id: Id
    chapter_id: Id
    entries: list[StoredEntry]
    entry_count: int
    full: bool
    created_at: datetime


class ConversationResponse(_Model):
    conversation: ConversationDTO | None


class DiscussionTurnRequest(_Model):
    course_id: Id
    chapter_id: Id
    conversation_id: Id
    message: Annotated[str, Field(min_length=1, max_length=_settings.max_message_chars)] | None = None


class VoiceTurnRequest(_Model):
    course_id: Id
    chapter_id: Id
    conversation_id: Id
    entries: Annotated[list[Entry], Field(max_length=32)]
```

`ChatRequest` gains nothing: the parcours wire shape is untouched. `VoiceSessionRequest` and `VoiceToolRequest` gain `mode` (and `conversation_id` on the former).

### 4.4 Configuration

| Setting | Default | Notes |
|---|---|---|
| `DISCUSSION_MAX_ENTRIES` | 400 | Mirrors `max_history_entries`. |
| `DISCUSSION_MAX_CHARS` | 200000 | Whichever is crossed first closes the conversation. |
| `DISCUSSION_CONVERSATIONS_PER_DAY` | 30 | Per student, counted from the rows (NFR 4.3.5). |

Trimming for the model reuses `history_token_budget`.

## 5. Error handling

The existing split holds: before the first SSE byte, an HTTP status with a French JSON body; after it, an `error` event then `turn.end`.

| Situation | Answer |
|---|---|
| Chapter not owned / unknown | `404 not_found` |
| Chapter without content | `409 chapter_not_ready` |
| Conversation unknown, or another student's, or another chapter's | `404 not_found` |
| Conversation closed (replaced, capped, content changed) | `409 conversation_closed` with the reason; the view offers « Nouvelle conversation » |
| Conversation at its cap | `409 conversation_full` |
| `message: null` on a non-empty conversation | `422 empty_conversation_expected` |
| A turn already in flight on this conversation | `409 conversation_busy` |
| Too many conversations started today | `429 discussion_quota` |
| Mode prompt file missing or broken | `500`, as for any prompt file; `/api/health` degraded |
| Provider failure mid-turn | `error` event + `turn.end`; **nothing appended** |
| Append fails after a good turn | `error` event after `turn.end`'s data is prepared; logged `conversation_append_failed`. The turn is lost to the store, not to the screen. |

New French messages live with the existing ones in `app/domain/errors.py`.

## 6. Testing strategy

**Backend, offline, with the scripted fake provider.**

- `test_prompt_service.py` — `render_system_text` with the two new markers; **`test_text_rendering_is_byte_stable` passes unchanged** for the parcours (the proof the prompt refactor is behaviour-preserving); a new sha fixture for the discussion rendering.
- `test_registry.py` — `declarations("parcours")` is byte-identical to today's snapshot; `declarations("discussion")` contains exactly `display_board` and `clear_board`; `realtime_declarations(mode) == declarations(mode)` minus `strict`, for every mode; `execute` refuses a section tool when `ctx.mode == "discussion"`, with a French message.
- `test_curriculum_render.py` — the parcours branches of `overview` and `state_message` byte-identical to their fixtures; the discussion branches name no tool.
- `test_discussion_service.py` — `entries_from_events` over a scripted event list; the cap; `live` closing a stale-version conversation.
- `test_conversation_repositories.py` — `start` closing the previous one, the partial unique index refusing a second live row, `append`'s `expected_count` guard, the cascades from chapter, course and user.
- `test_migrations.py` — head matches the models; `0005` upgrades and downgrades.
- `tests/integration/test_discussion_endpoint.py` — a **golden SSE transcript** for a discussion turn, the same byte-exact shape as `test_golden_text_only`; the opening turn; `409`s and `422`; and the load-bearing one: **after any discussion turn, `progress` holds no row for the chapter**, asserted directly against the database.
- `test_route_guards.py` and `test_layering.py` pass untouched.
- `test_chat_endpoint.py` unchanged — the parcours wire shape and goldens do not move.

**Frontend, vitest.**

- `sessionFromEntries` — pure, outside React: entries in, transcript/boards/board/markers out; round-trips a conversation whose last tool call was `clear_board`.
- The transport seam — `run`/`retry` re-send the same input; the parcours transport still posts `{course_id, chapter_id, history}`.
- `discussion-panel` under jsdom: `null` conversation → one `POST` then the opening turn; « Nouvelle conversation » confirms before replacing.
- The lesson route: opening Discussion and returning leaves the lesson's transcript and board intact (R1.3).

**Live scripts.** `scripts/probe.py` gains the discussion set of R9.2 (brought homework, « donne-moi juste la réponse » with an exercise open, a method outside the pack, an off-topic request, a request to close a section) and runs it through the discussion prompt and tool set. `scripts/smoke.py` runs two turns in **each** mode and keeps failing on a cache miss, which is how NFR 4.2.1 is enforced.

## 7. Performance

- **Cache.** Two prefixes per chapter (§1.1). `smoke` asserts a discussion turn's second round reports non-zero `cached_tokens`; the measured figure goes in `documentation/`.
- **The blob.** An append rewrites the `entries` JSON. At the cap that is ~200 KB per turn on SQLite — sub-millisecond, and it buys atomicity for free. If it ever bites, the row becomes a child table without touching the service seam.
- **One extra query per turn** (`live` / `get_owned`), in the same threadpool hop as the ownership check.
- **Storing does not delay the first byte**: the load happens before the stream opens, the append after `turn.end`.
- Trimming for the model is `history.trim` at `history_token_budget`, unchanged.

## 8. Security

- Every new route declares `require_roles("student")` and resolves the chapter through `lesson_chapter`, so ownership is checked in the SQL and a stranger's conversation is `404`, never `403`.
- `conversation_id` is uuid4 hex, validated by the same `Id` pattern; `get_owned` joins on `user_id` **and** `chapter_id`, so a valid id from another chapter does not resolve.
- Mutating routes pass `SameOriginMiddleware`; the SSE route streams, so the middleware's no-body rule still applies.
- **Stored conversation content is data.** It enters the model as transcript items, behind the cache breakpoint, never in the instruction layer. A `<!-- MODE -->` string inside a pack or a conversation is not substituted (single-pass rule).
- **The mode is a server-side fact** for tool execution: `registry.execute` gates on `ctx.mode`, so `/api/voice/tool` cannot be made to run `complete_section` from a discussion by editing the request. A client that lies about its *own* mode can only affect its own progress, which it may already change legitimately through the parcours — noted rather than defended further.
- No conversation text in any log, metric or client-visible message.
- Quotas: `DISCUSSION_CONVERSATIONS_PER_DAY` per student; the turn route inherits the existing body and rate limits.
- Cascades: `ON DELETE CASCADE` on both foreign keys, so conversations go with the chapter, the course and the account.

## 9. Monitoring and observability

- `turn_complete` gains `"mode"`, so cost, rounds and `cached_tokens` are readable per mode.
- New log lines, ids and counts only, never content: `conversation_started` (user, chapter, reason for closing the previous one), `conversation_closed` (reason), `conversation_appended` (entries added, entry_count, char_count), `conversation_append_failed`, `discussion_quota`.
- `/api/health` reports the mode prompt files like the others; a deleted `modes/discussion.fr.md` shows as degraded with the file named.
- R9.4's engagement counts come from the `conversations` table (rows per student, `entry_count`) — no new telemetry.

## 10. Deviations from the requirements

- **D1 — R4.4 in the voice channel.** "The stored conversation is the source of truth; a client cannot extend it" holds for the text channel. In voice, the model's speech reaches the browser and never the server, so a spoken turn is *reported* by the browser (`POST /api/discussion/voice/turn`) and appended after validation. Short of proxying audio there is no alternative; the exposure is that a student can write arbitrary entries into **their own** conversation. Shape, size and entry count are validated, and the route is owner-scoped.
- **D2 — R2.4's trailing message.** The message keeps carrying the path state, but its parcours wording ("appelle `start_section("…")`") is replaced in discussion, per open question 6.
- **D3 — R4.6's wording.** "Célestin says so in one sentence" becomes a plain sentence from the product when a turn is refused `409 conversation_full`, not a model turn: it is cheaper, and it cannot itself fail.
- **D4 — R6.3.** The Discussion view shows no chapter strip and no map at all, rather than a read-only one: less surface, and nothing that implies progress is moving.
