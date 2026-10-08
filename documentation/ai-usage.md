# AI usage

Spec 015. Every call the application makes to a model is one row of the **usage ledger** (`ai_usage`): who
caused it, what it was for, which model, how many tokens, how long, how it ended, and the cost when the provider
says what it was. The administrator reads it at `/admin/usage`: the calls one by one and the totals per user.

## What a row is

One call to a provider. A tutor turn with tool rounds is several rows (one per round, one correlation id), an
authoring run is several (one per stage, repair, page and attempt), a voice session is one.

| Field | Meaning |
|---|---|
| `created_at` | When the call started (UTC). For a voice session, the report's time minus its duration. |
| `user_id` | The account that caused it. A foreign key, **deleted with the account**. |
| `course_id`, `chapter_id` | When the call belongs to one. Set to null (the row stays) when the course or chapter is deleted. |
| `correlation_id` | What groups calls: a tutor `turn_id`, an authoring `run_id`, a voice session id. |
| `role` | `tutor`, `authoring`, `transcription`, `voice` (spec 014). Dictation is `voice`: it runs on the voice role's speech model. |
| `feature` | What for: `tutor_turn`, `discussion_turn`, `authoring`, `document_reading` (the transcription stage of a run), `work_reading`, `dictation`, `voice_session`, `ai_test`. |
| `model`, `provider` | The model name sent and the **host name** of the connection (never the URL, a path or a key). Empty for voice sessions carried over from `voice_usage`. |
| `status`, `error_code` | `ok`, `failed`, `truncated`, `cancelled`; for a failure the application's own code (`provider_timeout`…), never the provider's text. |
| `latency_ms`, `ttft_ms` | Request to last event or answer; request to the first text (streamed calls that sent text only). |
| `input_tokens`, `cached_tokens`, `output_tokens`, `reasoning_tokens` | As the provider reported. **Null is « not reported », not zero.** |
| `input_audio_tokens`, `output_audio_tokens`, `audio_seconds` | Voice sessions (and the length of a dictation, `audio_seconds`). |
| `cost_usd` | The amount the provider reported for this call, or null. |

**Metadata only.** No prompt, instruction, message, tool argument, answer, transcript, image, audio, file name,
course or chapter title, or provider error text is a column, a log line or an API answer of this feature.
`tests/integration/test_privacy_ledger.py` makes one call of each feature with a marker in everything and fails if
it appears in a row, in the recorder's logs or in what the admin routes answer, and pins the table's columns.

## Cost: reported, never computed

`cost_usd` is filled only from a number in the provider's own usage block (OpenRouter's `usage.cost`, in credits;
1 credit = 1 USD, which is the assumption made for any provider that reports one). It is finite and not negative
or it is ignored; a string is not coerced. It is stored as received and never recomputed. OpenAI, Groq and local
servers report none: their rows have no cost, and **no price per token is configured, stored or applied** by the
ledger (the `*_PRICE_*` settings of the log lines are not read by it).

So the screen never writes a zero for an unknown cost. A total is the sum of the reported costs, next to « Calls
with a cost reported by the provider: X of Y », and says the provider reports none when X is 0.

## How a call becomes a row

```
service opens a scope ─▶ contextvar ─▶ recording wrapper (hub) ─▶ UsageRecorder ─▶ executor ─▶ ai_usage
(user, course, chapter,                times the call, keeps       (never raises)
 feature, correlation id)              the last usage block
```

- `app/domain/usage.py`: the vocabulary (`Feature`, `Status`), `UsageScope`, `usage_scope()`, `read_usage()`.
- `app/providers/recording.py`: `RecordingLLM`, `RecordingCompletion`, `RecordingTranscriber` wrap the clients the
  hub builds (`ProviderHub.build`), so the hub's proxies, the admin's live test (which uses the clients directly)
  and every test fake are recorded alike. The wrappers never read the input, the answer or an exception's message.
  The Realtime client is not wrapped: minting a secret is not a billable call.
- The **scope** says who a call is for. It is a `contextvar` (as `request_id_var`), so a background task copies it
  at creation and so does every child of a `gather`. A call outside any scope is not recorded (scripts, startup
  checks): `scripts/smoke.py` and the other chapter-file scripts write nothing.
- Writes happen after the call ends, on the loop's default executor, and are not awaited: they never delay a
  streamed event, and a cancelled task can still hand its row over. A failed write is the log line
  `ai_usage_not_stored` (the error class and the role) and nothing else. `lifespan` drains pending writes at shutdown.

| Where | Scope |
|---|---|
| `TutorService.run_turn` | `tutor_turn` or `discussion_turn`, the student, `TurnContext.course_id` / `chapter_id`, the turn id. None when the context has no user (unit tests, scripts). |
| `AuthoringRunner._start`, around `create_task` | `authoring`, the chapter's owner, course, chapter, run id. `document_reading` is the same scope read with the transcription role (`feature_of`). |
| `WorkReader.read` | `work_reading`, the student, the course. |
| `DictationService.dictate` | `dictation`, the student, `audio_seconds` (capped at `DICTATION_MAX_S`, as its log line). |
| `routes/admin.py` `test_ai` | `ai_test`, the admin. |

`tests/unit/test_usage_scopes.py` lists every file that calls a provider client and fails on a new one that is not in
its table: **a new call site needs a scope, and a line there.**

### Voice

