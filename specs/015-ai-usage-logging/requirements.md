# 015 — AI usage logging: every model call recorded per user, viewed by the administrator

## 1. Introduction

Today usage data is partial and scattered:

| Call | Where it is recorded now |
|---|---|
| Tutor turn (parcours, discussion) | A `turn_complete` log line. The usage of a turn with tool rounds is the **last round's only** (`tutor_service.py` overwrites `usage` on each `Completed`). Not in the database. |
| Authoring and document transcription | Summed per run in `authoring_runs` (tokens, ms, a price-estimated cost). No per-call row. |
| Photographed work (`work_reading.py`) | A `work_read` log line. |
| Dictation | A `dictation` log line. |
| Voice (Realtime) | `voice_usage`: one row per session, reported by the browser, cost estimated from environment prices. |
| Admin live test (`ai_test.py`) | A log line. |

This spec adds one **usage ledger** in the database: a row per provider call, linked to the user who caused it (and the course and chapter when known), holding only metadata: role, model, provider host, tokens, latency, status and, when the provider reports it, the cost. The administrator reads it in a new admin screen: the individual calls, and the totals per user.

Vocabulary:

- **Call** — one request to a provider: one streamed tutor round, one `complete`, one transcription of a recording. A tutor turn with tool rounds is several calls.
- **Role** — `tutor`, `authoring`, `transcription`, `voice` (spec 014). Dictation is recorded under `voice`: it runs on the voice role's speech model and connection.
- **Feature** — what the call was for: `tutor_turn`, `discussion_turn`, `authoring` (pack, curriculum, repair), `document_reading` (transcription stage), `work_reading`, `dictation`, `voice_session`, `ai_test`.
- **Reported cost** — an amount the provider put in its own usage block (OpenRouter's `usage.cost`, in credits, 1 credit = 1 USD). Nothing else is a cost here.
- **Correlation id** — the id grouping the calls of one unit of work: a tutor `turn_id`, an authoring `run_id`, a voice `session_id`.

Scope:

- The ledger table and its migration, a recorder at the provider boundary, the carrying of user, course, chapter and correlation id to it.
- `GET` routes for the admin and a « Consommation » (usage) screen: totals, per-user aggregates, the call list.
- Documentation.

Out of scope:

- **Prices.** No price per token is configured, stored or applied by the ledger. A cost is recorded only when the provider reports it; otherwise it is empty. The existing environment price settings and the `cost_estimate_usd` / `*_cost_usd` columns of `authoring_runs` stay as they are, unused by the ledger.
- Logging of any content (R7).
- Budgets, quotas, alerts, limits based on usage; the existing per-student rate limits stand.
- Charts, CSV export, per-student self-view, a purge or retention setting.
- Backfill: calls made before the migration are not reconstructed, except the existing `voice_usage` rows (R4.5).
- Changing the authoring runner's quotas or `authoring_runs`.

## 2. Alignment with product vision

| Brief v2.0 | How this spec serves it |
|---|---|
| §8 Cost control | The operator sees what each student's use actually costs, call by call, not only logs. |
| §8 Privacy: a student's courses, material and progress are visible only to them | The ledger holds no content; the admin screen shows no course or chapter name (R6.6). Usage rows follow the account: deleted with it (R2.4). |
| §10 Authoring cost per chapter | Authoring and transcription calls are individually visible with model, tokens and latency. |
| Spec 014 (any provider, per-role models) | The model and provider host are recorded per call, so a change of model or provider can be compared afterwards. Cost is shown only where the provider reports it; elsewhere the screen says so instead of guessing. |

No deviation from `CLAUDE.md` or an earlier spec. Spec 012's `admin` role and routes, spec 010's French and English interface, and spec 014's hub are reused.

## 3. Requirements

### R1 — One row per provider call

**As** the administrator, **I want** every call to a model recorded, **so that** nothing the application spends goes unseen.

Acceptance criteria:

1. A row is written for every call of: the tutor stream (each round of a turn, in parcours and discussion), `complete` for the authoring and transcription roles (documents, repair calls, retried attempts, work reading), a dictation recording, the live checks of the admin AI test, and a voice session (R4).
2. A call that fails, times out, is truncated, is refused by the provider or is cancelled (client disconnect, run timeout) also gets a row, with its `status` (`ok`, `failed`, `truncated`, `cancelled`) and, for `failed`, the application's own error code (`ProviderTimeout`'s code, etc.), never provider text.
3. A retried call is two rows, not one.
4. A row is written once per call, when the call ends. A tutor round cut by the browser closing the stream still produces its row (`cancelled`).
5. Row fields:
   - `id`, `created_at` (UTC, call start);
   - `user_id` (R2), `course_id`, `chapter_id` (nullable, R2.3), `correlation_id` (nullable);
   - `role`, `feature`, `model` (the name sent, as in force for that call), `provider` (host name of the connection's base URL, nothing else of the URL);
   - `status`, `error_code`;
   - `latency_ms` (request sent to last event or response received); `ttft_ms` (streamed calls only, else null);
   - `input_tokens`, `cached_tokens`, `output_tokens`, `reasoning_tokens` (nullable: null means the provider did not report it, which is not zero; a provider that reports no usage at all gives nulls);
   - `input_audio_tokens`, `output_audio_tokens` (voice sessions; null elsewhere);
   - `audio_seconds` (dictation and voice sessions; null elsewhere);
   - `cost_usd` (nullable; R3).
6. The token fields read the provider-neutral usage both adapters already produce (`token_counts` over the Responses-shaped dict); the Chat Completions adapter's `usage_dict` carries the cost through too (R3.2).
7. A tutor turn's multiple calls are never merged into one row, and the turn's own `usage` in the `TurnEnd` event and the `turn_complete` log line is corrected to the **sum** of the turn's rounds (it reports the last round's today).

