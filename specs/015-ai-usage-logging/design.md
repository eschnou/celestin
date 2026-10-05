# 015 — AI usage logging: design

Requirements: [requirements.md](./requirements.md). References `R<n>` point there.

## 1. Overview

A **ledger** (`ai_usage` table) with one metadata-only row per provider call, written by recording wrappers that the provider hub puts around the clients it builds. The wrappers learn *who* from a **usage scope** held in a `contextvar` (the same mechanism as `request_id_var`): the services that know the user, course, chapter and correlation id open a scope around the code that calls a model; the wrapper reads it when the call starts. Nothing above `app/providers/` imports `openai`, the provider protocols (`LLMClient`, `CompletionClient`, `TranscriptionClient`) keep their signatures, and every offline fake is recorded without change because wrapping happens in the hub, after the factory.

Voice is the exception: the backend does not see Realtime's calls, so `POST /api/voice/usage` writes the session row directly. It replaces `voice_usage`, whose rows are copied into the ledger by the migration.

The admin reads the ledger through four `GET` routes under `/api/admin/usage` and one screen, `/admin/usage`.

Decisions:

| Decision | Choice | Why |
|---|---|---|
| How the user reaches the provider layer | `contextvar` scope, not a parameter | The authoring agent has dozens of call sites across its stages (`agent.py`); a scope set once in `AuthoringRunner._start` is copied into the background task and into every `gather`ed child. A parameter would change three protocols and every fake. |
| Where to wrap | `ProviderHub.build` (around the factory's `Clients`) | Covers the hub's proxies *and* `ai_test`, which uses `hub.current()` clients directly; covers fakes. |
| Write path | Fire-and-forget on the loop's default executor, drained at shutdown | R5: no write between events, none awaited in a `finally` under cancellation (an executor submit does not await). |
| Voice | Server-side map of the minted session → scope; row written by the usage route | The browser report does not carry course/chapter (`extra="forbid"`), and a client-supplied id would need an ownership check. |
| `voice_usage` | Copied into `ai_usage`, then dropped | No data shown twice (R4.5). Downgrade recreates it, best effort. |
| Absent vs zero | `usage_dict` (Chat adapter) omits what the server did not send | R1.5: null is not zero. Readers (`token_counts`) already treat a missing key as 0. |
| Cost | `usage["cost"]` if a finite number ≥ 0, else null | R3. No `Settings` price is read by this feature. |
| Pagination of calls | `limit + 1`, `has_more`, no `COUNT(*)` | A count over a large ledger is the one slow query; users are few, so the per-user view keeps an exact total. |

## 2. Architecture

```
 request / background task                                   admin browser
 ───────────────────────────                                 ─────────────
 TutorService.run_turn ──┐ with usage_scope(user, course,    /admin/usage
 AuthoringRunner._start ─┤   chapter, feature, correlation)       │ GET
 WorkReader.read ────────┤        │ contextvar                     ▼
 DictationService ───────┤        ▼                         api/routes/usage.py (AdminDep)
 admin /ai/test ─────────┘  ┌─────────────────────────────┐        │
                            │ ProviderHub (providers/)    │        ▼
   hub.llm / authoring_llm  │  Clients(wrapped):          │   AiUsageRepository
   hub.transcriber / ai_test│   RecordingLLM              │   (SQL GROUP BY, paged)
          ───────────────▶  │   RecordingCompletion ×2    │        ▲
                            │   RecordingTranscriber      │        │
                            └──────────┬──────────────────┘        │
                       inner client    │ UsageEntry                │
                       (Responses /    ▼                           │
                        Chat / audio) UsageRecorder.record ── executor ──▶ ai_usage
                                       (never raises; drain() at shutdown)  ▲
                                                                            │
 POST /api/voice/usage ── VoiceSessionScopes (mint → scope) ── add(entry) ──┘
```

## 3. Components and interfaces

### 3.1 `app/domain/usage.py` (new; depends on nothing)

```python
Feature = Literal["tutor_turn","discussion_turn","authoring","document_reading","work_reading",
                  "dictation","voice_session","ai_test"]
FEATURES: tuple[Feature, ...]
Status = Literal["ok","failed","truncated","cancelled"]
STATUSES: tuple[Status, ...]
# roles: reuse app.domain.ai_config.ROLES

@dataclass(frozen=True)
class UsageScope:
    user_id: str
    feature: Feature
    course_id: str | None = None
    chapter_id: str | None = None
    correlation_id: str | None = None
    audio_seconds: float | None = None      # dictation: known before the call

_scope: ContextVar[UsageScope | None]
def current_scope() -> UsageScope | None
@contextmanager
def usage_scope(scope: UsageScope | None) -> Iterator[None]:
    # previous = _scope.get(); _scope.set(scope); try: yield; finally: _scope.set(previous)
    # `set(previous)`, never `reset(token)`: a scope opened inside an async generator
    # (run_turn) may be left from another context, where reset raises ValueError.

@dataclass(frozen=True)
class UsageEntry:       # one row; every field of R1.5
    created_at: datetime; user_id: str; course_id: str|None; chapter_id: str|None; correlation_id: str|None
    role: Role; feature: Feature; model: str; provider: str
    status: Status; error_code: str|None
    latency_ms: int|None; ttft_ms: int|None
    input_tokens: int|None; cached_tokens: int|None; output_tokens: int|None; reasoning_tokens: int|None
    input_audio_tokens: int|None; output_audio_tokens: int|None; audio_seconds: float|None
    cost_usd: float|None

@dataclass(frozen=True)
class UsageNumbers:     # what a provider's usage dict says; None = not reported
    input_tokens; cached_tokens; output_tokens; reasoning_tokens: int | None; cost_usd: float | None

def read_usage(usage: dict[str, Any] | None) -> UsageNumbers
def feature_of(scope: UsageScope, role: Role) -> Feature
    # scope.feature == "authoring" and role == "transcription" -> "document_reading"; else scope.feature
```

`read_usage` over the Responses-shaped dict both adapters produce:

| Field | Source key | Null when |
|---|---|---|
| `input_tokens` | `input_tokens` | missing, not an int, negative |
| `cached_tokens` | `input_tokens_details.cached_tokens` | details or key missing |
| `output_tokens` | `output_tokens` | missing |
| `reasoning_tokens` | `output_tokens_details.reasoning_tokens` | details or key missing |
| `cost_usd` | `cost` | missing, `bool`, non-finite, negative, not a number |

An empty dict gives all nulls. Strings are never coerced (a provider's `"0.01"` is not a cost we vouch for).

### 3.2 `app/providers/recording.py` (new)

```python
class UsageSink(Protocol):
    def record(self, entry: UsageEntry) -> None: ...   # never raises

class UsageRecorder:                                    # the production sink
    def __init__(self, write: Callable[[UsageEntry], None]) -> None
    def record(self, entry) -> None
        # loop = running loop → fut = loop.run_in_executor(None, self._write_safely, entry);
        # kept in a set until done. No running loop (a sync caller) → write inline.
    def _write_safely(self, entry) -> None
        # try write(entry) except Exception: log.error("ai_usage_not_stored", extra={error: type(exc).__name__, role: entry.role})
    async def drain(self) -> None                       # await the pending writes (shutdown, tests)

def record_clients(clients: Clients, sink: UsageSink) -> Clients
    # dataclasses.replace(clients,
    #   tutor=RecordingLLM(clients.tutor, role="tutor", model=cfg.tutor.model, host=cfg.tutor.connection.host, sink),
    #   authoring=RecordingCompletion(..., role="authoring"), transcription=RecordingCompletion(..., role="transcription"),
    #   transcriber=RecordingTranscriber(..., role="voice", model=cfg.dictation.model, host=cfg.dictation.connection.host)
    #   if clients.transcriber else None)
    # `realtime` is not wrapped: the mint is not a billable call; the session row comes from the browser's report.
```

`model` and `host` come from `clients.config`, fixed when the clients are built, which is what R1.5 asks (the model in force for that call: a configuration change swaps the clients, and a call in flight finishes on the old ones).

**`RecordingLLM.stream`** keeps the protocol's shape (`AbstractAsyncContextManager[AsyncIterator[ProviderEvent]]`):

```python
@asynccontextmanager
async def stream(self, *, input, tools):
    scope = current_scope()            # read when the call starts
    started = time.monotonic(); seen = _Seen()   # first_token_at, usage, failed_code
    outcome: tuple[Status, str | None] = ("cancelled", None)
    try:
        async with self._inner.stream(input=input, tools=tools) as events:
            yield _watch(events, seen, started)  # async generator: notes TextDelta / Completed / Failed, re-yields
        outcome = seen.outcome()               # Failed seen → failed(code); Completed seen → ok; else cancelled
    except asyncio.CancelledError / GeneratorExit: outcome = ("cancelled", None); raise
    except Exception as exc: outcome = ("failed", _code(exc)); raise
    finally:
        self._emit(scope, outcome, latency=monotonic()-started, ttft=seen.ttft_ms(), usage=seen.usage)
```

A consumer that leaves the `async with` before `Completed` (the live check returns on the first valid tool call) is `cancelled`, usage null. A `Failed` event followed by the caller raising is `failed` with the event's code. `_code(exc)` = `exc.code` for a `TutorError`, else `"unknown"`; provider text is never read.

**`RecordingCompletion.complete`** (one instance per role, fixed `role`):

| Outcome | status | error_code | usage |
|---|---|---|---|
| returns | `ok` | null | `result.usage` |
| `ProviderOutputTruncated` | `truncated` | null | `exc.usage` |
| `ProviderOutputInvalid` | `failed` | `provider_output_invalid` | `exc.usage` |
| `CancelledError` | `cancelled` | null | none |
| other `Exception` | `failed` | `_code(exc)` | none |

Every branch re-raises the original exception. `latency_ms` = call start to return or raise.

**`RecordingTranscriber.transcribe`**: `ok` / `failed` / `cancelled`; tokens null, `cost_usd` null, `audio_seconds` from `scope.audio_seconds`.

**`_emit`**: no scope → `log.debug("ai_usage_unscoped", extra={"role": role})` and return (R2.5, R2.6: scripts and startup checks record nothing). Otherwise build the `UsageEntry` (`created_at` = wall-clock call start, `feature` = `feature_of(scope, role)`, numbers from `read_usage`) and `sink.record(entry)` inside `try/except Exception` (building the entry must not fail a call either).

**`ProviderHub`** takes `sink: UsageSink | None = None`; `build()` returns `record_clients(clients, sink)` when a sink is set. The proxies, `current()` and `install()` are unchanged. A test that asserts `hub.current().tutor is <fake>` must compare through the wrapper's `inner`.

**Adapters** (`providers/`):

- `chat_translate.usage_dict`: keys are emitted only for fields the server sent (`input_tokens` / `output_tokens` from `prompt_tokens` / `completion_tokens`; `input_tokens_details` only if `prompt_tokens_details.cached_tokens` is present; `output_tokens_details` likewise), plus `cost` when present on the usage object. Today it writes zeros. `token_counts` readers are unaffected (missing → 0). The line « absent fields count as zero » in `documentation/ai-providers.md` becomes « absent fields are left out ».
- `openai_responses`: `usage.model_dump()` already keeps provider extras (the SDK models allow extra fields), so `cost` flows through unchanged; a test pins it with an OpenRouter-shaped payload.
- `completion_result` / `chat_result`: `ProviderOutputTruncated(detail, usage=…)` and `ProviderOutputInvalid(detail, usage=…)` carry the call's usage dict (`.usage`, default `{}`), raised with the response's usage, so a retry or repair wrapper can count what an unusable answer was billed.

### 3.3 Where each scope is opened

| Site | Scope |
|---|---|
| `TutorService.run_turn` (first statement, closed in `finally`) | `UsageScope(ctx.user_id, "discussion_turn" if ctx.mode == "discussion" else "tutor_turn", ctx.course_id, ctx.chapter_id, turn_id)`; no scope when `ctx.user_id is None` (unit tests, scripts) |
| `AuthoringRunner._start`, around the `asyncio.create_task(self._execute(...))` line only | `UsageScope(user.id, "authoring", course.id, record.id, run_id)`: the task copies the context at creation, so every stage, repair, retry and `gather`ed page call carries it |
| `WorkReader.read` (new `course_id` parameter, from the route's `course.id`) | `UsageScope(user_id, "work_reading", course_id)` around `complete` |
| `DictationService.dictate` | `UsageScope(user_id, "dictation", audio_seconds=seconds)` around `transcribe` (`seconds` is computed before the call) |
| `routes/admin.py::test_ai` | `UsageScope(admin.id, "ai_test")` around `await ai.test(...)`; the checks run in the same task or children |

`TurnContext` gains `course_id: str | None = None` (and `from_progress(course_id=…)`); `open_lesson` passes its `course_id` to `load_context`, which sets it. `lesson_chapter` has already checked that the user owns that course and chapter.

The tutor turn's usage is summed (R1.7): `run_turn` keeps `usage` as the **sum** of the rounds' `Completed.usage` (new helper `domain/usage.py::add_usage(total, round) -> dict` adding `input_tokens`, `output_tokens`, the two `_details` counters, and `cost` when both sides have one), and `TurnEnd.usage` and `turn_complete` log the sum. The per-round numbers are in the ledger.

### 3.4 Voice session

- `VoiceService` holds `VoiceSessionScopes`: a bounded `OrderedDict[str, SessionScope]` (1,000 entries, 3 h TTL, lock-protected), filled in `create_session` after the secret is minted: `session_id → (user_id, course_id, chapter_id, model, host)` from `ctx` and `voice` config. In-process only; a restart loses it (the row is then written with null course and chapter and the model/host in force, a documented limit).
- `POST /api/voice/usage` (unchanged contract, still `204`, still never failing the caller): `entry = service.usage_entry(report, user.id)` then `await run_in_threadpool(repos.ai_usage.add, entry)`; the scope is used only if its `user_id` equals the authenticated user. `log_usage` keeps its log line (the environment-price estimate stays in the log, outside the ledger) but no longer returns a cost for storage.
- `usage_entry`: `role="voice"`, `feature="voice_session"`, `correlation_id=session_id`, `created_at = now − duration_s`, `status = "failed"/"voice_error"` for reason `error`, else `ok`; `input_tokens = input_text + input_audio`, `cached_tokens = cached_text + cached_audio`, `output_tokens = output_text + output_audio`, the two audio fields, `audio_seconds = duration_s`, `latency_ms`, `ttft_ms`, `cost_usd`, `reasoning_tokens` null. The bounds of `VoiceUsageReport` (R4.3) stay.

### 3.5 Repository

`AiUsageRepository(_Repo)` on `Repositories` (`ai_usage`; `voice_usage` removed with its row class). One short session per call.

```python
add(entry: UsageEntry) -> None
summary(period: Period) -> UsageTotals                        # + models: list[str] (distinct, sorted)
per_user(period, *, query, order, direction, limit, offset) -> tuple[list[UserUsage], int]
user_breakdown(user_id, period) -> Breakdown                  # by_role, by_model
calls(period, filters: CallFilters, *, limit, offset) -> tuple[list[CallListing], bool]   # bool = has_more
```

`Period(since: datetime | None, until: datetime | None)`: `created_at >= since` and `created_at < until`, UTC. Aggregates: `COUNT(*)`, `SUM(input_tokens)`, `SUM(cached_tokens)`, `SUM(output_tokens)`, `SUM(reasoning_tokens)` (nulls ignored by SQL, `coalesce(…, 0)`), `SUM(cost_usd)` (null when none reported) and `COUNT(cost_usd)` = calls with a reported cost. `per_user` joins `users` for name, email and `enabled`; `query` is matched exactly as `UserRepository.list_users` does (`lower()` + `LIKE … ESCAPE`, `%` and `_` literal; the Unicode-aware `lower()` registered on SQLite). `order` ∈ `calls | input_tokens | output_tokens | cost | name`, cost `NULLS LAST`; ties by `user_id` for stable paging. `calls` joins `users` (name, email) and `courses` (subject, language; left join, null once the course is gone) and orders by `created_at DESC, id DESC`; it reads `limit + 1` rows. Filters are `user_id`, `role`, `feature`, `model` (exact), `status`, `correlation_id`, all ANDed.

### 3.6 Admin API (`api/routes/usage.py`, router prefix `/admin/usage`, every route `AdminDep`)

| Route | Query | Answer |
|---|---|---|
| `GET /api/admin/usage/summary` | `since`, `until` | `{totals, models}` |
| `GET /api/admin/usage/users` | `since`, `until`, `q`, `order`, `direction`, `limit` (1–200, 50), `offset` | `{users: [UserUsageDTO], total}` |
| `GET /api/admin/usage/users/{user_id}` | `since`, `until` | `{user, totals, by_role, by_model}`; `404 not_found` for an unknown user; a user with no calls gets zeros and empty lists |
| `GET /api/admin/usage/calls` | `since`, `until`, `user_id`, `role`, `feature`, `model`, `status`, `correlation_id`, `limit` (1–200, 50), `offset` | `{calls: [CallDTO], has_more}` |

Validation is by FastAPI types: `role`, `feature`, `status`, `order`, `direction` are `Literal`s (an unknown value is `422`); `since`/`until` are timezone-aware `datetime` (naive → `422`) with `since < until` checked (`422`); `q` ≤ 100 characters; `model` ≤ 200; `correlation_id` ≤ 32. Handlers run the repository in `run_in_threadpool` like `list_users`. The router is included in `create_app`; `test_route_guards.py` covers it. No throttle: the routes are read-only and `GET`, unlike the settings routes that probe a provider.

DTOs (`api/schemas/usage.py`, `extra="forbid"` like the other schemas):

```python
class TotalsDTO:        calls: int; input_tokens: int; cached_tokens: int; output_tokens: int; reasoning_tokens: int
                        cost_usd: float | None; costed_calls: int            # costed_calls of calls
class UserUsageDTO(TotalsDTO):  user_id, name, email, enabled
class RoleUsageDTO(TotalsDTO):  role
class ModelUsageDTO(TotalsDTO): model, provider                              # grouped by (model, provider)
class CallDTO:          id: int; created_at: datetime; user_id, user_name, user_email
                        course_id, chapter_id: str | None; course_subject: Subject | None; course_language: CourseLanguage | None
                        correlation_id; role; feature; model; provider; status; error_code
                        latency_ms; ttft_ms; input_tokens; cached_tokens; output_tokens; reasoning_tokens
                        input_audio_tokens; output_audio_tokens; audio_seconds; cost_usd
```

No course or chapter name appears in any DTO (R6.6).

### 3.7 Frontend

```
src/routes/_auth/admin/usage.tsx             route /admin/usage; validateSearch: view (users|calls), period (today|7d|30d|all|custom), from, to, user, role, feature, model, status, correlation, page
src/components/celestin/admin/usage-panel.tsx   period selector, summary, the two views, the user detail
src/lib/admin-usage.ts                       the four queries (keepPreviousData), period → since/until, filter types
src/lib/i18n-format.ts                       + formatCost (4 decimals, locale), formatDurationMs, formatTokens (reuses formatCount)
messages/fr.json, en.json                    usage_* keys (labels for roles, features, statuses; columns; empty, loading, error states; « cost reported on X of Y »)
```

- The state lives in the URL search params (TanStack Router `validateSearch`), so a click on a user's row (`view=calls&user=<id>`) and the browser's back button work, and a view can be bookmarked. `period` presets are converted in the browser to `since`/`until` ISO strings (today = local midnight to now; the server only ever sees UTC instants). Default `30d`.
- `admin/index.tsx` gets a link « Consommation » next to the users panel. `isAdminPath` already admits `/admin/*`; `_auth.tsx`'s role routing applies. `routeTree.gen.ts` is regenerated by the router plugin.
- Per-user view: table (name + email, calls, input, cached, output tokens, cost, « cost reported on X of Y »), sort headers, search with the 250 ms debounce of `users-panel`, paging of 25 against `total`. The row expands the user's by-role and by-model totals (the `users/{id}` route) and has a « Voir les appels » action.
- Calls view: filter bar (user chip from the URL, role, feature, model from `summary.models`, status, correlation id), table with the columns of R6.5, « Next / Previous » driven by `has_more`. `cost_usd == null` renders `—`; a call with `status != ok` shows the status badge with the error code.
- Summary header: five figures and the cost with the coverage sentence; when `costed_calls == 0` the cost cell reads « Le fournisseur ne communique pas de coût » (R3, Usability 1), never `0`.
- Labels for role, feature, status are tables of message functions (the `ROLE_LABEL` pattern of `users-panel.tsx`); the `check-messages` test enforces catalog parity. The tables scroll horizontally on a narrow screen.

### 3.8 Documentation

`documentation/ai-usage.md` (new, linked from `index.md`); `admin.md` (routes, screen), `ai-providers.md` (the `usage_dict` line, the cost rule and known providers: OpenRouter's `usage.cost` in credits = USD; OpenAI, Groq and local servers report none), `voice.md` (the session row, client-reported caveat, `voice_usage` gone), `accounts-and-courses.md` (user deletion cascades the ledger); `CLAUDE.md` root and backend (layout, « Voice reuses… » line, the ledger and its scope rule); `specs/index.md`.

## 4. Data model

### `ai_usage` (migration `0010`, after `0009`)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | Integer PK autoincrement | no | |
| `created_at` | DateTime(tz) | no | call start, UTC |
| `user_id` | String(32) | no | FK `users.id` **ON DELETE CASCADE** |
| `course_id` | String(32) | yes | FK `courses.id` ON DELETE SET NULL |
| `chapter_id` | String(32) | yes | FK `chapters.id` ON DELETE SET NULL |
| `correlation_id` | String(32) | yes | turn id (12), run id (32), voice session id (12–32) |
| `role` | String(14) | no | check ∈ `ROLES` |
| `feature` | String(16) | no | check ∈ `FEATURES` |
| `model` | String(200) | no | `''` only for carried-over voice rows |
| `provider` | String(255) | no | host name; `''` for carried-over rows |
| `status` | String(10) | no | check ∈ `STATUSES` |
| `error_code` | String(40) | yes | |
| `latency_ms`, `ttft_ms` | Integer | yes | |
| `input_tokens`, `cached_tokens`, `output_tokens`, `reasoning_tokens` | Integer | yes | null = not reported |
| `input_audio_tokens`, `output_audio_tokens` | Integer | yes | voice sessions |
| `audio_seconds` | Float | yes | dictation, voice |
| `cost_usd` | Float | yes | provider-reported only |

Indexes: `ix_ai_usage_user_created (user_id, created_at)`, `ix_ai_usage_created (created_at)`, `ix_ai_usage_correlation (correlation_id)`, `ix_ai_usage_course (course_id)`, `ix_ai_usage_chapter (chapter_id)` (the last two keep the `SET NULL` of a course or chapter deletion from scanning the table). Check constraints are named `ck_ai_usage_role|feature|status` like `ck_conversations_state`.

### Migration `0010_ai_usage`

1. `op.create_table('ai_usage', …)` and the indexes (autogenerate, then review).
2. Carry-over, portable SQL: `INSERT INTO ai_usage (created_at, user_id, correlation_id, role, feature, model, provider, status, input_tokens, cached_tokens, output_tokens, input_audio_tokens, output_audio_tokens, audio_seconds) SELECT created_at, user_id, session_id, 'voice', 'voice_session', '', '', CASE WHEN reason = 'error' THEN 'failed' ELSE 'ok' END, input_text + input_audio, cached_text + cached_audio, output_text + output_audio, input_audio, output_audio, duration_s FROM voice_usage`. `cost_usd` null (their cost was an estimate). `error_code` is `voice_error` for reason `error`.
3. `op.drop_table('voice_usage')`.
4. `downgrade`: recreate `voice_usage` (columns as in 0001/0002, `session_id` String(32)), copy `voice_session` rows back (`reason` `learner`/`error` from status, `responses` 0, text shares = totals − audio shares, `cost_estimate_usd` 0), drop `ai_usage`.

No `users` table rebuild (spec 012's warning): nothing is added to it, and no SQL-expression default is used. The startup backup of spec 013 runs before this migration like any other. A migration test (`test_upgrade_from_0009_…`) loads rows into `voice_usage` first, upgrades, and checks the carry-over and that courses and users survive.

`models.py`: `AiUsageRow` replaces `VoiceUsageRow`; `ROLES` imported from `domain/ai_config`, `FEATURES` and `STATUSES` from `domain/usage`.

## 5. Error handling

| Situation | Behaviour |
|---|---|
| Ledger write fails (locked database, constraint, closed engine) | `UsageRecorder._write_safely` logs `ai_usage_not_stored` (error class and role only) and drops the row. The call, the turn and the response are untouched (R5.1). |
| Building an entry fails | Caught in `_emit`, same log line; the provider result or exception passes through unchanged. |
| No scope | No row, `ai_usage_unscoped` at debug (R2.5). A test per feature proves the scope is open at each call site. |
| Provider call fails or is cut | A row with `failed`, `truncated` or `cancelled`; the original exception is re-raised untouched. |
| Provider omits usage or cost | Nulls. Never estimated (R3.3). |
| Malformed or forged voice report | `VoiceUsageReport` validation as today (`204`, logged `voice_usage_malformed`); a scope owned by another user is ignored (null course and chapter). |
| Admin query with a bad enum, naive datetime, `since >= until`, oversized `q` | `422`. |
| Unknown user on `/usage/users/{id}` | `404 not_found`. |
| Non-admin | `403 forbidden` through `require_roles("admin")`. |
| Shutdown with writes pending | `lifespan` awaits `recorder.drain()` before `engine.dispose()`; a hard kill loses the pending rows (accepted, NFR Reliability 2). |
| SDK-internal retries | Invisible to the ledger: one application call is one row, its latency including the retries. An application-level retry is a separate call and a separate row. |

## 6. Testing strategy

Unit (offline, scripted fakes):

- `test_usage_domain.py`: `read_usage` table (Responses shape, Chat shape, empty, missing details, `cost` as int/float/str/bool/negative/NaN), `add_usage`, `feature_of`, `usage_scope` nesting and restore, including closing a scope from a different context (no exception).
- `test_recording.py`: each wrapper against `FakeLLM`/`FakeCompletion`/`FakeTranscriber`: `ok`, `failed` (`Failed` event; raised `ProviderTimeout` → `provider_timeout`), `truncated`, `cancelled` (task cancelled mid-stream; consumer leaving early), `ttft_ms` only when text came, model and host from the configuration, no scope → nothing recorded, and a sink that raises → the call still completes. `UsageRecorder`: writes off the loop thread, `drain`, a failing writer logs and swallows.
- `test_usage_providers.py`: `usage_dict` omits absent fields and passes `cost`; the Responses mapping keeps `cost` from an OpenRouter-shaped payload; `ProviderOutputTruncated.usage`.
- `test_usage_scopes.py`: one case per site of §3.3, each driving the real service with fakes and asserting the row's user, course, chapter, correlation id and feature (tutor parcours and discussion, authoring including a transcription page and a repair, work reading, dictation, `/admin/ai/test`); the authoring case proves a `gather`ed child and a retried attempt each produce a row.
- `test_tutor_service.py` (extended): a three-round turn's `TurnEnd.usage` and `turn_complete` carry the sum; the ledger has three rows with one correlation id.
- `test_privacy_ledger.py` (R7.3): one call per feature with distinctive strings in the input, the output, the tool arguments and the filename; the stored rows, the captured log records and every admin response contain none of them.
- `test_voice_service.py` / `test_voice_endpoint.py` (updated): the session row, the scope map (hit, miss after restart, wrong user, eviction at the bound), `reason=error`, the bounds of the report; `voice_usage` references removed.
- `test_repositories.py` (updated): `AiUsageRepository` against SQLite: aggregates with mixed null and reported costs (`costed_calls`), period boundaries (`>= since`, `< until`), `NULLS LAST` ordering, paging stability, `q` with `%`, `_` and accents, `has_more`, user deletion cascading the rows, course and chapter deletion nulling the ids and keeping the rows.
- `test_route_guards.py`: the four routes require `admin`.

Integration (`tests/integration/test_admin_usage.py`): the four routes through the app with seeded rows: admin sees every user's rows, student and parent get `403`, unauthenticated `401`, `422` cases, `404`, no course or chapter name in any body. `test_upgrade_from_0009_…` for the migration (Alembic upgrade on a SQLite file with `voice_usage` rows, then downgrade).

Frontend (`vitest`): `admin-usage.test.ts` (period → `since`/`until`, URL search validation, query keys); component tests for the panel (empty state, cost « not reported » never `0`, coverage sentence, row → calls navigation, paging with `has_more`, sort), `formatCost` and `formatDurationMs` in `i18n-format.test.ts`; `check-messages` for parity; the existing route-guard test extended for `/admin/usage`.

Live: `scripts/smoke.py` stays unrecorded (no scope). One manual check on a real provider that reports a cost (OpenRouter) confirms the `cost` key arrives on both API styles; the Chat path's shape of `usage.cost` is the only part the offline tests assume.

## 7. Performance considerations

- Write: one `INSERT` per call, on the executor, after the call ends; the tutor's first token and every later event are untouched (the wrapper only timestamps and stores the last usage). A multi-round turn adds a handful of rows.
- Read: `summary` and `per_user` are single `GROUP BY` scans bounded by the period, served by `ix_ai_usage_created`; `calls` is an index range scan on `created_at` (or `user_id, created_at` with a user filter) with `LIMIT n+1`, no `COUNT(*)`. All-time with no filter is the slow case and is still one scan per request, not a load into Python. `per_user` counts distinct users from the grouped subquery (one row per user with calls).
- Row size is bounded: ids, enumerations, a host name, a model name, numbers.
- The executor is the loop's default one, separate from the threadpool that serves requests, so a burst of writes cannot starve request handlers.
- Frontend queries use `keepPreviousData` and a 250 ms debounce on search, like `users-panel`.

## 8. Security considerations

- Read routes are `AdminDep` only and read-only; the ledger has no write route. The one browser-fed write (`/api/voice/usage`) writes only for the authenticated student, takes no ids from the body, and reads course and chapter from a server-side map bound to that user.
- No content is ever an input of an entry: the recorder sees the provider's usage dict, a status, a model name, a host and the scope's ids. `input`, `instructions`, `tools`, the events' text and the exception messages are never read by the wrapper (`_code` reads `.code`, not the message). `provider` is `Connection.host` (host name only, no scheme, port, path, user-info or key).
- Queries bind every parameter; `q` is escaped for `LIKE` and bound; enumerations are `Literal`s; there is no dynamic SQL from request text (`order` maps to a fixed column table).
- The admin DTOs carry no course or chapter name, only ids, subject and language (R6.6). Account deletion removes the rows by the foreign key (R2.4).
- Voice figures are client-reported; the documentation says so. Bounds on the report keep a forged one from producing negative or absurd numbers.

## 9. Monitoring and observability

- Log lines (JSON, `extra` fields, never content): `ai_usage_not_stored` (`error`, `role`), `ai_usage_unscoped` (`role`, debug). The existing `turn_complete`, `authoring_*`, `work_read`, `dictation` and `voice_usage` lines stay; `turn_complete.usage` becomes the turn's sum.
- The ledger is itself the observability of provider cost and latency: per call, per user, per model and provider host; the calls view filtered by `status != ok` shows failures with their error code, and by correlation id shows all the rounds of one turn, run or session.
- `GET /api/health` is unchanged. A test asserts a failing sink leaves it green.
