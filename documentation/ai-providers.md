# AI providers

Spec 014. Célestin runs on any OpenAI-compatible server: OpenAI, Groq, OpenRouter, a local Ollama, vLLM,
llama.cpp. The administrator picks the provider, gives its address and key, and names a model per job, in the
browser, without a restart. This page is the whole picture; the first-run flow that leads here is in
[first-run-setup.md](./first-run-setup.md), the Docker image in [docker.md](./docker.md).

## The model: a connection and four roles

A **connection** is how to reach one server: a base URL, an API key (optional for a server that is not
OpenAI's), an **API style** and a **structured-output mode**. A **role** is a job the application gives a model:

| Role | What it does | What it needs from a model |
|---|---|---|
| `tutor` | Teaches the lesson and answers in a discussion | Streaming, and calling tools, the board's `display_board` above all |
| `authoring` | Turns a document into a pack and a curriculum | Following a JSON schema (or, in JSON mode, producing a JSON object) |
| `transcription` | Reads the pages of an uploaded document, and a photo of the student's own work ([work-reading.md](./work-reading.md)) | Accepting images |
| `voice` | Talks with the student (Realtime) and, with its speech model, transcribes dictation | An OpenAI Realtime server; dictation only needs `/audio/transcriptions` |

Each role has a **model**, a **reasoning effort** and, optionally, a **connection of its own**. Without one it
uses the **default connection** (OpenAI, `https://api.openai.com/v1`, out of the box). The common case is one
connection and four model names; a role on its own provider is the exception (a local tutor with OpenAI voice,
a vision model hosted elsewhere).

## Where a setting comes from

Per field, the first of: **the environment** (a variable explicitly set, in the environment or in `.env`), **what
an administrator stored**, **the built-in default**. A field the environment sets is read-only in the interface
and a save that tries to change it answers `409 setting_from_environment`; a save that echoes it back is fine.
`Settings.model_fields_set` tells a set variable from a default, so an empty `AUTHORING_REASONING_EFFORT=` is a
setting (« not sent»), while a blank model name or key is not one.

| Setting | Variable | Built-in default |
|---|---|---|
| Default connection: address | `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| key | `OPENAI_API_KEY` | none |
| API style | `AI_API_STYLE` | `responses` |
| structured outputs | `AI_STRUCTURED_OUTPUTS` | `schema` |
| Tutor model, effort | `OPENAI_MODEL`, `TUTOR_REASONING_EFFORT` | `gpt-6.1-sol`, not sent |
| Authoring model, effort | `AUTHORING_MODEL`, `AUTHORING_REASONING_EFFORT` | `gpt-6.1-sol`, `medium` on OpenAI |
| Transcription model, effort | `TRANSCRIPTION_MODEL`, `TRANSCRIPTION_REASONING_EFFORT` | `gpt-6.1-sol`, `low` on OpenAI |
| Voice model, effort, speech model | `VOICE_MODEL`, `VOICE_REASONING_EFFORT`, `VOICE_TRANSCRIPTION_MODEL` | `gpt-realtime-2.1`, `low`, `gpt-4o-mini-transcribe` |
| A role's own connection | `<ROLE>_BASE_URL`, `_API_KEY`, `_API_STYLE`, `_STRUCTURED_OUTPUTS` (`TUTOR_`, `AUTHORING_`, `TRANSCRIPTION_`, `VOICE_`) | none: the role uses the default connection |

Setting `<ROLE>_BASE_URL` takes the whole connection of that role from the environment.

**The built-in reasoning efforts are OpenAI's.** `low` and `medium` are values another provider's models may
refuse (an earlier test found Qwen's on Groq taking only « default » or « none »; `qwen/qwen3.8-27b` did accept
`medium` and `high` on 5 October 2026), so on a connection that is not OpenAI's nothing is sent unless the
administrator chooses an effort. The settings screen shows the effective default.

## Choosing and configuring in the browser

`Settings` → « Fournisseur d'IA » (admin only). A preset (OpenAI, Groq, OpenRouter, Ollama, another server) fills
the address, the style and suggested models; only the resulting values are stored. Then the key, a model per
role, a reasoning effort per role (« default », « not sent », low, medium, high) and, behind « Use a different
provider for this role », a connection of the role's own. « Lister les modèles » offers what the **saved**
connection lists as suggestions; any name can be typed. A provider that is not OpenAI has no default model, so
tutor, authoring and transcription must be named before a save.

Saving is atomic from the outside: the input is validated, a connection whose address or key changed is asked
whether it works (`GET <base>/models`, free), the clients are built, and only then is the document written and
the hub swapped. A rejected key (`422 ai_key_rejected`) or an unreachable server (`502`) leaves the previous
configuration in force. **Changing a connection's address without giving a key drops the stored key**: it was
given for another server, and must not be sent to this one. A call already in flight finishes with the clients
it started on; the next call uses the new ones.

Routes (all `admin`, throttled per admin, same-origin): `GET /api/admin/ai` (the view: every field with its
source, the key as a source and its last four characters), `PUT /api/admin/ai` (the whole form),
`GET /api/admin/ai/models?slot=` and `POST /api/admin/ai/test {live}`.

## The two API styles

| Style | Wire | Use it for |
|---|---|---|
| `responses` (default) | OpenAI's Responses API, the application's own message format | OpenAI, Groq, Ollama, vLLM, OpenRouter: any server that has `/v1/responses` |
| `chat` | Chat Completions, translated by `providers/chat_translate.py` | llama.cpp, LM Studio, text-generation-webui, gateways with no Responses API |

Both are adapters behind the provider protocols (`LLMClient`, `CompletionClient`); nothing above
`app/providers/` knows the style. What the adapters do for a server that is **not OpenAI's**, so the request
is one such a server accepts:

- `prompt_cache_breakpoint` on content parts and tool `strict` are not sent (they are OpenAI's; Pydantic
  validates tool arguments in any case). OpenAI's own requests are byte-identical to what they always were.
- The first `developer` message is sent as `system` and every later one as a `user` message. Chat templates of
  open models know no `developer` role, expect a single system message and refuse a conversation without a user
  message, and the tutor's opening turn is the prompt and the path state, nothing else.
- The Responses stream is read as raw events (`responses.create(stream=True)`), not through the SDK's
  `responses.stream()` helper, which folds events into a snapshot and raised on a server whose events arrive in
  another order.
- The Chat adapter assembles tool calls from their fragments by index and emits them when the stream ends, strips
  `<think>…</think>` text (a model's visible thinking never reaches the student), reads usage into the Responses
  shape, learns once whether the server wants `max_completion_tokens` or `max_tokens`, and treats a missing or
  `length` finish reason as a failure.

## Structured outputs

`schema` (default): strict `json_schema`, as before. `json`: a JSON object is asked for, the schema is put in the
instructions (`Output exactly one JSON object…`), and the answer is read out of a code fence or prose and
validated by the same Pydantic model. A wrong answer is an `ProviderOutputInvalid` or a validation failure that
authoring's existing repair loop handles; nothing else in authoring changed. It applies to both styles.

## The test

« Tester la connexion » asks each distinct connection (`GET /models`) and reports, per role, whether the server
answered, refused the key, or could not be reached, and whether the model is listed. Models are found in the
server's listing first (ids such as `openai/gpt-oss-120b` are not found by a path lookup). A server with no
models route, or a restricted key, is `limited`: valid, availability unknown.

The **live check** (a checkbox: a few thousand tokens) runs one real call per role through the clients the hub
holds, so the report is about what a student's request will use:

| Role | Check | Failure codes |
|---|---|---|
| tutor | Streams one request with the application's own five tools and needs a **valid** `display_board` call | `no_tool_calls`, `tool_arguments` |
| authoring | A tiny answer that must follow a schema (or JSON mode) | `schema_unsupported` |
| transcription | A generated PNG of « 42 » that must be read | `no_image_input` |
| voice | A Realtime client secret must be mintable (no audio) | `other` |

Every role can also fail with `rejected` (key refused), `unreachable`, `model_not_found` or `other`. A request
the server refused cannot say which parameter it refused (provider text is never forwarded), so
`no_tool_calls`, `schema_unsupported` and `no_image_input` for a refusal are the likeliest cause, not a
certainty. Each check is bounded to 45 seconds and logs `ai_test` with the role, the outcome and the time.

## Voice

Voice is the one role that is not « any OpenAI-compatible server »: it needs a Realtime server. It follows the
default connection **only when that is OpenAI's**; otherwise it needs a connection of its own (`VOICE_BASE_URL`
or « Use a different provider » on the voice role), and the administrator asserts it is Realtime-compatible.
The session response carries `calls_url` (`<voice base URL>/realtime/calls`, `https`, or `http` for a loopback or
private host); the browser holds no URL. `GET /api/health` reports `voice` only when voice is enabled, a voice
model and connection exist and that connection is Realtime-capable. OpenAI is the only provider verified.

**Dictation** (the composer's microphone, [voice.md](./voice.md)) rides on the voice role's *speech model* and
connection but not on Realtime: `AiConfig.dictation` is resolved whenever that connection is usable and, off OpenAI,
the voice role has a connection of its own or a speech model somebody chose. `GET /api/health` reports `dictation`.

## Where it is stored, and upgrading

`app_settings` (spec 013), key `ai_settings`: one JSON document with the non-secret settings and each key
encrypted (AES-256-GCM, a context per slot: `celestin:ai_key:v1:<default|role>`). Nothing else: no migration. A
stored 013 key (`openai_api_key`) is read as the default connection's key when `ai_settings` has none, so an
upgrade needs nothing from the administrator; while the default connection is OpenAI's with a stored key, the
legacy row is mirrored on every save (and removed otherwise), so rolling the code back still finds the key. A
document whose address does not validate, or that is not JSON, is ignored as a whole with an
`ai_settings_unreadable` warning; a key that cannot be decrypted counts as absent and shows as « unreadable ».

The instance is **configured** when the tutor, authoring and transcription roles each have a model and a usable
connection (a key, or a server that is not OpenAI's: a local server needs none). Otherwise the seven AI routes
answer `503 ai_not_configured` (the list is `tests/integration/test_needs_key.py`) and the dashboard banner leads
to the settings.

## Cost estimates

Token counts are logged for every provider. `cost_estimate_usd` applies the `*_PRICE_*` settings when the role's
connection is OpenAI's **or** the price was set explicitly in the environment, and is `0.0` otherwise: another
provider's run never reports OpenAI's prices as its own.

The **usage ledger** (spec 015, [ai-usage.md](./ai-usage.md)) does not use these prices: it stores a call's cost
only when the provider reports one in its usage block (OpenRouter's `usage.cost`, read on both API styles), and the
Chat adapter's `usage_dict` leaves out the fields a server did not send (so « not reported » is not zero) and passes
`cost` through as sent.

## Running a local server from Docker

The container reaches the host as `host.docker.internal`: for an Ollama on the host, the address is
`http://host.docker.internal:11434/v1` (on Linux add `--add-host=host.docker.internal:host-gateway`). Private and
loopback addresses are accepted on purpose; the administrator decides where the server makes requests.

## Privacy, by setup

With OpenAI or any hosted provider, **the pages a student uploads and their conversations go to that provider**
under the operator's own account and terms. With a local server nothing leaves the host. Redirects are not
followed (a key goes to the host that was named and nowhere else), the key is never returned, logged or put in
an error, and prompt and pack content stay out of the logs unless `DEBUG_LOG_PROMPTS=true`.

## Compatibility

What was run, on 3 and 4 October 2026 (and the Qwen 3.8 row on 5 October, from `evals/`), through the Responses API
unless noted. `tutor` means a lesson turn with a
`display_board` call (`scripts.smoke`, and the Test button's live check); `authoring` the fixtures of
`scripts.authoring_eval`.

| Provider · model | Tutor | Authoring | Reading images | Notes |
|---|---|---|---|---|
| OpenAI · `gpt-5.6-terra` (the default until 4 October 2026) | works | works | works | the reference; prompt cache hits (26k tokens) |
| OpenAI · `gpt-6.1-sol` (the default since) | works (live check, a full turn in both modes) | works | works | prompt cache hits in both modes (26.6k and 25.9k tokens); OpenAI's own defaults (`medium` authoring, `low` reading) accepted |
| OpenAI · `gpt-6-luna` | works (live checks 3/3 at `medium` and `high`; 98–100 % of turns finished) | works (4/4 fixtures, about 1/20 of `gpt-6.1-sol`'s cost per document) | works | judged indistinguishable from `gpt-6.1-sol` at `medium` in a 96-pair comparison (56 %, 95 % CI 46–66 %, [model-evals.md](./model-evals.md)), but slower (median turn 9.5 s vs 6.9 s, p95 22 s vs 11 s), about 4× more output tokens, about 1/8 of the cost per turn; in a discussion it tended to speak of a course path that does not exist (lost 11 of 12 homework comparisons) |
| Groq · `qwen/qwen3.8-27b` | live checks pass (5/5 and 3/3), but **not reliable**: in the comparison of 5 October ([model-evals.md](./model-evals.md), 48 turns per effort) 85–88 % of turns finished, the rest aborted by Groq on a malformed `display_board` call; one answer written while an exercise was open (`high`); out-of-pack teaching in 4–10 % of turns; judged clearly worse than `gpt-6.1-sol` | works at `medium` (4/4, about 3 attempts) with `AUTHORING_MAX_OUTPUT_TOKENS=16000`; at `high` 1/4 (`truncated`; probably the reasoning shares the output budget) | works | no prompt cache; refused outright without the output cap, see below |
| Groq · `qwen/qwen3.6-27b` | works (4/5 live checks; both modes over Responses **and** Chat Completions) | not run | works | fewer reliable tool calls than 3.8 |
| Groq · `openai/gpt-oss-120b` | **does not work**: never produces the nested `{card: …}` the board tool needs, and Groq refuses the call (`tool_use_failed`) | works, both structured modes, over Responses and Chat | no (text only) | prompt cache hits; a good authoring model |
| Groq · `openai/gpt-oss-20b` | does not work (same) | not run | no | |

**A provider can cap a model's output below what the application asks for.** The authoring agent asks for up to
`AUTHORING_MAX_OUTPUT_TOKENS` (32 000) per call; Groq caps `qwen/qwen3.8-27b` at 16 384 and answers
`400 max_completion_tokens must be less than or equal to 16384` to every authoring request (the live check passes,
its request is tiny). Set `AUTHORING_MAX_OUTPUT_TOKENS=16000` for such a model; a chapter whose pack does not fit
then fails as `truncated`.

**Groq checks a tool call's arguments itself.** When a model's `display_board` call does not match the schema
(`card` written as a string, fields missing), Groq aborts the stream (`400 tool call validation failed`) instead of
letting the application's own validation send the correction back, so a recoverable mistake ends the turn: the
student sees « Célestin est injoignable ». It is why a model that passes the live check can still lose one turn in
eight on Groq.

Not verified: Ollama,
vLLM, OpenRouter, llama.cpp (the adapters follow their documented APIs and are covered by offline tests),
voice on anything but OpenAI. A weaker model teaches less well; the invariants (answers withheld, mechanical
verdicts, content restricted to the pack) are enforced in the tools and do not depend on it. To measure a
model: `OPENAI_BASE_URL=… OPENAI_MODEL=… uv run python -m scripts.probe` (and `smoke`, `authoring_eval`,
`document_eval`, `voice_smoke`), which read the same configuration as the server, the environment first and the
stored settings when `DATABASE_URL` and `SECRETS_DIR` point at a database.

## Not supported

Azure OpenAI and other providers with non-Bearer authentication or per-deployment URLs; custom request
headers; several keys per connection; per-student or per-course models; automatic fallback between providers;
prices in the interface (they stay environment-only); several replicas (the hub is in-process).

## Where the code is

`app/domain/ai_config.py` (connection, role and configuration types, address validation, `calls_url`, `priced`);
`app/services/ai_resolution.py` (environment > stored > default); `app/services/ai_settings.py` (save, models,
test, `load_ai_config` for scripts); `app/services/ai_test.py` (the live checks); `app/providers/hub.py` (clients
per role, runtime swap), `openai_responses.py`, `openai_chat.py`, `chat_translate.py`, `_client.py`,
`openai_probe.py`, `openai_realtime.py`; `app/api/routes/admin.py` and `schemas/ai.py`; frontend
`settings/ai-section.tsx`, `ai-form.ts`, `lib/ai-presets.ts`, `lib/admin.ts`. Tests: `test_ai_config.py`,
`test_ai_settings_service.py`, `test_ai_test.py`, `test_provider_hub.py`, `test_openai_adapter.py`,
`test_openai_chat_adapter.py`, `test_chat_translate.py`, `test_openai_probe.py`, `test_provider_client.py`,
`test_cost_rule.py`, `integration/test_ai_settings.py`, `integration/test_chat_style.py`; frontend
`ai-section.test.tsx`, `ai-form.test.ts`, `ai-presets.test.ts`, `ai-settings.test.ts`.