### R2 — Linked to the user, the course and the chapter

**As** the administrator, **I want** each call tied to the account that caused it, **so that** I can attribute cost.

Acceptance criteria:

1. Every row has a `user_id`, a foreign key to `users.id`. A call with no user cannot be recorded: the code path that would make one is a defect, found by a test, not a null column.
2. The user is the account that made the request that led to the call: the student for a tutor turn, discussion, voice, dictation and work reading; the owner of the chapter for an authoring run, including its background stages after the request returned; the admin for an AI test.
3. `course_id` and `chapter_id` are set when the call belongs to a course or chapter (turns, discussions, voice sessions, authoring and transcription of a chapter, work reading on a course). They are nullable and are set to null (not cascaded) when the course or chapter is deleted, so deleting a chapter does not erase its cost from the user's totals. Dictation and AI tests carry none.
4. Deleting a user deletes their rows (`ON DELETE CASCADE`): the ledger never outlives the account. Nothing else deletes a row; there is no expiry, and data is kept until the user is deleted.
5. The user, the course, the chapter and the correlation id reach the recorder without changing the `LLMClient`, `CompletionClient` and `TranscriptionClient` protocol signatures that the offline fakes implement, or, if the design changes them, every fake is updated in the same change. The design chooses the mechanism; a call made without a context (a startup check, a script) is not recorded and is logged once at `debug`.
6. `scripts/smoke.py`, `probe.py` and the other scripts that run on chapter files and not on an account record nothing.

### R3 — Cost only when the provider reports it

**As** the administrator, **I want** a cost only when it is a real figure, **so that** the totals are never a guess.

Acceptance criteria:

