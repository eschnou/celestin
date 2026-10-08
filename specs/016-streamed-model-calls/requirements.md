# 016 — Streamed model calls: no automatic retry, idle timeout, live authoring progress

## 1. Introduction

Observed failure (8 October 2026): three authoring runs (`4bf7a18d`, `aec9547e`, `34c48cb9`; 26 and 42 pages) ended `timeout` at the pack stage after 1 400 to 1 500 s. Transcription was fine (100 s). The pack stage is one non-streamed `responses.create` call that must write about 25 000 tokens. The log shows `openai._base_client: Retrying request in 0.47 s` twice before the call returned: the SDK client (`providers/_client.py`, `max_retries=2`) restarted the whole generation after a transport failure or a 5xx, each attempt billed and silent. Nothing in the log said why, how long each attempt lasted, or how far a generation had got. The student saw « En préparation… » for 25 minutes, then a timeout.

Today:

| Aspect | State |
|---|---|
| Retry | `make_client(max_retries=2)` for every client except the connection probe. The SDK retries connection errors, timeouts, 408, 409, 429 and ≥500, invisibly, and a retried generation restarts from zero. |
| Call shape | The tutor streams. `complete()` (authoring, transcription, work reading, admin test) is a single non-streamed request on both adapters (`openai_responses.py`, `openai_chat.py`). Nothing arrives until the answer is whole. |
| Timeouts | `AUTHORING_CALL_TIMEOUT_S` (300) is the httpx timeout of the authoring and transcription clients; `AUTHORING_TIMEOUT_S` (900 by default) bounds the whole run. A slow-but-progressing generation and a dead connection look the same. |
| Progress | The chapter row has `authoring_stage` and `pages_done` / `page_count`, shown only while transcribing (« Lecture des pages… n/N »). From the pack stage on, the student sees a static « En préparation… ». |
| Failure logs | `authoring_failed` has a code and totals. The provider failure itself (exception class, elapsed time, attempt) is not logged. |

This spec: (1) removes every automatic transport retry of a call that generates tokens, so the student is the one who retries; (2) makes `complete()` stream, on both adapters, and logs progress while a call runs; (3) replaces the per-call total wait with an idle timeout; (4) shows the student real progress of the pack and path stages; (5) logs the exception class and elapsed time of every provider failure.

Vocabulary:

- **Transport retry** — the SDK re-sending a request after a failure, without the application's knowledge. Distinct from a **repair**: the agent's own bounded, logged, content-driven second call (spec 005 R3, spec 006 R3.2), which stays.
- **Idle time** — time since the last event of a streamed response, of any kind (text delta, reasoning delta, lifecycle or usage event).
- **Received** — the count of output characters streamed so far in the current call. A count, never content.
- **Stage** — `transcription`, `pack`, `curriculum` (spec 006).

Scope:

- Provider clients: retry setting, a streamed `complete()` on the Responses and Chat adapters, idle timeout, progress callback, failure logging.
- The recording wrapper (spec 015) for streamed completions.
- The authoring agent and runner: timeouts, progress reporting, storing live progress.
- Chapter row DTO, course/chapter polling, the preparation card and course page, French and English strings.
- Tests, documentation.

Out of scope:

- Streaming any text to the student. The partial pack or transcription is never shown or stored.
- Resuming a generation after a mid-stream failure; a failed call is discarded whole.
- Changing the repair loops (`AUTHORING_MAX_REPAIRS`, the transcription batch retry and page split), prompts, models, batch sizes or concurrency.
- Splitting a large chapter into several pack calls.
- Server-push of progress (SSE, WebSocket): the existing 3-second polling stays.
- Prices, budgets or new fields in the usage ledger beyond R2.4 and R6.5.
- The tutor's turn pipeline other than the retry setting (R1) and the idle timeout inherited from the shared client.

## 2. Alignment with product vision

| Brief v2.0 | How this spec serves it |
|---|---|
| §8 Cost control | No hidden double or triple billing of a long generation; every attempt is one the student chose to start. |
| §6 Authoring: the lesson opens a few minutes after the drop | A slow provider is told apart from a dead one; a failing run fails in seconds to minutes, not at the end of a 25-minute wait. |
| Interface is a lesson, calm and legible | The student sees that the work is moving, and at which stage, instead of a frozen message. |
| §8 Privacy | Progress is counts and a stage; logs and the progress fields never carry content (as spec 005 NFR 4.3.4, spec 015 R7). |
| Spec 014 (any OpenAI-compatible provider) | The Chat adapter streams too; the behaviour does not depend on OpenAI-only events. |

