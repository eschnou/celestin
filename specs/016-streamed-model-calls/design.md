# 016 — Streamed model calls: design

## 1. Overview

`CompletionClient.complete()` becomes a streamed call on both adapters. Its result is unchanged; what changes is how the call is watched. One shared helper (`providers/streaming.py`) opens the stream, applies a first-event deadline then an idle deadline, counts what arrives, emits throttled progress snapshots and, on failure, classifies the exception, logs one `provider_call_failed` line and attaches diagnostics to the domain error. Every SDK client is built with `max_retries=0`, and the parameter disappears.

The authoring agent passes a progress callback per call. A `LiveProgress` object owned by the runner turns snapshots into (a) a throttled database write on the chapter row (`authoring_received_chars`, `authoring_progress_at`), (b) a `provider_call_progress` log every 30 s. The course DTO exposes the count and the seconds since the last write; the preparation card renders them.

Decisions (they refine the requirements, §11 lists the differences):

1. Live progress is stored on the chapter row, not in memory. The route layer stays a pure function of the database, a restart clears it with the existing orphan sweep, and polling needs no new dependency.
2. The slow-service notice is computed from a server-side `authoring_quiet_s`, not from a timestamp the browser would compare with its own clock.
3. A `ProviderTimeout` in authoring is run code `timeout` (« La préparation a pris trop de temps »), no longer `provider`.
4. The tutor keeps `REQUEST_TIMEOUT_S` as the SDK client's read timeout (already an idle limit between chunks); only the retry setting and the failure log change for it.
5. The event-level idle clock does not see SSE comment lines (the SDK drops them); the first-event allowance covers a reasoning model's silence, and an operator behind a gateway that pings raises `AUTHORING_IDLE_TIMEOUT_S` if needed.

## 2. Architecture

```
AuthoringRunner._execute
  │  LiveProgress(chapters repo, chapter_id, settings, extra)   ◀── one per run
  ▼
AuthoringAgent ── complete(..., on_progress=live.for_call(stage, attempt))
  │                                   │ ProgressSnapshot (≤1/s, no text)
  ▼                                   ▼
hub._CompletionProxy ──▶ RecordingCompletion ──▶ OpenAIResponsesClient / OpenAIChatClient
 (spec 014)              (spec 015: 1 ledger row)      │
                                                       ▼
                                         providers/streaming.py  consume(open, handle, limits, stats)
                                            · first-event deadline, then idle deadline (asyncio.timeout_at, rescheduled)
                                            · CallStats: events, received_chars, first/last event
                                            · progress snapshots, throttled to 1/s, one final
                                            · on failure: classify → log provider_call_failed → diagnostics on the error
                                                       │
                                                       ▼
                                      openai SDK (max_retries=0) ── stream=True ── provider

LiveProgress                        chapters repo                      GET /api/courses/{id}  (polled 3 s)
  callback(snapshot) ─ ≤1/s ─▶ coalescing writer ─ to_thread ─▶ set_received(chapter_id, chars)
  every 30 s ─▶ log provider_call_progress                      chapters.authoring_received_chars / _progress_at
                                                                        │ ChapterRow DTO: authoring_received_chars, authoring_quiet_s
                                                                        ▼
                                                            preparation card, chapter row badge
```

## 3. Components and interfaces

### 3.1 `app/providers/_client.py`

`make_client(connection, timeout_s)` — the `max_retries` parameter is removed; the client is built with `max_retries=0`. `openai_probe.py` drops its `max_retries=0` argument. `http_client=DefaultAsyncHttpxClient(timeout=timeout_s, …)` unchanged: `timeout_s` is the tutor's `REQUEST_TIMEOUT_S`, and for the two one-shot roles the first-event allowance (a backstop at least as large as both deadlines; the precise deadlines are `streaming.py`'s).

### 3.2 `app/providers/base.py`

```python
@dataclass(frozen=True)
class ProgressSnapshot:
    received_chars: int
    events: int
    elapsed_ms: int
    idle_ms: int

ProgressCallback = Callable[[ProgressSnapshot], None]   # synchronous, cheap, never raises into the stream

class CompletionClient(Protocol):
    async def complete(self, *, role, instructions, input, schema=None, schema_name=None,
                       max_output_tokens: int, on_progress: ProgressCallback | None = None) -> CompletionResult: ...

@dataclass(frozen=True)
class StreamLimits:
    first_event_s: float
    idle_s: float
```