1. `cost_usd` is filled only from a numeric cost in the provider's usage block of that call (OpenRouter: `usage.cost`). It is the amount as reported, stored as received at call time and never recomputed afterwards: the stored figure is locked.
2. Both adapters read the field: the Responses adapter keeps it from the usage payload, the Chat adapter's `usage_dict` passes it through. A non-numeric, negative or absent value gives null.
3. When the provider reports no cost (OpenAI, Groq, a local server) `cost_usd` is null. The application applies no price, from `Settings` or from anywhere else, to a ledger row.
4. Null is not zero: aggregates sum the reported costs and always state how many of the calls in the aggregate reported one (R6.3, R6.4).
5. The unit is recorded as USD on the assumption that a provider reporting a cost reports it in USD (OpenRouter's credits are USD). The documentation states the assumption and names the providers known to report a cost.

### R4 — Voice sessions and dictation

**As** the administrator, **I want** voice and dictation in the same ledger, **so that** the per-user total is complete.

Acceptance criteria:

1. A voice session is one row (`feature = voice_session`, `correlation_id` = the session id): the Realtime API is driven by the browser, so the backend sees a session, not its calls. The row carries the six token totals folded into `input_tokens` / `cached_tokens` / `output_tokens` (text and audio together) and the audio shares in `input_audio_tokens` / `output_audio_tokens`, plus `audio_seconds` from the reported duration and `latency_ms` null.
2. `POST /api/voice/usage` writes the ledger row for the authenticated student, as it writes `voice_usage` today; it still never fails the caller (a beacon cannot retry).
3. The voice figures are **client-reported**; the screen does not mark them differently, but the documentation says so, and the values are bounded by validation (non-negative integers within a sanity limit, as `VoiceUsageReport` does) so a forged report cannot produce a negative or absurd total.
4. A dictation is one row (`feature = dictation`) with `audio_seconds` from the recording's duration, capped at `DICTATION_MAX_S` as today, tokens null, `cost_usd` null (the transcription endpoint reports none), and `latency_ms`.
5. The existing `voice_usage` rows are carried into the ledger by the migration (`feature = voice_session`, `status = ok`, `cost_usd` null: their cost was an environment-price estimate, not a reported one). Whether `voice_usage` is then dropped or left is the design's decision; no data is shown twice.

### R5 — Never in the way of the student

**As** a student, **I want** my lesson unaffected by the bookkeeping, **so that** logging cannot break or slow it.

Acceptance criteria:

1. A failure to write a row (database locked, constraint) never fails, delays or alters the call, the turn, the run or the response: it is logged (`ai_usage_not_stored` with the error class and the role) and swallowed.
2. Rows are written off the event loop (thread pool, like the other repositories) and not between the provider's events: a streamed turn's first token is not delayed by a write.
3. The recorder is exercised on a failing repository in a test: the turn still ends, with its normal events.
4. The recorder adds no network call and no extra provider request.

### R6 — The admin screen

**As** the administrator, **I want** a screen showing usage by user and call by call, **so that** I can see who uses what and what it costs.

Acceptance criteria:

1. A new route under the admin area, linked from the « Administration » page (« Consommation » / « Usage »), reachable by an `admin` only. Any other role gets `403`; the routes are in `test_route_guards.py`'s scope (`require_roles("admin")`).
2. **Period.** A selector applies to everything on the screen: today, last 7 days, last 30 days, all time, and a custom date range. The default is the last 30 days.
3. **Summary** for the period: calls, input, cached, output and reasoning tokens, reported cost, and « cost reported on X of Y calls ».
4. **Per user** (the default view): one row per user with calls in the period: name and email, calls, input tokens, cached tokens, output tokens, reported cost, and « cost reported on X of Y calls ». Sortable by calls, tokens and cost; paged; searchable by name or email (case-insensitive, `%` and `_` literal, as spec 012). A user's row opens the same user's calls (item 5), and shows the user's totals by role and by model.
5. **Calls**: a table, newest first, paged (default 50, at most 200), filterable by user, role, feature, model, status and period. Columns: time, user, role, feature, model, provider host, status (with the error code on a failure), latency, time to first token, input / cached / output / reasoning tokens, audio seconds, reported cost (a dash when none), correlation id. A correlation id filter shows the calls of one turn, run or session.
6. The screen shows no course or chapter name, only the course's subject and language, and the ids; nothing a student wrote or uploaded appears. Disabled users stay visible. A user with no calls in the period is not listed.
7. Empty states, loading and error states are written for each view. An unknown filter value is a `422`, not an empty list.
8. All interface text is in the message catalog in French and English (spec 010); dates, durations and numbers follow the interface language; amounts are shown in USD. Raw role, feature and status values are translated labels, not the database strings.
9. The screen works at the admin page's width, with tables scrolling horizontally on a narrow screen.

### R7 — Metadata only

**As** a student (and a parent), **I want** nothing I write, say or upload kept by the ledger, **so that** usage tracking is not surveillance.

Acceptance criteria:

1. No row, log line or API answer of this feature contains a prompt, an instruction, a message, a tool argument or result, a model answer, a transcript, an image, an audio, a file name, a title of a course or chapter, or provider error text.
2. The only free-text-like fields are enumerated values (`role`, `feature`, `status`, `error_code`) and `model` (the name the administrator configured) and `provider` (a host name).
3. A test builds one call of each feature with distinctive content in its input and output and checks that none of it appears in the stored row, the log records and the admin answers.
4. The base URL's credentials, path and query never reach the row (host name only).

## 4. Non-functional requirements

### Architecture

1. The recorder lives at the provider boundary, where the role, model, connection, timing and usage are all known: in or around the hub's proxies and the adapters in `app/providers/`, or a thin wrapper above them. Nothing above `app/providers/` imports `openai`; the repository is reached through a protocol injected at startup, so the providers package does not import `app.db`.
2. One table (`ai_usage`, migration `0010`), indexed for `(user_id, created_at)`, `(created_at)` and `(correlation_id)`; `role` and `feature` as check-constrained strings like the other tables. The migration works on SQLite and PostgreSQL, adds the table without rebuilding `users` (spec 012's default-expression warning), and `test_upgrade_from_…` style tests cover it.
3. The repository follows the existing pattern (`_Repo`, one short session per call) and is on `Repositories`.
4. Aggregation is done in SQL (`GROUP BY`, `SUM`, `COUNT`, conditional counts for « cost reported »), portable across SQLite and PostgreSQL, never by loading rows into Python. Time filtering is on `created_at` in UTC.
5. The provider-neutral events and results carry what is needed (cost, time to first token, status) without a vendor type leaking out; `Completed.usage` and `CompletionResult.usage` stay dicts in the Responses shape.
6. Documentation: a new `documentation/ai-usage.md` (ledger, fields, what is and is not recorded, the voice caveat, the cost rule, retention), linked from `documentation/index.md`; `documentation/admin.md`, `ai-providers.md` and `voice.md` updated; the root and backend `CLAUDE.md` layout notes updated; `specs/index.md` updated.

### Performance

1. A row write adds no measurable latency to a turn (off the event loop, after the call ends; R5).
2. The calls list answers in under a second on a ledger of a million rows, and the per-user view in under two seconds, using the indexes above; both are paged server-side.
3. Row size is bounded: no variable-length text field beyond host name, model name and codes.

### Security

1. All routes are `admin` only, same-origin, and throttled like the other admin routes; they are read-only (`GET`). The ledger has no write route; only the recorder and `POST /api/voice/usage` write.
2. The admin sees usage of any user; this is the administrator's role, with no ownership check (spec 012). A student cannot read any of it, including their own, in this spec.
3. Query parameters are validated (enumerations, bounded integers, date range of at most the whole ledger); `q` is bounded and bound as a parameter, never interpolated.

### Reliability

1. See R5. The ledger is best-effort: a lost row is a log line, never an incident for the student.
2. A crash between a call's end and its write loses that row. This is accepted; the cancellation and timeout paths write in a `finally` so a normal abort does not.
3. The migration is additive and idempotent in its voice carry-over; a migration on a populated database backs up first (spec 013).

### Usability

1. The screen states plainly when cost is unavailable (« Le fournisseur ne communique pas de coût ») and never shows 0 for an unreported cost.
2. Numbers use thousands separators and the interface language's decimal mark; tokens are integers, cost has four decimals.
3. The admin page remains usable without the new screen: the users panel and the AI banner are unchanged.

## 5. Decisions recorded

| Decision | Why |
|---|---|
| A row per provider call, not per turn or run | Tool rounds are separately billed; `authoring_runs` already holds the run total. |
| Cost only when reported, never computed | No prices are configured in the app. Env prices would silently be wrong off OpenAI. |
| Unknown tokens are null | A provider that reports no usage must not look free. |
| Rows are deleted with the user, kept (course and chapter nulled) when a course or chapter goes | The ledger belongs to the account, not to the material. |
| No course or chapter names in the admin screen | Names are what the student wrote; ids and subject are enough to attribute cost. |
| Voice is one row per session | The backend does not see the Realtime API's calls. |
| Tutor-turn usage corrected to the sum of the rounds | The last-round value is a latent defect the ledger would otherwise contradict. |