No deviation from `CLAUDE.md` or an earlier spec. Spec 015's ledger and usage scopes, spec 014's hub and spec 010's interface language are reused.

## 3. Requirements

### R1 — No automatic transport retry of a generating call

**As** the operator, **I want** no request that generates tokens to be re-sent automatically, **so that** I never pay twice for one request without anyone choosing it.

Acceptance criteria:

1. Every client built by `make_client` has `max_retries=0`: the tutor (Responses and Chat), authoring, transcription, the admin test and the Realtime secret mint. There is no parameter that raises it for a generating role.
2. The httpx layer does not retry either (no transport with `retries`).
3. A failed call surfaces to its caller as the existing domain error (`ProviderTimeout`, `ProviderRateLimited`, `ProviderUnavailable`, …) on the first failure. A 429 is not waited out.
4. Authoring: a provider failure fails the run with code `provider` or `timeout` (existing codes and messages); the student's « Réessayer » is the only retry. The repair loops (out of scope, §1) are unchanged and still count each call separately in the ledger.
5. The tutor turn: a provider failure ends the turn with its existing `error` event; the student resends. No behaviour added.
6. `openai._base_client` "Retrying request" lines no longer occur; a test asserts `max_retries == 0` on every client the hub builds.

### R2 — `complete()` is streamed

**As** the operator, **I want** authoring and transcription calls to be streamed, **so that** a live generation can be told from a dead connection and measured while it runs.

Acceptance criteria:

1. `CompletionClient.complete()` keeps its signature and its result (`CompletionResult`: text, parsed `data`, usage) and gains an optional `on_progress` callback (R4.1). Callers that pass none behave as before. The Responses adapter requests `stream=True` and consumes the raw event stream (as `stream()` does); the Chat adapter requests `stream=True` with `stream_options={"include_usage": True}`.
2. The streamed text is assembled into the same result a non-streamed call gave: `output_text`, JSON parsing and `extract_json` for `structured: json`, `strip_think` for the Chat adapter, the same `ProviderOutputTruncated` (`status == "incomplete"`, `finish_reason == "length"`) and `ProviderOutputInvalid` carrying the usage block.
3. Usage is read from the final event. A stream that ends without a completion event, or ends `failed`, is `ProviderUnavailable`.
4. A server that does not support streaming for the call is a `ProviderUnavailable` with a distinct log reason (R6), not a silent fallback to a non-streamed request (a fallback would bring back the silent wait).
5. Request bodies are otherwise unchanged (instructions, cache breakpoint, schema, `store=False`, effort, output limit). A test pins that the only differences from today's request are the stream flags.
6. Work reading and the admin test, which call `complete()` too, go through the same path with no callback.
7. The recording wrapper (spec 015) still writes one row per call: `ok` with the usage block; `truncated` with the usage of the exception; `failed` with the code; `cancelled`. For a stream cut before its final event the tokens are `null` (not reported); no estimate is stored.

### R3 — Idle timeout instead of a total wait

**As** the operator, **I want** a call to be abandoned when the provider stops sending, not when a fixed total elapses, **so that** a long healthy generation is allowed to finish and a dead one is dropped quickly.

Acceptance criteria:

1. A streamed `complete()` raises `ProviderTimeout` when no event has arrived for `AUTHORING_IDLE_TIMEOUT_S` (new setting, default 60, minimum 5). Any event resets the clock, reasoning events included.
2. Before the first event the allowance is `AUTHORING_FIRST_EVENT_TIMEOUT_S` (new setting, default 180, minimum 10): a connection and a reasoning model's first output can take longer than a pause between tokens.
3. `AUTHORING_CALL_TIMEOUT_S` is removed as the call's limit: it no longer bounds a call's total duration. Its documentation line and its use in `hub.build_clients` are replaced by R3.1 and R3.2. An environment that still sets it is accepted and ignored with one startup warning log.
4. `AUTHORING_TIMEOUT_S` stays as the absolute ceiling of a whole run, transcription included, so that a stream that trickles forever cannot hold a worker. Its default rises to 1 800. It stays editable; a run that hits it fails `timeout` as today.
5. The tutor client keeps its own `REQUEST_TIMEOUT_S` (120) as its idle limit between events; the setting is documented as an idle limit.
6. The httpx client of a role has `connect` = the first-event allowance and no `read` limit beyond what R3.1–3.2 enforce in the adapter, so that a single mechanism decides.
7. A timeout aborts the request (the stream is closed, the connection released) so that no worker keeps reading.
8. The semaphore (`AUTHORING_MAX_CONCURRENT`) is still held for the duration of the run, as today.