### 3.3 `app/providers/streaming.py` (new, no `openai` import)

```python
class StreamTimeout(Exception):               # raised by consume, translated by failure()
    reason: Literal["first_event_timeout", "idle_timeout"]

class StreamBroken(Exception):                # raised by a handler
    reason: Literal["stream_ended", "error_event"]
    code: str                                 # a ProviderUnavailable/RateLimited/Timeout code

@dataclass
class CallStats:
    started: float                            # loop.time()
    events: int = 0
    received_chars: int = 0
    first_event_at: float | None = None
    last_event_at: float | None = None
    # properties: elapsed_ms, idle_ms, first_event_ms

async def consume(open_stream, handle, *, limits, stats, on_progress=None, progress_every_s=1.0) -> None
def failure(exc, *, role, model, host, stats) -> Exception     # translate + diagnostics + log
def log_done(*, role, model, host, stats, usage) -> None
```

`consume`:

```python
loop = asyncio.get_running_loop()
last_emit = stats.started
try:
    async with asyncio.timeout_at(stats.started + limits.first_event_s) as scope:
        raw = await open_stream()                    # headers; counts against the first-event allowance
        async with raw:                              # closes the response on every exit path
            async for event in raw:
                now = loop.time()
                stats.on_event(now)
                scope.reschedule(now + limits.idle_s)
                handle(event)                        # sync; updates stats.received_chars; may raise StreamBroken
                if on_progress and now - last_emit >= progress_every_s:
                    last_emit = now; _emit(on_progress, stats)
    if on_progress: _emit(on_progress, stats)        # the final snapshot
except TimeoutError as exc:
    if scope.expired():
        raise StreamTimeout("first_event_timeout" if stats.events == 0 else "idle_timeout") from exc
    raise
```

No `yield` inside the timeout scope: cancellation can only land in the awaits of the SDK stream. `_emit` swallows and logs (class only) a failing callback. Any event, of any type, counts as activity (R4 reasoning deltas, lifecycle events, unknown events). Every `consume` caller starts `stats` with `loop.time()` before building the request.

`failure(exc, …)` returns the domain error to raise: `_errors.translate(exc)` (for `StreamTimeout` → `ProviderTimeout`; `StreamBroken` → the error its `code` names), then `exc.diagnostics = CallDiagnostics(...)`, then one WARNING `provider_call_failed` (§8). Already-domain errors (`ProviderOutputTruncated`, `ProviderOutputInvalid`) pass through with reason `truncated` / `invalid_output`.

### 3.4 `app/providers/_errors.py`

Adds `classify(exc) -> Classification(error_class, reason, status_code, provider_code, request_id)`; `translate` is unchanged.

| Exception | `reason` |
|---|---|
| `StreamTimeout` | its own (`first_event_timeout`, `idle_timeout`) |
| `StreamBroken` | its own (`stream_ended`, `error_event`) |
| `openai.APITimeoutError` | `transport_timeout` |
| `openai.APIConnectionError` | `connection` |
| `openai.BadRequestError` whose message contains `stream` (case-insensitive) | `stream_unsupported` |
| `openai.APIStatusError` | `http_status` |
| `ProviderOutputTruncated` / `ProviderOutputInvalid` | `truncated` / `invalid_output` |
| anything else | `other` |

