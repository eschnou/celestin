# 014 — AI provider configuration: open models, set in the admin UI

## 1. Introduction

Today the application talks to one vendor. The endpoint is OpenAI's, the key is OpenAI's (spec 013 stores it encrypted), and the four models are environment variables with OpenAI defaults (`OPENAI_MODEL`, `AUTHORING_MODEL`, `TRANSCRIPTION_MODEL`, `VOICE_MODEL`). For an open-source project that is a barrier: an operator should be able to run Célestin on Groq, OpenRouter, a local Ollama, vLLM or llama.cpp, and to change any model without a restart or a shell.

This epic makes the AI backend a setting the administrator edits in the browser:

- A **connection** (base URL, API key, API style) that any OpenAI-compatible server satisfies.
- A **model per role** (tutor, authoring, transcription, voice), each with its reasoning effort, and an optional connection of its own.
- Presets for the common providers, a model list fetched from the server, and a **test** that checks the thing the application actually needs from each model (streaming, tool calls, structured output, image input).
- OpenAI stays the default and keeps working with no action from an existing instance.

What was verified before writing this (against Groq's live endpoint, `openai/gpt-oss-120b`, with the existing code paths): the **Responses API** adapter works unchanged with only `base_url` changed. Streaming tool calls, `store=False`, the `prompt_cache_breakpoint` content field, strict `json_schema` output with `reasoning.effort`, and a `function_call` / `function_call_output` history round trip all succeed. Groq documents the Responses API as beta and compatible, with `previous_response_id`, `store`, `truncation` and `prompt_cache_key` unsupported (the application uses none of them). Ollama and vLLM expose `/v1/responses` as well. Servers that only offer **Chat Completions** (llama.cpp, LM Studio, text-generation-webui, many gateways) need a second API style. The Realtime voice API has no equivalent outside OpenAI-compatible Realtime servers.

Vocabulary:

- **Connection** — `{base_url, api_key, api_style}`. How to reach one server.
- **Default connection** — the one every role uses unless it has its own. OpenAI (`https://api.openai.com/v1`, `responses`) out of the box.
- **Role** — `tutor` (streaming turns, tools, discussion), `authoring` (pack and curriculum, structured output), `transcription` (reads pages: **image input** required), `voice` (Realtime session). Each has a **model**, an optional **reasoning effort**, and optionally an **own connection**.
- **API style** — `responses` (OpenAI Responses API, the application's internal format) or `chat` (Chat Completions, translated by an adapter).
- **Structured-output mode** — `schema` (strict `json_schema`, today's behaviour) or `json` (JSON object mode, for models that cannot constrain to a schema; the existing validate-and-repair loop enforces the shape).
- **Effective setting** — the value in force: the environment variable when explicitly set, else the stored value, else the built-in default.
- **AI configured** — the tutor, authoring and transcription roles each resolve to a connection and a model. Voice is optional.

Scope:

- The connection and role settings, their storage, the admin API and the settings section replacing « OpenAI ».
- A Chat Completions adapter beside the Responses adapter, behind the existing provider protocols.
- Runtime swap of the clients (spec 013's hub), the test action, health, cost logging, voice URL, documentation, README.

Out of scope:

- Changes to the tutor, the tools, the prompts, the checker or the authoring pipeline. The invariants of the brief hold on any model; quality on a given model is the operator's judgement (R9 gives them the means to measure it).
- Azure OpenAI and other providers with non-Bearer authentication or per-deployment URLs; custom request headers; OAuth.
- Several API keys per connection, per-student or per-course models, automatic fallback between providers, load balancing.
- Moving prices, limits, timeouts or `REGISTRATION_MODE` into the interface (cost-price settings stay environment-only).
- Speech-to-text or text-to-speech endpoints other than Realtime (Whisper-style `/audio` routes), local model download or management.
- Several replicas (the hub is in-process; spec 013 stands).

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §5.7 Setup is minutes, not hours | Choosing a provider is a preset, a key and a button; no file to edit, no restart. |
| §10 Authoring cost per chapter | An instance can run on a cheap or free-tier or self-hosted model; the limits and cost logs stay. |
| §8 Privacy | An instance on a local model sends nothing to a third party; the documentation says exactly where data goes for each setup. |
| §5.3, §5.4, §8 invariants | Untouched: rules live in the tools, the checker and the pack restriction, not in a model's behaviour. |
| §11 Out of scope: content we author | Unchanged. |

Deviations from specs and `CLAUDE.md`:

1. **Spec 013 « any provider other than OpenAI » out of scope.** Now in scope; 013's mechanisms (encrypted key, hub, needs-key state, test action, environment wins) are generalised, not replaced.
2. **Spec 013 « Moving other settings (models …) into the interface » out of scope.** The models and the connection move into the interface; limits, prices and timeouts do not.
3. **`CLAUDE.md` « `OPENAI_API_KEY` is optional » and the `503 ai_not_configured` rule.** Generalised to « AI configured » (R8); the error code and its route list do not change.

## 3. Requirements

### R1 — The connection

**As an** administrator, **I want** to point the instance at any OpenAI-compatible server, **so that** I can use the provider or hardware I prefer.

Acceptance criteria:

1. The default connection has a base URL (default `https://api.openai.com/v1`), an API key and an API style (`responses` default, or `chat`).
2. The base URL is validated on save: `http` or `https` only, a host, no user-info, no fragment, at most 2048 characters; a trailing slash is normalised away. Private and loopback addresses are **allowed** (a local Ollama is the point); the administrator is trusted with this, and the documentation says so.
3. The API key is **optional** when the base URL is not OpenAI's (local servers need none); the adapter sends a placeholder bearer value then. For OpenAI's own URL a key is required.
4. The key is stored encrypted exactly as spec 013 stores the OpenAI key (same cipher, same rules: never returned, `last4` at most, never logged, `stored_unreadable` when it cannot be decrypted, no storage without an encryption key).
5. Saving validates before committing: the server is asked (`GET <base>/models`, free) and the result classified as `ok`, `rejected` (401), `unreachable`, or `ok` + `limited` (403 or a server with no models route: valid, cannot list). Nothing is stored or swapped on `rejected` or `unreachable`; the previous configuration stays in force. A server with no `/models` route is accepted (`limited`), because llama.cpp-style servers may lack it.
6. Presets fill the base URL, API style and a suggested model per role: OpenAI, Groq, OpenRouter, Ollama (local), and Custom. A preset is a UI convenience: only the resulting values are stored. Suggestions are data, easy to update, never required.
7. Provider error text, URLs with credentials and the key never reach logs, error bodies or the health answer. A log line may carry the host name of the base URL.

### R2 — Models per role

**As an** administrator, **I want** to choose the model for each job and change it at any time, **so that** I can trade quality, speed and cost.

Acceptance criteria:

1. Four roles each have a model name (free text, 1–200 characters, no whitespace at the ends). The built-in defaults are today's (`gpt-5.6-terra` for tutor, authoring and transcription; `gpt-realtime-2.1` for voice, with `gpt-4o-mini-transcribe` as the voice's transcription model).
2. When the connection offers a model list, the interface offers it as suggestions (fetched on demand, never required: a name that is not listed can still be saved).
3. Authoring, transcription and voice also have a **reasoning effort** (`low`, `medium`, `high`, or empty = not sent). Empty means the parameter is omitted from the request, because non-reasoning models reject it. Built-in defaults are today's (`medium`, `low`, `low`). The tutor role has one too (empty by default, i.e. today's behaviour).
4. A model change applies to the next call: no restart, a call in flight finishes with the model it started with. The authoring runner and the tutor read the current model per call, never one captured at construction.
5. Stored changes are recorded with the admin's id and a timestamp (the `app_settings` convention) and logged as `ai_settings_changed` with ids and the names of the roles changed, never values of secrets.

### R3 — A connection per role

**As an** administrator, **I want** a role to use a different server from the others, **so that** I can mix them (a local tutor with OpenAI voice, or a vision model hosted elsewhere).

Acceptance criteria:

1. Each role may hold its own connection (base URL, key, API style). Absent, the role uses the default connection.
2. The interface shows this as an opt-in under each role (« Use a different provider for this role »), collapsed by default; the common case is one connection and four model names.
3. Each connection is validated and stored as in R1.
4. Removing a role's own connection returns it to the default connection; nothing else changes.

### R4 — Responses API style on any server

**As an** administrator running a Responses-compatible server, **I want** the existing adapter to work unchanged, **so that** the tutor behaves the same as it does on OpenAI.

Acceptance criteria:

1. The Responses adapter takes the connection's base URL and key. Behaviour against OpenAI is byte-identical to today (same request bodies, tested).
2. Fields that are OpenAI-specific are sent only when the base URL is OpenAI's host: `prompt_cache_breakpoint` on a content part, and any other extension found while building the design. Standard fields (`store=false`, `reasoning`, `text.format`, `tools`, `max_output_tokens`) are sent to every server; the verification above shows Groq accepts them.
3. Events the application does not use (for example `response.reasoning_text.*`, extra lifecycle events) are ignored; the mapping to the provider-neutral events is unchanged.
4. Usage reporting tolerates providers that omit or null token detail fields (`cached_tokens`, `reasoning_tokens`), counting them as zero.

### R5 — Chat Completions style

**As an** administrator running a server with only Chat Completions, **I want** an adapter for it, **so that** open-model servers without the Responses API still work.

Acceptance criteria:

1. A second adapter implements both provider protocols (`LLMClient.stream`, `CompletionClient.complete`) over `chat/completions`, behind the same hub proxies. Nothing above `app/providers/` changes.
2. It translates the application's Responses-shaped input to chat messages: `developer` → `system`, `user` and `assistant` messages (text parts), `input_image` → image part (`image_url`, with `detail` kept), `function_call` → an assistant message with `tool_calls`, `function_call_output` → a `tool` message with the matching `tool_call_id`; and the tool definitions to `tools: [{type: "function", function: …}]`. The translation is pure and covered by golden tests, including the history shapes `history.py` and `tutor_service.py` produce.
3. Streaming maps text deltas, tool-call fragments (assembled per index, emitted once complete, like `.done` today), finish reasons (`length` → truncated) and usage (`stream_options.include_usage`) onto `TextDelta`, `ToolCallRequested`, `Completed` and `Failed`. Parallel tool calls are supported.
4. `complete` supports `schema` by structured-output mode (R6), `reasoning_effort` when set, and the output limit under the parameter name the server accepts (`max_completion_tokens`, falling back to `max_tokens` on the server's explicit rejection of the first; the design fixes the rule).
5. A tool call whose arguments are not valid JSON is not repaired by the adapter: it is passed on and refused by the tool layer, as today.
6. Reasoning or thinking text in the stream (`reasoning_content`, `<think>` blocks) never reaches the student: it is dropped, and a model that emits only reasoning and no answer ends the turn with the existing empty-turn handling.

### R6 — Structured outputs and what a model cannot do

**As an** administrator, **I want** the application to cope with models that cannot guarantee a JSON schema, **so that** authoring works on them too.

Acceptance criteria:

1. A setting, per connection, **structured outputs**: `schema` (default; strict `json_schema`) or `json` (JSON object mode, the schema instead written into the instructions). Applies to both API styles.
2. In `json` mode the response is parsed and validated against the same Pydantic model; invalid output is `ProviderOutputInvalid`, which authoring's existing repair loop handles. No other authoring logic changes.
3. The strict schema sent is the one built today. The Chat adapter does not alter it; where a server rejects it with a 400 naming the schema, the error surfaces as a provider failure that the administrator can diagnose from the test action (R7), not a silent downgrade.
4. Image input (`input_image` parts) is required by the transcription role only. The application does not guess a model's capabilities from its name: the test action (R7) shows them.

### R7 — Test the configuration

**As an** administrator, **I want** a test that tells me whether each role will work, **so that** I find out now and not on a student's first upload.

Acceptance criteria:

1. A « Test » action per role and one for all runs against the **effective** configuration (stored values, not unsaved form fields; the form says to save first, or tests the draft explicitly: the design decides, the behaviour is stated in the interface).
2. It reports per role, in plain words: connection reachable and authenticated (R1.5 classification), the model listed or not (`visible: true | false | null`, as spec 013), and an optional **live check** (opt-in checkbox, with a sentence saying it spends a few tokens):
   - tutor: a one-token streamed answer **and** a forced tool call, both received;
   - authoring: a tiny structured answer in the configured structured-output mode, validated;
   - transcription: a tiny generated image (a rendered word) read back, checking the model accepts image input;
   - voice: the Realtime client secret can be minted (no audio).
3. Each failure is classified (`rejected`, `unreachable`, `model_not_found`, `no_tool_calls`, `no_image_input`, `schema_unsupported`, `other`) and shown with a short remedy, in the interface language. Provider text is never forwarded.
4. The test is admin-only, throttled per admin, never writes settings, and returns within 60 seconds in total (per-check timeouts).
5. Spec 013's `POST /api/admin/openai-key/test` behaviour (key valid, models visible, `limited`) is a subset of this report.

### R8 — The effective configuration, precedence and the needs-config state

**As an** operator, **I want** environment variables to keep working and to win, **so that** orchestrated deployments are not surprised by a browser edit.

Acceptance criteria:

1. **Precedence per setting**: an environment variable explicitly set (present in the environment or `.env`, not merely defaulted) > the stored value > the built-in default. Existing variables keep their names and meaning: `OPENAI_API_KEY`, `OPENAI_MODEL` (tutor), `AUTHORING_MODEL`, `AUTHORING_REASONING_EFFORT`, `TRANSCRIPTION_MODEL`, `TRANSCRIPTION_REASONING_EFFORT`, `VOICE_MODEL`, `VOICE_TRANSCRIPTION_MODEL`, `VOICE_REASONING_EFFORT`. New variables cover base URL, API style and structured outputs for the default connection and, symmetrically, a role's own connection (names fixed in the design; `OPENAI_BASE_URL` for the default base URL).
2. The interface shows a setting fixed by the environment as read-only with the reason; the API refuses to change it (`409`, like `key_from_environment`).
3. The effective values are available in one place (a resolved-configuration object); no service reads `settings.openai_model` and friends directly any more. `GET /api/health` reports the effective tutor, authoring and voice models, `ai_configured`, and `voice`.
4. **AI configured** (above) replaces « has a key »: a local server with no key and a model name is configured. Otherwise the instance is in the needs-config state: the same seven routes answer `503 ai_not_configured`, the dashboard banner (reworded: « AI provider ») leads to the settings, everything else works. The error code and the route list are unchanged.
5. `voice` in health is true only when voice is enabled, a voice model and a connection are configured, and that connection is Realtime-capable (R10). It no longer implies the default connection.
6. **Upgrade is invisible**: a stored `openai_api_key` (spec 013) is the default connection's key after upgrade, with the OpenAI URL, `responses` style and today's models; nothing is asked of the administrator, no data is migrated by hand, and rolling the code back leaves the old key readable (the old row is not rewritten destructively).

### R9 — Measuring quality on a chosen model

**As a** maintainer, **I want** the existing smoke and probe scripts to run against whichever provider is configured, **so that** « it works on model X » is a measured claim.

Acceptance criteria:

1. `scripts.smoke`, `scripts.probe` (all sets), `scripts.authoring_eval` and `scripts.document_eval` use the effective configuration (environment and, when a database is configured, the stored settings), so `OPENAI_BASE_URL=… OPENAI_MODEL=… uv run python -m scripts.probe` works.
2. They keep their cost warning and add the provider host and model names to their header line.
3. A short compatibility table in the documentation lists what was run on which provider and model (Groq `openai/gpt-oss-120b` for tutor and authoring is the first entry), what passed, and what is known not to work (voice, vision on text-only models). It is data a maintainer updates, not a claim the code makes.

### R10 — Voice

**As a** student, **I want** voice to keep working when the instance has a Realtime-capable connection, **so that** choosing an open model for text does not remove it, and no broken mic appears when it cannot work.

Acceptance criteria:

1. The voice role has its own connection (R3) and its own model. By default it uses the default connection **only when that connection is OpenAI's**; otherwise voice is off until a voice connection is set. Voice is not guessed to work on any other server.
2. The browser no longer holds `https://api.openai.com/v1/realtime/calls`: the session response carries the calls URL, `<voice base_url>/realtime/calls`, validated server-side as `https` or (only for a loopback or private host) `http`. The default for OpenAI is unchanged.
3. The Realtime client mints the client secret through the voice connection's base URL. The session configuration, the tool bridge and the usage report are unchanged.
4. A Realtime-compatible third-party server is possible (it must accept the same client-secret route and SDP exchange); the documentation says OpenAI is the only provider verified.
5. With voice unavailable, the mic is inert exactly as today (`voice: false`).

### R11 — Cost and usage logging

**As an** operator, **I want** cost estimates that do not lie, **so that** logs stay trustworthy on any provider.

Acceptance criteria:

1. Token counts are logged for every provider (zero where the provider omits a field).
2. `cost_estimate_usd` uses the price settings (`AUTHORING_PRICE_*`, `TRANSCRIPTION_PRICE_*`, `VOICE_PRICE_*`) when a role's connection is OpenAI's **or** the price was explicitly set in the environment; otherwise it is `0.0`, so a Groq or local run never reports OpenAI's prices as its own. The documentation says so.
3. The stored columns and existing logs keep their names and types; no migration for this.

### R12 — The settings screen

**As an** administrator, **I want** one clear screen, **so that** I can configure and verify the AI backend without reading the documentation.

Acceptance criteria:

1. The « OpenAI » settings section becomes « AI provider » (admin-only, `SettingsSection.roles`). Layout: preset picker, base URL, API key (password field, emptied after save, `last4` shown), API style, structured-outputs mode; below, a row per role: model (with suggestions), reasoning effort, « Use a different provider for this role » (reveals the role's own connection fields); then Save, « Test » and, per R7, the live-check checkbox.
2. Fields fixed by the environment are read-only with a one-line reason (R8.2). Without an encryption key (`SECRETS_DIR` unset) the key fields explain and offer none, as today.
3. The first-run path of spec 013 is unchanged for the common case: the dashboard banner leads here, an OpenAI key and Save are enough (the defaults are OpenAI's).
4. Removing the key (confirmed) is available for each stored key. After a removal that leaves a role without a connection or model, the needs-config state applies (R8.4).
5. Everything is French or English per the interface language; new error codes and labels are in both catalogs (`i18n:check`, the English-sweep test). Provider and model names are not translated.
6. The section works at tablet width and with the keyboard; errors are tied to their fields; the key is never announced back.

### R13 — Documentation

Acceptance criteria:

1. A new `documentation/ai-providers.md`: the settings and their precedence, the presets, the two API styles and when to use which, structured-output modes, per-role connections, voice limits, the test action, cost logging, a Docker note (`http://host.docker.internal:11434/v1` for an Ollama on the host), the compatibility table (R9.3), the privacy statement per setup.
2. `documentation/index.md`, `first-run-setup.md` (key section generalised), `docker.md`, `running-locally.md` (new variables), `admin.md` and `CLAUDE.md` (the OpenAI-specific sentences) are updated; the `README.md` features, quick start step 3, configuration table and the « Your data and OpenAI » section say « AI provider », name Groq, Ollama and OpenAI as examples, and keep the privacy note accurate.

## 4. Non-functional requirements

### 4.1 Architecture

1. **The provider boundary holds.** Only `app/providers/` imports `openai` (the SDK is used for both styles: `AsyncOpenAI(base_url=…)` talks to Chat Completions and Responses alike). Services, routes and the authoring agent depend on the protocols in `base.py`. The Responses-shaped internal format stays the application's lingua franca; the Chat adapter is the only translator.
2. **One resolved configuration.** A service resolves environment > stored > default into an immutable configuration object and hands it to the hub, which builds the clients (per role, sharing a connection's underlying client where connections are equal). The hub's proxies and the swap-last rule of spec 013 stay; its API generalises from `set_key` to « apply this configuration ». Model names are read per call from the hub's current configuration, not from `Settings` at construction.
3. **Storage** is the `app_settings` table (spec 013): one JSON document for the non-secret settings and the encrypted keys inside it (or one row per connection key; the design chooses). No new table unless the design shows a need; if a migration is needed it follows `NNNN_slug` and the startup schema check, and the 013 backup-before-migration applies.
4. **Routes stay thin**: a service owns resolve, validate, store, test; the admin router calls it. `/api/admin/openai-key*` is replaced by the generalised routes or kept as aliases for one release; the frontend is the only consumer, so the design may replace them outright.
5. **Single process stays the rule**; the documentation repeats it.
6. The frontend extends the settings registry and catalogs only; no new state library.
7. The Chat adapter is a module of its own with its translators as pure functions, so they are tested without a network.

### 4.2 Performance

1. Per-request overhead is unchanged: the configuration is held in memory and read per call; the database is read at startup and on a settings change.
2. Applying a change does not block the event loop (clients are built off-loop, as spec 013) and is visible to the next call.
3. The test action's live checks use minimal tokens (a few dozen) and run roles in parallel.
4. Streaming first-token latency through the Chat adapter adds no buffering beyond what is needed to assemble a tool call.

### 4.3 Security and privacy

1. **Keys**: never returned, logged, put in an error, a test report, a health answer or a backup of the database alone; encrypted at rest with spec 013's cipher; a connection's key is only ever sent to that connection's base URL. Changing a base URL without re-entering the key **clears the key** (otherwise a stored key could be sent to a new host).
2. **Admin-only**, throttled, same-origin, in the route-guard test's allow-list.
3. **SSRF is an accepted, bounded risk**: an administrator chooses where the server makes requests, private networks included (R1.2). The URL is validated (scheme, no user-info), redirects to a different host are not followed with the bearer key, the response size read for `/models` is capped, and request timeouts apply. The base URL is shown back to the admin only.
4. **Data flow is documented per setup**: with a non-OpenAI provider, uploaded pages and conversations go to that provider under the operator's account with it; with a local server nothing leaves the host. The README says so.
5. **Prompt and pack content stays out of logs** (`DEBUG_LOG_PROMPTS` unchanged); provider text in errors is never forwarded to clients.
6. A model that ignores an instruction cannot break an invariant: verdicts, answer withholding and pack restriction are enforced in tools and code (existing). The documentation states that weaker models teach less well, and R9 says how to measure.

### 4.4 Reliability and quality

1. A save is atomic: validated first, stored, then swapped last; a failure at any step leaves the previous configuration in force (spec 013's rule, extended to every field).
2. A provider that errors, times out or rate-limits is translated to the existing domain errors (`ProviderUnavailable`, `ProviderTimeout`, `ProviderRateLimited`) for both styles; `AiNotConfigured` when no connection or model is resolved.
3. A stored configuration that cannot be read (corrupt JSON, undecryptable key) degrades to the needs-config state with a `warning` log and a visible « unreadable » flag, never a crash.
4. The offline suite covers: resolution and precedence (env explicit vs default vs stored, each field); the upgrade from a 013 database with a stored key; URL validation (schemes, user-info, trailing slash, private hosts allowed); key clearing on a base-URL change; the Responses request bodies against OpenAI (byte-identical to today) and against another host (no `prompt_cache_breakpoint`); the Chat translators on golden histories (text, images, tool calls and results, parallel calls); streaming assembly with fragmented tool arguments, usage, `length`, `<think>` stripping; structured output in both modes; the swap (a call in flight keeps its model, the next uses the new one); the save atomicity cases; the needs-config refusals; per-role connection fallback; the test action's classifications (with fakes); health; voice URL derivation and `voice` flag; cost logging rule; the route-guard allow-list; both catalogs and the English sweep.
5. Backend and frontend suites, `tsc`, lint and `i18n:check` pass. The OpenAI paths of `scripts.smoke` and the probes are unaffected.
6. A manual run against Groq (`openai/gpt-oss-120b`, `https://api.groq.com/openai/v1`) of a lesson turn with a tool call and a document-less authoring run is recorded in the compatibility table before the spec is closed. No credential is committed or written to a fixture.

### 4.5 Usability

1. The default path is unchanged for OpenAI users: paste a key, Save.
2. Choosing a preset is one click and fills everything but the key; a Custom connection needs a URL and, if the server wants one, a key.
3. Error messages name the cause and the action (« The server did not answer: check the address and that it is running », « This model does not accept images: pick a vision model for transcription ») in the interface language.
4. The test result is a short checklist per role, not a log.
5. Documentation lists, for each setup (OpenAI, Groq, Ollama on the host, Ollama in Docker), the exact values to enter.