### R4 — Progress reported while a call runs

**As** the operator and the student, **I want** to know how far a long generation has got, **so that** a stalled run is visible and a healthy one is reassuring.

Acceptance criteria:

1. The `on_progress` callback of `complete()` receives a snapshot `(received_chars, events, elapsed_ms)` at most once per second and once at the end. It never receives text.
2. Each streamed call logs, at INFO, `provider_call_progress` every `AUTHORING_PROGRESS_LOG_S` (new setting, default 30, minimum 5) while it runs, with the attribution fields of the run (`run_id`, `user_id`, `course_id`, `chapter_id`, `stage`, `attempt`), `received_chars`, `elapsed_ms`, `idle_ms`. No other line is added per event.
3. The agent maps the snapshots of the pack and curriculum stages to the chapter's live progress (R5). A transcription batch reports through its existing page count; it also logs R4.2 lines.
4. Progress writes are throttled (R4.1) and never block the stream: a failing write is logged and ignored.
5. Logs and stored progress contain counts and a stage only, never text (`test_privacy_ledger.py`-style sweep).

### R5 — The student sees real progress

**As** a student waiting for my chapter, **I want** to see which step it is on and that it is advancing, **so that** I know whether to wait or to retry.

Acceptance criteria:

1. The chapter row (`ChapterRow` and the content DTO that carries `authoring_*`) gains `authoring_received_chars` (integer, 0 outside a run or outside the pack and curriculum stages) and `authoring_updated_at` (the time of the last progress write, ISO 8601, null outside a run). The existing `authoring_stage`, `pages_done`, `page_count` are unchanged.
2. While `authoring_state == "generating"` and the stage is `pack` or `curriculum`, `received_chars` grows as the stream delivers, within the 3-second polling of the course and chapter queries. It resets to 0 when a stage starts and when a repair attempt starts.
3. The preparation card (« Préparation du chapitre ») and the chapter row on the course page show, per stage:
   - transcription: « Lecture des pages… n/N » (unchanged);
   - pack: « Rédaction du chapitre… » with a step indicator (step 2 of 3) and the amount received as a count of characters (« 12 400 caractères reçus »), formatted in the interface language;
   - curriculum: « Construction du parcours… », step 3 of 3, with its count;
   - a repair attempt is shown as the same stage, count restarted; the student sees no attempt number.
   The English equivalents exist in `messages/en.json`; strings go through paraglide (spec 010).
4. No percentage or time estimate is displayed: the total output is not known in advance.
5. When the last progress write is older than 45 s while the chapter is still `generating` (a stalled provider before the idle timeout fires), the card adds « Toujours en cours, le service est lent. » in `aria-live="polite"`. It disappears when progress resumes.
6. The counts reach the browser only through the existing authenticated, ownership-checked routes; another student's chapter is a 404 as today.
7. A restart leaves nothing stale: startup already fails every `generating` chapter; the new fields are cleared there.
8. Accessibility: the progress text is a text node, not only a visual bar; a bar, if any, has `role="progressbar"` with `aria-valuetext` and no fake `aria-valuenow`.

### R6 — Every provider failure is logged with its class and duration

**As** the operator, **I want** each provider failure logged with its exception and how long the call lasted, **so that** the next timeout can be explained from the log alone.

Acceptance criteria:

1. A failed `complete()` or `stream()` logs one WARNING `provider_call_failed` with: `role`, `model`, `provider_host`, `error_class` (the SDK exception class name, e.g. `APITimeoutError`, `RateLimitError`, `APIStatusError`), `status_code` when the provider answered, `reason` (a fixed token: `idle_timeout`, `first_event_timeout`, `http_status`, `connection`, `stream_ended`, `stream_unsupported`, `truncated`, `invalid_output`), `elapsed_ms`, `idle_ms`, `received_chars`, and the attribution fields of the current usage scope when there is one.
2. The message of the exception is never logged (it can quote a request); the provider's error `code` and `request_id` (the provider's, e.g. `x-request-id`) are, when present.
3. The domain error raised to callers is unchanged (R1.3).
4. `authoring_failed` gains `error_class` and `reason` of the underlying provider failure for codes `provider` and `timeout`, and `idle_ms` of the last call.
5. The ledger row of the failed call keeps its existing columns; `error_code` carries the domain code as today. No new ledger column.
6. A successful streamed call logs a single INFO `provider_call_done` with `elapsed_ms`, `time_to_first_event_ms`, `received_chars`, and the usage block's token counts, at the same level of detail as `authoring_stage`. No duplicate of the `httpx` line is required; the `httpx` logger stays at INFO.