The message is read for the `stream` test only and is never logged. `provider_code` is `exc.code` when it is a short string; `request_id` is `exc.request_id` (the SDK's capture of `x-request-id`).

### 3.5 `app/providers/openai_responses.py`

`complete()` builds the same request (`completion_request`, unchanged) plus `stream=True`, then:

```python
stats = CallStats(started=loop.time())
text: list[str] = []
final: Any = None

def handle(event):
    nonlocal final
    kind = getattr(event, "type", "")
    if kind == "response.output_text.delta":
        text.append(event.delta); stats.received_chars += len(event.delta)
    elif kind in ("response.completed", "response.incomplete"):
        final = event.response
    elif kind in ("response.failed", "error"):
        raise StreamBroken("error_event", _failure_code(event))

await consume(lambda: self._client.responses.create(**request, stream=True), handle, …)
if final is None: raise StreamBroken("stream_ended", ProviderUnavailable.code)
```

The result is `completion_result(final_with_text, …)`: `final` supplies `status` and `usage`; `output_text` is `final.output_text` when non-empty, else the joined deltas (a compatible server may send an empty `output` in its last event). `completion_result` keeps its current behaviour (`incomplete` → `ProviderOutputTruncated` with usage; `failed` → `ProviderUnavailable`), so an answer is byte-identical to the non-streamed one. The `except Exception → raise failure(...)` wrapper replaces `_translate`. Unknown events are counted by `consume` and ignored by `handle`.

Constructor: `OpenAIResponsesClient(connection, model, timeout_s, reasoning_effort=None, limits: StreamLimits | None = None)`; `limits=None` means `StreamLimits(timeout_s, timeout_s)` (existing tests and the tutor-only paths).

`stream()` (tutor): request unchanged; the `except` calls `failure(...)` with `stats=None`-safe logging (no `received_chars`, `idle_ms`, `elapsed_ms` measured from the call start).

### 3.6 `app/providers/openai_chat.py`

`complete()` sends `stream=True, stream_options={"include_usage": True}` and the existing `max_completion_tokens` / `max_tokens` fallback (the first attempt's `BadRequestError` is raised by `open_stream()` and caught by the same wrapper, then the second `open_stream()` runs inside a new `consume`; a single `CallStats` spans both). `handle(chunk)`: appends `choice.delta.content` (counts chars), keeps the last `usage` (`usage_dict`), keeps `finish_reason`. After `consume`: no `finish_reason` → `StreamBroken("stream_ended")`; then a new `chat_finish(text, finish, usage, parse_json)` shared with `chat_result` (the latter keeps its signature and calls it), so `strip_think`, `length` → `ProviderOutputTruncated(usage)`, JSON parsing and `ProviderOutputInvalid` are the same code as today. Reasoning deltas (`reasoning_content`) count as events but not as `received_chars`.

### 3.7 `app/providers/recording.py`, `hub.py`

- `RecordingCompletion.complete` and `_CompletionProxy.complete` forward `on_progress`. The ledger logic is untouched: a cut stream raises with no `usage` attribute → null tokens (R2.7); a truncated one carries its usage.
- `build_clients`: tutor `_role_client(config.tutor, settings.request_timeout_s)`; authoring and transcription `_role_client(role, settings.authoring_first_event_timeout_s, StreamLimits(settings.authoring_first_event_timeout_s, settings.authoring_idle_timeout_s))`. `_role_client` passes `limits` to the adapters.
- The Realtime client is built through `make_client`, so it loses its retries too.

### 3.8 `app/domain/errors.py`

```python
@dataclass(frozen=True)
class CallDiagnostics:
    error_class: str
    reason: str
    status_code: int | None
    elapsed_ms: int
    idle_ms: int
    received_chars: int
    provider_code: str | None = None
    request_id: str | None = None
```

Set as the attribute `diagnostics` on the domain error `failure()` returns (and on `ProviderOutputTruncated` / `Invalid`). Nothing else in `domain` changes; no new message key (R6 is logs only).

### 3.9 `app/services/authoring/progress.py` (new)

```python
class LiveProgress:
    def __init__(self, chapters: ChapterRepository, chapter_id: str, settings: Settings, extra: dict) -> None
    def for_call(self, stage: Stage, attempt: int, *, counting: bool) -> ProgressCallback
    async def begin_call(self, stage, attempt) -> None      # zero the count, progress_at = now, awaited
    async def settle(self) -> None                          # await the writer's last write
    def close(self) -> None                                 # cancel a pending write (task cancelled/timeout)
```

- The callback returned by `for_call` (a) hands `snapshot.received_chars` (`counting=True`) or nothing (`counting=False`: transcription batches, several in flight, their count is the page count) to the **coalescing writer**; (b) logs `provider_call_progress` when 30 s (`authoring_progress_log_s`) have passed since this call's last log, with `{**extra, stage, attempt, received_chars, elapsed_ms, idle_ms}`.
- Coalescing writer: holds only the latest value; one `asyncio.Task` drains it through `asyncio.to_thread(chapters.set_received, chapter_id, chars)` (`chars=None` → touch only). A failed write is logged (`authoring_progress_not_stored`, exception class) and ignored. At most one write in flight; snapshots arrive at most once per second.
- `begin_call` is called by the agent before each provider call of the pack and curriculum stages (including each repair attempt) and before each transcription batch call (`counting=False` there: it only touches `progress_at`).

### 3.10 `app/services/authoring/agent.py`

- `run(..., progress: LiveProgress | None = None)`. The existing `on_progress(stage, pages_done)` and `on_transcribed` callbacks are kept.
- `_call(stage, …, attempt)` and `_transcribe` call `await progress.begin_call(...)`, pass `on_progress=progress.for_call(...)` to `complete()`, and `await progress.settle()` in `finally` so the last count lands before the stage log.
- `_provider_failure(stage, usage, exc) -> AuthoringFailed`: `ProviderTimeout` → code `timeout`; every other `PROVIDER_ERRORS` member → `provider`; `from exc` so the runner can read `exc.__cause__.diagnostics`. `FailureCode` gains `"timeout"`. The `AuthoringFailed("provider", …)` raise sites in `_transcribe` and `_call` use it.
- Repairs and the transcription batch retry are unchanged: each is a separate `complete()` call, a separate ledger row, logged as `authoring_stage` with its attempt.

### 3.11 `app/services/authoring/runner.py`

- `_execute` builds `LiveProgress` and passes it to `agent.run`; `finally: live.close()`.
- `except AuthoringFailed as exc` → `_fail(..., diagnostics=getattr(exc.__cause__, "diagnostics", None))`.
- `except TimeoutError` (the run ceiling) → `_fail(..., reason="run_ceiling")`.
- `_fail` adds to `authoring_failed`: `error_class`, `reason`, `status_code`, `idle_ms`, `received_chars`, `provider_request_id` when diagnostics exist; only `reason` for the ceiling. `detail` is unchanged (class name or `run timeout`).
- `_execute` keeps `asyncio.timeout(authoring_timeout_s)` around the run; its default is 1800.

### 3.12 Settings (`app/config.py`)

| Setting | Default | Constraint |
|---|---|---|
| `AUTHORING_IDLE_TIMEOUT_S` | 60 | ≥ 5 |
| `AUTHORING_FIRST_EVENT_TIMEOUT_S` | 180 | ≥ 10 |
| `AUTHORING_PROGRESS_LOG_S` | 30 | ≥ 5 |
| `AUTHORING_TIMEOUT_S` | 1800 (was 900) | ≥ 10 |
| `AUTHORING_CALL_TIMEOUT_S` | `None` (deprecated) | field kept `float | None`; `create_app` logs one WARNING `setting_ignored` with `setting="AUTHORING_CALL_TIMEOUT_S"` when it is set |

`work_reading` and the admin test use the authoring/transcription clients, so they get the same limits.

## 4. Data models

### 4.1 Migration `0011_authoring_live_progress`

`chapters`: `authoring_received_chars INTEGER NOT NULL DEFAULT 0`, `authoring_progress_at DATETIME(timezone) NULL` (SQLite batch mode, as `0004`). `ChapterRow` (SQLAlchemy) gets both; `test_head_matches_the_models` pins the pair. `ChapterRecord` gets `authoring_received_chars: int = 0` and `authoring_progress_at: datetime | None = None`; `_CHAPTER_LIGHT` and `_chapter_light` read them.

### 4.2 Repository (`ChapterRepository`)

| Method | Change |
|---|---|
| `set_progress(chapter_id, stage, pages_done=None)` | also sets `authoring_received_chars=0`, `authoring_progress_at=now` (a stage starts) |
| `set_received(chapter_id, chars: int \| None)` | new: `UPDATE … SET authoring_progress_at=now[, authoring_received_chars=chars] WHERE id=… AND authoring_state='generating'` |
| `begin_authoring` | sets both to `0` / `now` with the other `generating` values |
| `_adopt(idle=True)`, `finish_failed`, `RunRepository.fail_orphans` | set `authoring_received_chars=0`, `authoring_progress_at=NULL` |

`store_transcription` already moves the stage to `pack`; it also zeroes the count.

### 4.3 DTO (`app/api/schemas/courses.py`)

`ChapterRow` gains:

```python
authoring_received_chars: int       # 0 unless generating in the pack or curriculum stage
authoring_quiet_s: int | None       # seconds since the last progress write; None unless generating
```

`_rows(chapters, records, locale)` computes `now = utcnow()` once and `quiet = max(0, int((now - chapter.authoring_progress_at).total_seconds()))` when `authoring_state == "generating"` and `authoring_progress_at` is set. `ChapterContent` is unchanged (the preparation card reads the course row). `frontend/src/lib/tutor/types.ts` `ChapterRow` mirrors both fields.

### 4.4 Log schema

| Line | Level | Fields |
|---|---|---|
| `provider_call_progress` | INFO | run attribution (`run_id`, `user_id`, `course_id`, `chapter_id`), `stage`, `attempt`, `received_chars`, `elapsed_ms`, `idle_ms` |
| `provider_call_done` | INFO | `role`, `model`, `provider_host`, scope attribution, `elapsed_ms`, `time_to_first_event_ms`, `received_chars`, `events`, token counts |
| `provider_call_failed` | WARNING | `role`, `model`, `provider_host`, scope attribution, `error_class`, `reason`, `status_code`, `provider_code`, `provider_request_id`, `elapsed_ms`, `idle_ms`, `received_chars`, `events` |
| `authoring_failed` | WARNING | existing fields + `error_class`, `reason`, `status_code`, `idle_ms`, `received_chars`, `provider_request_id` |
| `authoring_progress_not_stored` | WARNING | attribution, `error` (class) |
| `setting_ignored` | WARNING | `setting` |

The provider-level lines take attribution from `current_scope()` (`user_id`, `course_id`, `chapter_id`, `correlation_id` — the run id for authoring); outside a scope those fields are absent.

## 5. Frontend

- `types.ts`: `ChapterRow` + `authoring_received_chars: number`, `authoring_quiet_s: number | null`. Test fixtures that build a `ChapterRow` gain the two fields (`featured-chapter.test.ts`, `chapter-page.test.tsx`, `courses-en.test.tsx`, `english-sweep.test.tsx`).
- `chapter-row.tsx`:
  - `preparingLabel(row)`: transcription → `chapter_reading_pages` (unchanged); `pack` → `chapter_writing_pack`; `curriculum` → `chapter_building_path`; other/null → `chapter_preparing`.
  - `preparingDetail(row)`: `preparingLabel` plus, for `pack`/`curriculum` when `authoring_received_chars > 0`, `m.chapter_received_chars({ count: formatInt(n) })` (`formatInt` from `lib/i18n-format.ts`, the interface locale).
  - `const SLOW_AFTER_S = 45`; `isSlow(row)`: `authoring_state === "generating"` and `authoring_quiet_s != null && >= SLOW_AFTER_S`.
- `chapter-state-card.tsx`: the hint line shows `preparingDetail(row)` for every stage; for `pack`/`curriculum` the existing generic hint follows. When `isSlow(row)`, a second paragraph `m.chapter_slow()` in the same `aria-live="polite"` region. No bar is added: the count is text.
- The course page badge keeps `preparingLabel(row)` (short, no count); its `chapter_status_new_version` suffix works with the new labels.
- Messages (both files, parity-checked by `npm run i18n:check`): `chapter_writing_pack` « Rédaction du chapitre… » / "Writing the chapter…", `chapter_building_path` « Construction du parcours… » / "Building the path…", `chapter_received_chars` « {count} caractères reçus » / "{count} characters received", `chapter_slow` « Toujours en cours, le service est lent. » / "Still working, the service is slow."
- Polling stays `GENERATING_POLL_MS`. No new query.

## 6. Error handling

| Situation | Behaviour |
|---|---|
| No event before `AUTHORING_FIRST_EVENT_TIMEOUT_S` (including the wait for response headers) | `StreamTimeout("first_event_timeout")` → `ProviderTimeout` → authoring `timeout` |
| Silence of `AUTHORING_IDLE_TIMEOUT_S` after an event | `idle_timeout`, same path |
| SDK `APITimeoutError` / `APIConnectionError` / HTTP status | domain error as today (`ProviderTimeout`, `ProviderUnavailable`, `ProviderRateLimited`, …), no retry; reason in the log |
| `response.failed` / `error` event, or the stream ends without a completion event | `StreamBroken` → `ProviderUnavailable` (or the code the event names), reason `error_event` / `stream_ended` |
| `response.incomplete` / `finish_reason == "length"` | `ProviderOutputTruncated(usage)` as today |
| Server refuses `stream` | `ProviderRejectedRequest`, reason `stream_unsupported`; the admin test and the log say so; no fallback |
| Callback raises | swallowed, logged (class), the stream continues |
| Progress write fails | logged, ignored; the run continues |
| Task cancelled mid-stream | `async with raw` closes the response; `CancelledError` propagates; the ledger row is `cancelled`; `LiveProgress.close()` cancels a pending write |
| Run ceiling | unchanged `TimeoutError` → `timeout`, log `reason="run_ceiling"` |
| Authoring failure codes | `provider` → `timeout` for `ProviderTimeout`; messages unchanged |

The student retries through « Réessayer »; nothing re-sends a request on its own.

## 7. Testing strategy

Offline, no network, no test waits more than a few tens of milliseconds (timeouts of 20–50 ms against scripted async iterators).

- `tests/unit/test_streaming.py` (new): `consume` with scripted events — normal end, first-event timeout, idle timeout after events (a slow-but-flowing stream is not cut), reasoning/unknown events reset the clock, throttled snapshots (1 per interval + final), a raising callback does not break the stream, `handle` raising `StreamBroken`, the stream is closed on timeout, error and cancellation (sentinel `aclose` flag), no task left behind.
- `test_provider_client.py`: `max_retries == 0`; `make_client` has no `max_retries` parameter; `test_openai_probe.py` adjusted.
- New test: every client the hub builds (`build_clients` over fake connections for both API styles, voice on) has `max_retries == 0`.
- `test_openai_adapter.py`: `complete()` request equals today's plus `stream=True` (a pinned key set); text assembled from deltas equals `output_text`; empty `output_text` falls back to deltas; `incomplete` → truncated with usage; `failed`/`error` event → unavailable with reason; no completion event → `stream_ended`; JSON mode and schema parse as before; the old non-streamed `complete` tests move to a scripted stream.
- `test_openai_chat_adapter.py`: chunks → same `CompletionResult` as `chat_result` on the whole text (think-stripping, JSON extraction, `length`), `include_usage` sent, the `max_tokens` fallback still works, missing finish reason → `stream_ended`, reasoning deltas reset idle but add no chars.
- Diagnostics: `classify` table (one case per reason), the message is never in the log (`caplog` sweep with a poisoned message), `provider_call_failed` carries scope attribution, `provider_call_done` fields.
- `test_authoring_agent.py` / `test_authoring_runner.py` with `FakeCompletion` extended: `on_progress` accepted and, when `snapshots=[…]` is set, called with them. Cases: byte-identical output with and without progress (R7.1); the count is written per snapshot and zeroed at each stage and repair; transcription batches only touch `progress_at`; a failed write does not fail the run; `ProviderTimeout` → run code `timeout`, `ProviderUnavailable` → `provider`; `authoring_failed` carries `error_class`/`reason`; a run ceiling logs `run_ceiling`; cancellation closes the writer; `provider_call_progress` logged at the configured interval (monkeypatched to 0) and never carries text (extend `test_logs_never_carry_content`).
- Repository / migration: `0011` upgrade from `0010` keeps rows with `0`/`NULL`; `set_received` only while generating; adopt, failure and orphan sweep clear both; `test_head_matches_the_models`.
- Integration (`test_courses_endpoint.py`): the course detail of a generating chapter shows `authoring_received_chars` and `authoring_quiet_s`, `0`/`null` otherwise; another student's chapter is still a 404.
- `test_usage_scopes.py` / `test_privacy_ledger.py`: streamed calls still produce exactly one row; a cut stream has null tokens; no content column or log field.
- `test_config.py`: new settings, bounds, defaults; `AUTHORING_CALL_TIMEOUT_S` accepted with the warning.
- Layering (`test_layering.py`): `streaming.py` imports no `openai`; `_errors.py` stays the only place that does.
- Frontend (vitest): `preparingLabel` per stage; `preparingDetail` formats the count per interface locale; the slow notice appears at 45 s and not before, only while generating; French and English card snapshots; the English sweep passes; `i18n:check`.
- `scripts/smoke.py` (real calls, run by hand): still fails on a cache miss; the stream request keeps the cache breakpoint.

## 8. Performance

- No extra provider request; streaming adds per-event Python work proportional to events (hundreds to a few thousand per call).
- Progress: ≤ 1 snapshot per second per call; ≤ 1 DB write in flight per run, off the loop. With `AUTHORING_MAX_CONCURRENT` = 4 the worst case is four small `UPDATE`s per second against SQLite, each guarded by `authoring_state = 'generating'`.
- Memory: the delta list plus the joined text, bounded by `AUTHORING_MAX_OUTPUT_TOKENS` (32 000 tokens ≈ 130 KB).
- The 3-second poll response grows by two integers.

## 9. Security and privacy

- Snapshots, stored progress and log fields are counts, durations, a stage and class names. The pack, transcription and any partial text never leave the adapter.
- Exception messages are inspected only for the `stream` test (R6.2) and never logged; provider error `code` and `x-request-id` are logged (short strings, truncated to 64 characters).
- The key, the redirect policy and the host are unchanged. `authoring_received_chars` and `authoring_quiet_s` ride on the ownership-checked course routes.
- `test_privacy_ledger.py` sweeps the new log lines and the ledger rows; no new ledger column.

## 10. Monitoring and observability

- `provider_call_progress` every 30 s while a call runs shows a live generation, its pace (`received_chars / elapsed_ms`) and a stall (`idle_ms` growing).
- `provider_call_failed` replaces guessing: the next timeout is classified (`first_event_timeout`, `idle_timeout`, `http_status`, …) with elapsed and idle time and the provider's request id for a support ticket.
- `provider_call_done` gives time to first event and characters per call, so reasoning latency is visible per model.
- Logs already carry `ts` (UTC); `docker logs` shows all lines of a run in order.
- Documentation to update with the implementation: `documentation/authoring.md` (provider call, timeouts, progress, logs, states table, failure table), `ai-providers.md` (streamed `complete`, no retries, limits per role), `ai-usage.md` (cut streams, null tokens), `running-locally.md` (settings), `docker.md` (log lines), `index.md` if a file is added.

## 11. Differences from the requirements

| Requirement | Design |
|---|---|
| R5.1 `authoring_updated_at` | `authoring_quiet_s` in the DTO (server-computed); the timestamp stays a column. Avoids browser clock skew. |
| R5.3 step indicator « étape 2/3 » | Stage wording only (« Rédaction du chapitre… », « Construction du parcours… »). A text edit or a retry starts at the pack stage, so a step number would lie. |
| R5.1 content DTO | Only `ChapterRow` (the course routes) carries the fields; the preparation card reads that row. |
| R3.5 / NFR 4.1.2 tutor on the shared timer | The tutor keeps the SDK read timeout (`REQUEST_TIMEOUT_S`), which already bounds the silence between chunks; only retries and failure logging change. |
| R3.6 httpx `connect`/`read` | One float per role (the first-event allowance) as backstop; the precise deadlines live in `consume`. |
| R6.1 reason list | Adds `transport_timeout` (SDK/httpx timeout) and `error_event` (a `failed`/`error` event) and `other`. |
| R1.4 / R6.4 `provider` or `timeout` | `ProviderTimeout` → `timeout`; the rest → `provider`. |
| R4.2 stage/attempt on the progress line | Logged by `LiveProgress` (the agent knows stage and attempt); `provider_call_failed` / `done` carry the scope's attribution only. |