The browser drives the Realtime API, so the backend sees a session, not its calls. `POST /api/voice/usage` writes
one row (`voice_session`, the correlation id is the session id, text and audio tokens folded into the totals, the
audio shares apart, `audio_seconds`, no cost). The figures are **reported by the browser**: each token total is
bounded (`0 … 100 000 000`, `MAX_TOKENS`; a report outside it is dropped as malformed, `204` as always), but they are
not verified. A session is stored **once** per user and session id (`add_once`: the stop and the unload beacon can both
report it), and reports are limited per user to twice the sessions the minting allows an hour (the rest are dropped with
a `204` and `voice_usage_rate_limited`). The course and chapter come from `VoiceSessionScopes` (in process, 1,000 entries, 3 hours): what the
session was minted for, with the model and host it was minted with. The report carries no course or chapter id
(`extra="forbid"`), and a session id minted for another user gives none. After a restart the row has no course or
chapter, and the model and host in force.

`voice_usage` is gone: migration `0010` copied its rows into the ledger (cost null, model unknown) and dropped it;
the downgrade recreates it, best effort.

### What the tutor turn reports

`TurnEnd.usage` and the `turn_complete` log line are the **sum** of the turn's rounds (`add_usage`: the figures the
application reads, in the same shape for one round or many; before spec 015 they were the last round's only). The per-round
figures are the ledger's rows. A cost the provider reported is in the sum and the log but **not in `turn.end`**: the
student gets the tokens, the ledger is the administrator's.

## Retention

Rows are kept until the user is deleted (`ON DELETE CASCADE`); nothing expires and there is no purge setting.
Deleting a course or a chapter keeps the rows with that id nulled, so their cost stays in the user's totals.

## The admin screen

`/admin/usage`, linked from the dashboard (« Consommation de l'IA »). Admin only.

- **Period**: today, 7 days, 30 days (the default), all, or a custom range of local days (both ends included). The
  browser sends instants with an offset; the server compares in UTC.
- **Totals** for the period: calls, input (cached), output (reasoning) tokens, the reported cost and its coverage.
- **Per user**: calls, tokens, cost and its coverage, sortable, searchable by name or email, 25 per page; a row
  expands to the user's totals by role and by model, and « Voir les appels » opens their calls.
- **Calls**: newest first, 50 per page (« next » is driven by `has_more`, no count), filters by user, role, feature,
  model, status and group id (click a group id to see the calls of one turn, run or session).
- The page's state is its address, so a view can be bookmarked and the back button works.
- No course or chapter name is shown, only the subject, the language and the ids.

| Route (all `admin`, `GET`) | Answer |
|---|---|
| `/api/admin/usage/summary?since&until` | `{totals, models}` |
| `/api/admin/usage/users?since&until&q&order&direction&limit&offset` | `{users, total}`; `order` is `calls`, `input_tokens`, `output_tokens`, `cost` (null last) or `name` |
| `/api/admin/usage/users/{id}?since&until` | `{user, totals, by_role, by_model}`; `404` for an unknown account |
| `/api/admin/usage/calls?since&until&user_id&role&feature&model&status&correlation_id&limit&offset` | `{calls, has_more}` |

`since` is included, `until` excluded, both with an offset (`422` without one, or when `since >= until`). An unknown
`role`, `feature`, `status`, `order` or `direction` is a `422`, not an empty list. Totals are one SQL `GROUP BY`,
on SQLite and PostgreSQL alike; the table is indexed on `(user_id, created_at)`, `created_at`, `correlation_id`,
`course_id` and `chapter_id`.

## Logs

`ai_usage_not_stored` (error: `error` class, `role`), `ai_usage_unscoped` (debug: `role`). The existing
`turn_complete`, `authoring_*`, `work_read`, `dictation` and `voice_usage` lines stay, with the cost estimates some
of them carry from the `*_PRICE_*` settings; those are not the ledger.

## Not done

Budgets, quotas or alerts from usage; a chart, a CSV export, a view for the student of their own usage; a purge or
retention setting; a price table; backfilling calls made before the migration (only the voice sessions were stored).
The SDK's own retries are invisible: one application call is one row, its latency including them.

## Edge cases the ledger settles

- A call that was made and finished is `ok` whatever its consumer does with the answer afterwards; its latency stops when
  the provider's stream ended, not when the consumer did.
- A call in flight when its course or chapter is deleted is stored without them (`IntegrityError` → retried with the ids
  nulled); one whose user is gone is refused and logged.
- `error_code` is only ever one of our own errors' codes (`TutorError`, `provider_output_invalid`), else `unknown`.
- A streamed one-shot call (authoring, transcription, work reading, the admin test; spec 016) is one row like any
  other. One cut before its final event (the provider went quiet, the connection dropped) is `failed` with the
  domain code (`provider_timeout`…) and **null tokens**: only the final event carries usage, and nothing is estimated
  from the characters received. A stream that ends `incomplete` is `truncated` with its usage.
- A streamed round cut at the output limit is `failed/provider_unavailable` with no tokens: only `Completed` carries usage,
  so `truncated` exists for one-shot calls only.
- The screen's rolling periods are measured from an anchor that moves when a period is chosen (again too) and every five
  minutes; it says « Chargement… » while a query has nothing yet and warns when a custom range ends before it starts.

## Manual check

With an admin and a student on a scratch database (`DATABASE_URL`, `SECRETS_DIR`): run a lesson turn, upload a page
or a text chapter, dictate a few words, then open `/admin/usage`: one row per round and per stage under the student's
name, `—` for the cost on OpenAI and a figure on OpenRouter, the correlation id grouping a turn. Delete the user: the
rows go.