### R7 — Behaviour that must not change

**As** a maintainer, **I want** the observable output of authoring and the tutor preserved, **so that** the change is a transport change only.

Acceptance criteria:

1. With a scripted fake stream carrying the same text, the agent produces byte-identical packs, indexes and curricula as with the non-streamed fake; the `render` golden hashes and all existing tests that use `fake_completion.py` pass unchanged.
2. The cached prefix is unaffected: request instructions, cache breakpoint and ordering are identical (`smoke` still fails on a second turn with zero cached tokens).
3. Limits (`AUTHORING_*` quotas, concurrency, per-student busy), error codes and their French and English messages are unchanged.
4. A run cancelled mid-stream closes the stream and records `interrupted` as today; the ledger row is `cancelled`.

## 4. Non-functional requirements

### 4.1 Architecture

1. Only `app/providers/` imports `openai`; the streamed `complete()`, the idle timer and the failure log live there. The agent talks to `CompletionClient` and receives progress through a plain callback; the progress callback type is defined in `providers/base.py` with no SDK types.
2. One shared stream-consumption helper for the idle and first-event timers, used by both adapters; the tutor's `stream()` uses the same timer rather than a second implementation.
3. The recording wrapper (spec 015) sits outside the streaming logic and is the only writer of ledger rows; a progress callback never writes the ledger.
4. Live progress is carried by the existing chapter row (a migration adds the two columns, nullable or defaulted, SQLite batch mode) or an equivalent store chosen by the design; it must be correct across the runner's thread and the request threads and must not add a table.
5. Tests drive streams from a scripted fake (events with delays on a fake clock); no test sleeps for real seconds.

### 4.2 Performance

1. Streaming adds no measurable latency to a call's completion and no extra provider request.
2. Progress writes to the database are at most one per second per run and run off the event loop (`asyncio.to_thread`, as `on_progress` does today).
3. Memory per call is bounded by the output limit (`AUTHORING_MAX_OUTPUT_TOKENS`); the assembled text is kept once.
4. The 3-second polling cost is unchanged (the two new fields ride on the existing response).

### 4.3 Security and privacy

1. No prompt, transcription, pack, curriculum or partial output in any log line, progress field or ledger row. Counts, durations, stage and class names only.
2. Exception messages are not logged (R6.2); the API key never appears.
3. Redirects remain disabled and the connection's host is still the only destination.
4. A student can read only the progress of their own chapters (existing ownership checks).

### 4.4 Reliability

1. A dead connection is abandoned within `AUTHORING_IDLE_TIMEOUT_S` (or the first-event allowance) and fails the run in that time; a healthy long generation completes within the run ceiling.
2. A timeout, a cancelled task and a mid-stream error all close the stream; no task or socket outlives the call (tested).
3. A provider that sends keep-alive or reasoning events resets the idle clock; one that sends nothing for the allowance is dropped. Neither depends on OpenAI-only event names: unknown events count as activity.
4. A failed progress write never fails the run.
5. A run's tokens and cost are still recorded when the stream fails after partial output, as far as the provider reported them; otherwise as « not reported ».

### 4.5 Usability

1. French by default, English by interface choice; all new strings in both catalogs (parity test).
2. The card's wording is calm: no error colour while generating; the slow notice is informational.
3. Numbers are formatted by locale (`Intl.NumberFormat` with the interface locale), never the course language.

### 4.6 Observability and documentation

1. Update `documentation/authoring.md` (provider call, timeouts, progress, logs, failure table), `documentation/ai-providers.md` (streamed `complete`, no retries, idle timeout), `documentation/ai-usage.md` (streamed calls, cut streams have null tokens), `documentation/running-locally.md` (settings table), `documentation/docker.md` (log lines), and `documentation/index.md` when a file is added.
2. `specs/index.md` lists this spec.
