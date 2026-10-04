# 014 — AI provider configuration: design

Requirements: [requirements.md](./requirements.md) (R1–R13, NFR 4.x). Builds on spec 013 (`ProviderHub`, `OpenAIKeyService`, `Cipher`, `app_settings`).

## 1. Overview

The AI backend becomes an **`AiConfig`**: one default **connection** (`base_url`, `api_key`, `api_style`, `structured`) plus four **roles** (`tutor`, `authoring`, `transcription`, `voice`), each with a model, a reasoning effort and an optional own connection. `AiConfig` is resolved per field as environment (explicitly set) > stored > default, by `AiSettingsService`, and applied to `ProviderHub`, which builds one client per role and swaps them atomically.

Decisions that shape everything else:

1. **The application's internal message format stays Responses-shaped.** `OpenAIResponsesClient` is reused with a `base_url`. A new `OpenAIChatClient` is the only translator to Chat Completions, through pure functions in `chat_translate.py`. Nothing above `app/providers/` learns the style.
2. **`CompletionClient.complete` takes a `role`, not a model.** The role client owns model, reasoning effort, structured mode and connection. This is what lets transcription use another server than authoring, and a model change reach the next call.
3. **No migration.** Settings go in the existing `app_settings` table (key `ai_settings`). A stored 013 `openai_api_key` row is read as the default connection's key when `ai_settings` has none, and is mirrored back on save while the default connection is OpenAI's (rollback safety, R8.6).
4. **OpenAI-only wire fields are stripped for other hosts**: `prompt_cache_breakpoint` on content parts and tool `strict`. OpenAI requests stay byte-identical to today.
5. **The test action runs against the hub's clients** (the effective configuration), so it tests exactly what a student's request will use.
6. Verified before writing (Groq `openai/gpt-oss-120b`, Responses API, current adapter code): streaming tool calls, `store=False`, `prompt_cache_breakpoint`, strict `json_schema` + `reasoning.effort`, `function_call`/`function_call_output` history, `/models` listing. `strict` on Pydantic-generated tool schemas against Groq is not yet verified, hence decision 4.

## 2. Architecture

```
 env (Settings.model_fields_set) ─┐
 app_settings.ai_settings (JSON) ─┼─▶ AiSettingsService.resolve() ─▶ AiConfig ─▶ ProviderHub.apply()
 app_settings.openai_api_key     ─┘      │ save / test / models              │ build per-role clients, swap last
 (legacy, read + mirror)                 ▼                                   ▼
                                  admin routes /api/admin/ai*      ┌─ llm (tutor)         ──▶ ResponsesClient | ChatClient
                                                                   ├─ authoring_llm       ──▶   (role: authoring | transcription)
 TutorService ── hub.llm ─────────────────────────────────────────▶├─ realtime (voice)    ──▶ RealtimeClient(base_url)
 AuthoringAgent/Runner ── hub.authoring_llm + hub.config            └─ config (models, hosts, voice_available)
 VoiceService ── hub.realtime + hub.config.voice
 health / deps ── hub.configured, hub.config
```

`app/providers/` is the only package importing `openai`. New modules there: `_client.py` (the one place `AsyncOpenAI` is built), `openai_chat.py`. `chat_translate.py` and `ai_config` types import nothing from the SDK.

## 3. Components and interfaces

### 3.1 Domain: `app/domain/ai_config.py` (pure)

```python
Role = Literal["tutor", "authoring", "transcription", "voice"]
ApiStyle = Literal["responses", "chat"]
StructuredMode = Literal["schema", "json"]
Effort = Literal["low", "medium", "high"]          # None = not sent

OPENAI_BASE_URL = "https://api.openai.com/v1"

@dataclass(frozen=True)
class Connection:
    base_url: str
    api_key: str | None            # None: sends the placeholder bearer "no-key"
    api_style: ApiStyle = "responses"
    structured: StructuredMode = "schema"
    def __repr__(self) -> str: ...            # base_url, style, structured; never the key
    @property
    def host(self) -> str: ...                # urlsplit(base_url).hostname
    @property
    def is_openai(self) -> bool: ...          # host == "api.openai.com"

@dataclass(frozen=True)
class RoleConfig:
    role: Role
    model: str
    reasoning_effort: Effort | None
    connection: Connection
    voice_transcription_model: str | None = None   # voice only

@dataclass(frozen=True)
class AiConfig:
    tutor: RoleConfig
    authoring: RoleConfig
    transcription: RoleConfig
    voice: RoleConfig | None                        # None: voice off (R10.1)
    def role(self, name: Role) -> RoleConfig | None: ...
    def describe(self) -> dict[str, dict[str, str]]  # {role: {host, model, style}} for logs and health

def normalise_base_url(raw: str) -> str            # raises InvalidAiSettings(field) per R1.2
def calls_url(connection: Connection) -> str       # f"{base_url}/realtime/calls"; https, or http only for a loopback/private host
def priced(settings: Settings, connection: Connection, *price_fields: str) -> bool
    # connection.is_openai or any(f in settings.model_fields_set for f in price_fields)   (R11.2)
```

`normalise_base_url`: strip; scheme `http|https`; hostname required; no `username`/`password`/fragment; length ≤ 2048; strip trailing `/`; query strings allowed (rare gateways) but not logged. Private, loopback and link-local hosts are accepted.

### 3.2 Settings (`app/config.py`)

New fields (every one is also an environment variable; explicit presence is read from `model_fields_set`):

| Field | Default | Meaning |
|---|---|---|
| `openai_base_url` | `OPENAI_BASE_URL` | default connection URL |
| `ai_api_style` | `"responses"` | default connection style |
| `ai_structured_outputs` | `"schema"` | default connection structured mode |
| `tutor_reasoning_effort` | `""` | tutor effort (empty = not sent) |
| `{tutor,authoring,transcription,voice}_base_url` | `""` | role own connection; non-empty ⇒ the role's connection comes from the environment |
| `{role}_api_key` | `""` | its key |
| `{role}_api_style` | `"responses"` | its style |
| `{role}_structured_outputs` | `"schema"` | its structured mode |

Existing fields keep name and meaning. `require_api_key()` and `MissingApiKey` are removed from the app path; `scripts/*` use `load_ai_config()` (3.4). Effort fields become `Literal["", "low", "medium", "high"]`; today's values are valid. `tests/conftest.py::_isolate_env` adds the `AI_` prefix.

### 3.3 Storage and resolution: `app/services/ai_settings.py` (replaces `openai_key.py`)

Stored document, `app_settings` key `ai_settings` (`updated_by` = admin id):

```json
{"v": 1,
 "default": {"base_url": "…", "api_style": "responses", "structured": "schema",
             "key": {"ct": "<AES-GCM>", "last4": "ab12"}},
 "roles": {"tutor": {"model": "…", "reasoning_effort": "low",
                     "connection": {"base_url": "…", "api_style": "chat", "structured": "json", "key": null}},
           "voice": {"model": "…", "transcription_model": "…", "reasoning_effort": null, "connection": null}}}
```

Every field is optional; an absent field takes the default. `reasoning_effort: null` is stored as `""` to distinguish « not sent » from « unset »: absent = built-in default for the role, `""` = not sent. Unknown keys are ignored. Cipher context: `celestin:ai_key:v1:<slot>` with slot `default` or a role name (binds a ciphertext to its purpose). The legacy row uses spec 013's context.

```python
@dataclass(frozen=True)
class Field(Generic[T]):  value: T; source: Literal["environment", "stored", "default"]

class AiSettingsService:
    def __init__(self, repo: AppSettingsRepository, cipher: Cipher | None, hub: ProviderHub,
                 probe: ConnectionProbe, settings: Settings) -> None
    def load(self) -> None                         # startup: resolve → hub.apply, log ai_config_applied / warnings
    def view(self) -> AiSettingsView               # what the screen shows (3.8); no secret
    async def save(self, request: SaveAiSettings, actor_id: str) -> AiSettingsView
    async def models(self, slot: Slot) -> ModelListing       # suggestions, R2.2
    async def test(self, live: bool) -> AiTestReport
```

**Resolution (`_resolve() -> Resolved(config: AiConfig | None, view parts)`)**, per field:

1. Environment: the field name is in `settings.model_fields_set` and the value is meaningful (keys and model names: non-empty after strip; efforts: any valid value, `""` meaning not sent).
2. Stored document value.
3. Built-in default (`DEFAULT_MODELS`: tutor/authoring/transcription `gpt-5.6-terra`, voice `gpt-realtime-2.1`, voice transcription `gpt-4o-mini-transcribe`; efforts `None`/`medium`/`low`/`low`; today's values).

Connections: `default` from `openai_base_url`/`openai_api_key`/`ai_api_style`/`ai_structured_outputs`. A role has an own connection from the environment iff `{role}_base_url` is set (then every connection field of that role comes from `{role}_*` env, the key too, and the role's connection is locked); else from the stored `roles.<role>.connection` if present; else the default. Default key resolution: env `OPENAI_API_KEY` → stored `ai_settings.default.key` → legacy `openai_api_key` row → none. A key that cannot be decrypted (no cipher, bad ciphertext) sets `unreadable` on that connection and counts as no key.

A role resolves iff it has a model and a connection with a usable credential: **usable** = key present, or `not connection.is_openai` (keyless local servers). `AiConfig` is `None` unless tutor, authoring and transcription all resolve (**AI configured**). `voice` resolves iff `settings.voice_enabled`, a voice model exists, and its connection is either its own (any host: the administrator asserts Realtime support) or the default connection **and** `is_openai`.

**Save (`SaveAiSettings`, 3.8)** is a full replacement of the stored document, built from the request:

1. Validate shapes (`normalise_base_url`, model 1–200 chars trimmed, enums). Violations raise `InvalidAiSettings(fields=[…])` (422).
2. Environment-locked fields: if the request carries a value different from the effective one → `SettingFromEnvironment(fields)` (409). A request value equal to the effective one, or `null`, is accepted and ignored.
3. For every connection in the request: if its `base_url` differs from the stored one and the request has no new `api_key`, the stored key is **dropped** (R4.3.1). `clear_key` drops it too. A new `api_key` (trimmed, 1–256, no whitespace) is encrypted; with no cipher → `StorageUnavailable`.
4. Probe each connection that is new or whose `base_url`/key changed (not the unchanged ones): `rejected` → `AiKeyRejected` (422, `fields=[slot]`), `unreachable` → `ProviderUnavailable` (502), `limited` accepted. All under `self._lock`; probes run concurrently.
5. Write the document (`run_in_threadpool`), mirror the legacy row (default connection OpenAI-hosted with a key → write `openai_api_key` in 013's format; otherwise delete it), re-resolve, `hub.apply(config)` off the event loop, log `ai_settings_changed` (actor, roles and field names changed). If step 5 fails the previous config stays: the hub is swapped last.

Environment-locked defaults and a save that changes nothing are legal.

### 3.4 Loading outside the app: `app/services/ai_settings.py::load_ai_config(settings, repo=None, cipher=None) -> AiConfig`

Used by `scripts/smoke`, `probe`, `authoring_eval`, `document_eval`, `voice_smoke`. Resolves from the environment and, when `DATABASE_URL`'s database exists and `SECRETS_DIR` gives a cipher, from the stored settings; raises `MissingApiKey` (kept for the scripts) naming what is missing. Each script prints `provider host · model` for the roles it uses, then builds clients with `build_clients(settings, config)` (3.5).

### 3.5 Providers (`app/providers/`)

**`base.py`**: `LLMClient` gains `model: str` (read-only; for logs). `CompletionClient.complete(*, role: Literal["authoring","transcription"], instructions, input, schema=None, schema_name=None, max_output_tokens)`: `model` and `reasoning_effort` removed (the role client owns them). `ProviderEvent` and `CompletionResult` unchanged. `RealtimeClient` unchanged (`create_client_secret`). `KeyProbe` is replaced by:

```python
class ConnectionProbe(Protocol):
    async def check(self, connection: Connection, models: Sequence[str] = ()) -> ProbeResult
@dataclass(frozen=True)
class ProbeResult:
    status: Literal["ok", "rejected", "unreachable"]
    limited: bool = False
    models: list[ModelVisibility] = ...
    available: list[str] = ...        # up to 500 ids from /models, for suggestions
```

**`_client.py`**: `make_client(connection, timeout_s, max_retries=2) -> AsyncOpenAI` = `AsyncOpenAI(api_key=connection.api_key or "no-key", base_url=connection.base_url, timeout=timeout_s, http_client=DefaultAsyncHttpxClient(follow_redirects=False, timeout=timeout_s))`. A redirect surfaces as an error (R security: never follow with a bearer key).

**`openai_responses.py`**: `OpenAIResponsesClient(connection, model, timeout_s, reasoning_effort=None, structured="schema", role=...)`.
- `stream(input, tools)`: `input = wire_input(input, openai=connection.is_openai)`, `tools = wire_tools(tools, openai=…)`; adds `reasoning={"effort": e}` when set; `store=False` as today.
- `complete(role, …)`: `completion_request(...)` gains `openai: bool`, `structured`, uses the client's model and effort. `schema` mode: today's request. `json` mode: `text.format = {"type": "json_object"}` and `json_instruction(schema)` appended to the developer message text. The response goes through `completion_result(parse_json=…)`, which in `json` mode first runs `extract_json(text)` (3.6).
- `wire_input`: deep-copies content parts without `prompt_cache_breakpoint` when not OpenAI; identity (same objects) when OpenAI, so OpenAI bodies stay byte-identical. `wire_tools`: drops `strict` when not OpenAI.
- `_map_events` unchanged (unknown events ignored); usage fields may be `None` (`token_counts` already tolerates).

**`chat_translate.py`** (pure, no SDK):
- `to_messages(input, instructions: list[str] | None) -> list[dict]`:
  - Leading `developer`/`system` messages (and `instructions`) merge into one `system` string at position 0; a `developer` message after the first non-system item becomes a `user` message with the same text (templates of open models often reject a late or second system message).
  - `user` content: string kept; parts list → `[{"type":"text","text":…}|{"type":"image_url","image_url":{"url":…, "detail":…}}]` (a list only when an image is present, else the joined string). `assistant` content: parts joined into a string.
  - `function_call` items → one assistant message with `tool_calls=[{"id": call_id, "type":"function", "function":{"name","arguments"}}]`; consecutive calls, and a directly preceding assistant text message with no tool calls, merge into it. `function_call_output` → `{"role":"tool","tool_call_id":…,"content": output}`.
- `to_tools(tools, openai: bool) -> list[dict]`: `{"type":"function","function":{"name","description","parameters"[, "strict"]}}`; `strict` only when `openai`.
- `ThinkStripper`: incremental filter removing `<think>…</think>` across chunk boundaries; `strip_think(text)`.
- `usage_dict(chat_usage) -> dict` in the Responses shape (`input_tokens`, `output_tokens`, `input_tokens_details.cached_tokens`, `output_tokens_details.reasoning_tokens`), zeros for missing fields.
- `extract_json(text) -> str`: strips `<think>`, a leading code fence, and surrounding prose up to the first `{`/last `}`.
- `json_instruction(schema) -> str`: `"Output exactly one JSON object and nothing else. It must validate against this JSON Schema:\n" + json`. Language-neutral on purpose; used only in `json` mode, so default behaviour (and French bytes) are untouched.

**`openai_chat.py`**: `OpenAIChatClient(connection, model, timeout_s, reasoning_effort, structured, role)`.
- `stream`: `chat.completions.create(model, messages, tools or NOT_GIVEN, stream=True, stream_options={"include_usage": True}, reasoning_effort=… if set)`. Per chunk: `delta.content` through `ThinkStripper` → `TextDelta`; `delta.tool_calls[i]` accumulated by `index` (id, name, argument fragments); reasoning fields ignored. At the end: `ToolCallRequested` per call in index order (an empty `id` is replaced by `call_{index}`), then `Completed(usage_dict)`. `finish_reason == "length"` → `Failed("provider_unavailable", "output limit")`. Exceptions go through `translate` (3.7).
- `complete`: `messages = to_messages(input, instructions)`; `response_format` per structured mode (`json_schema` strict with `to_strict_json_schema`, or `{"type":"json_object"}` + `json_instruction`); output limit as `max_completion_tokens`, switching the instance to `max_tokens` (remembered) on a `BadRequestError` whose message names `max_completion_tokens`, then retrying once. `finish_reason == "length"` → `ProviderOutputTruncated`. Text through `strip_think`; JSON through `extract_json` + `json.loads` (`ProviderOutputInvalid` on failure or a non-object).

**`openai_realtime.py`**: `OpenAIRealtimeClient(connection, timeout_s)` builds its client with `make_client`. Endpoint is the connection's `base_url`.

**`openai_probe.py`** → `ConnectionProbe` implementation `OpenAIConnectionProbe`: `models.list()` with `max_retries=0`, 15 s: `AuthenticationError` → `rejected`; `PermissionDeniedError` → `ok` + `limited`; `NotFoundError`/status 404, 405, 501 on the listing → `ok` + `limited` (server without a models route); `RateLimitError` → continues as ok; connection/timeout/5xx/other → `unreachable`. `available` = first 500 model ids sorted. Visibility of wanted models as today (`models.retrieve`; `NotFoundError` → false; others → null), skipped when the listing was `limited`. Nothing is logged or re-raised with provider text.

**`hub.py`**:

```python
@dataclass(frozen=True)
class Clients:
    config: AiConfig
    tutor: LLMClient
    authoring: CompletionClient
    transcription: CompletionClient
    realtime: RealtimeClient | None

ClientFactory = Callable[[Settings, AiConfig], Clients]

def build_clients(settings: Settings, config: AiConfig) -> Clients   # per role: style → Responses | Chat client
class ProviderHub:
    configured -> bool                    # config is not None
    config -> AiConfig | None             # read once per use
    voice_available -> bool               # realtime is not None
    def apply(self, config: AiConfig | None) -> None     # build all, swap in one assignment, under the lock
    def current(self) -> Clients                          # raises AiNotConfigured
    llm: LLMClient; authoring_llm: CompletionClient; realtime: RealtimeClient   # proxies as today
```

The proxies resolve `current()` per call. `_CompletionProxy.complete(role=…)` routes by role; `_RealtimeProxy` raises `VoiceDisabled` when `realtime is None`. `_LLMProxy.model` reads the current tutor model. Timeouts: tutor `request_timeout_s`; authoring and transcription `authoring_call_timeout_s`; realtime `request_timeout_s`.

### 3.6 Errors (`app/providers/_errors.py`, `app/domain/errors.py`)

`translate` distinguishes (all subclasses of `ProviderUnavailable`, so every existing `except` keeps working, and `PROVIDER_ERRORS` needs no change):

| SDK | Domain | Code | Status |
|---|---|---|---|
| `AuthenticationError`, `PermissionDeniedError` | `ProviderAuthRejected` | `provider_auth_rejected` | 502 |
| `NotFoundError` | `ProviderModelNotFound` | `provider_model_not_found` | 502 |
| `BadRequestError`, `UnprocessableEntityError` | `ProviderRejectedRequest` | `provider_rejected_request` | 502 |
| `RateLimitError`, timeouts | unchanged | | |
| other `APIError` | `ProviderUnavailable` | | |

The three new codes render the same student-facing message as `provider_unavailable` (catalog entries added in both languages). `AiNotConfigured` message becomes provider-neutral (« …to set up the AI provider »). Spec 013's `InvalidOpenAIKey`, `OpenAIKeyRejected`, `KeyFromEnvironment` are replaced by `InvalidAiSettings` (422 `invalid_ai_settings`, `params={"fields": …}` for the log), `AiKeyRejected` (422 `ai_key_rejected`) and `SettingFromEnvironment` (409 `setting_from_environment`); `StorageUnavailable` stays. Catalog entries (fr/en) replace the old keys; the wire body stays `{code, message}`.

### 3.7 Services that read models

- **`TutorService`**: logs `self._llm.model`; no other change (the client owns the model).
- **`AuthoringAgent(llm, prompts, settings, ai: AiConfigSource)`**, `AiConfigSource` = `Protocol` with `config: AiConfig | None` (the hub). `_call` passes `role="authoring"`; transcription calls `role="transcription"`; both without model or effort. `estimate_cost(usage, settings, config)` applies the pricing rule: a role's price fields are used iff `priced(settings, role.connection, "<role>_price_in", …)`, else that share is `0.0`. Token counts are always recorded. `AuthoringRunner` logs and stores `model=ai.config.authoring.model` (read at run start; `AiNotConfigured` before side effects, as today via `AiReady`).
- **`VoiceService(realtime, prompts, settings, ai)`**: session config uses `ai.config.voice` (model, transcription model, effort); the response carries `calls_url` (`calls_url(voice.connection)`); `voice_cost` uses `priced(…)` for the voice price fields.
- **`routes/voice.py`**: refuses with `VoiceDisabled` unless `settings.voice_enabled and hub.voice_available`.
- **`routes/health.py`**: `model`, `authoring_model`, `voice_model` from `hub.config` (strings, `null` when absent); `ai_configured = hub.configured`; `voice = settings.voice_enabled and hub.voice_available`.
- **`deps.require_ai`** unchanged in behaviour (`hub.configured`); docstring updated.
- **`main.py`**: `app.state.keys` → `app.state.ai_settings` (`AiSettingsService`); `create_app(..., probe: ConnectionProbe | None)`; agent, runner, voice service receive the hub as `ai`.

### 3.8 Admin API (`app/api/routes/admin.py`, `app/api/schemas/ai.py`)

All routes: `AdminDep`, throttled per admin (`login_limiter`, key `ai-settings:{id}`), same-origin, in the route-guard allow-list. `/api/admin/openai-key*` is removed.

| Route | Body → Response |
|---|---|
| `GET /api/admin/ai` | → `AiSettingsView` |
| `PUT /api/admin/ai` | `SaveAiSettings` → `AiSettingsView` |
| `GET /api/admin/ai/models?slot=default\|tutor\|authoring\|transcription\|voice` | → `{status, ids: [str]}` (suggestions from the slot's effective connection; empty when `limited`) |
| `POST /api/admin/ai/test` | `{live: bool}` → `AiTestReport` |

```python
class FieldDTO(_Model, Generic[T]): value: T | None; source: Literal["environment","stored","default"]
class KeyDTO(_Model): source: Literal["environment","stored","none"]; last4: str | None; unreadable: bool
class ConnectionDTO(_Model): base_url: FieldDTO[str]; api_style: FieldDTO[ApiStyle]; structured: FieldDTO[StructuredMode]; key: KeyDTO
class RoleDTO(_Model):
    model: FieldDTO[str]; reasoning_effort: FieldDTO[Effort | None]
    voice_transcription_model: FieldDTO[str] | None      # voice only
    own_connection: ConnectionDTO | None                  # None: uses the default connection
    uses_default: bool
    resolved: bool                                        # the role has a model and a usable connection
class AiSettingsView(_Model):
    can_store: bool; configured: bool; voice_available: bool
    default: ConnectionDTO; roles: dict[Role, RoleDTO]

class ConnectionInput(_Model): base_url: str; api_style: ApiStyle; structured: StructuredMode
                               api_key: str | None = None; clear_key: bool = False
class RoleInput(_Model): model: str | None; reasoning_effort: Effort | Literal[""] | None
                         voice_transcription_model: str | None = None; connection: ConnectionInput | None = None
class SaveAiSettings(_Model): default: ConnectionInput; roles: dict[Role, RoleInput]
    # model None / reasoning_effort None: unset (built-in default); "" effort: not sent; connection None: use the default

class RoleReportDTO(_Model):
    role: Role; connection: Literal["ok","rejected","unreachable"]; limited: bool
    model_visible: bool | None
    live: LiveResultDTO | None
class LiveResultDTO(_Model): status: Literal["ok","failed"]; code: LiveCode | None
LiveCode = Literal["rejected","unreachable","model_not_found","no_tool_calls","no_image_input","schema_unsupported","other"]
class AiTestReport(_Model): roles: list[RoleReportDTO]    # only roles that resolve; voice absent when off
```

`SaveAiSettings` is the whole screen's state. `api_key` and `clear_key` are never echoed. Validation limits live in the schema (`max_length`) and in `ai_config.normalise_base_url`.

### 3.9 Test action: `app/services/ai_test.py`

`AiSettingsService.test(live)` takes `hub.current()` (`AiNotConfigured` if none) and its `config`. It probes each *distinct* connection once (`ConnectionProbe.check(connection, wanted_models)`), fills `connection`, `limited`, `model_visible` per role, then, if `live`, runs the checks concurrently, each in `asyncio.wait_for(…, 45)`:

| Role | Check (through the hub's clients) | Pass |
|---|---|---|
| tutor | `llm.stream(input=[user "Call the ping tool with ok=true."], tools=[ping])`; stop at the first event of interest | a `ToolCallRequested` for `ping`, then (or without waiting for) the stream end without `Failed` |
| authoring | `authoring.complete(role="authoring", schema=Ping, max_output_tokens=2000)` | parsed into `Ping{ok: bool, word: str}` |
| transcription | `transcription.complete(role="transcription", input=[user [text, input_image(PNG of "42" rendered with Pillow, 96×48)]], max_output_tokens=2000)` | the reply contains `42` |
| voice | `realtime.create_client_secret(session={"type":"realtime","model":…}, ttl_s=10)` | a secret is returned (no audio, no session use) |

Failure classification: `ProviderAuthRejected` → `rejected`; `ProviderModelNotFound` → `model_not_found`; `ProviderRejectedRequest` → `no_tool_calls` (tutor), `schema_unsupported` (authoring), `no_image_input` (transcription), `other` (voice); `ProviderOutputInvalid` → `schema_unsupported`; transcription completing without `42` → `no_image_input`; tutor stream with no tool call → `no_tool_calls`; `ProviderTimeout`/`ProviderUnavailable` → `unreachable`; anything else → `other`. The report never carries provider text. `ping` is a one-argument function tool, declared in the module, not in the registry.

### 3.10 Frontend

- `lib/admin.ts`: types of 3.8; `aiSettingsQuery`, `saveAiSettings`, `aiModels(slot)`, `testAi(live)`, `afterAiChange(queryClient, view)` (sets the query data, invalidates `health` and the auth-config-independent dashboard banner query). Old `openai*` functions removed.
- `lib/ai-presets.ts`: `PRESETS: {id, label, base_url, api_style, models?: Partial<Record<Role, string>>, keyRequired, hint}`:

  | Preset | URL | Style | Suggested models |
  |---|---|---|---|
  | `openai` | `https://api.openai.com/v1` | responses | `gpt-5.6-terra` ×3, voice `gpt-realtime-2.1` |
  | `groq` | `https://api.groq.com/openai/v1` | responses | tutor, authoring `openai/gpt-oss-120b`; transcription `qwen/qwen3.8-27b` (vision; verify with the test) |
  | `openrouter` | `https://openrouter.ai/api/v1` | responses | none |
  | `ollama` | `http://localhost:11434/v1` | chat | none (placeholder `qwen3:8b`) |
  | `custom` | empty | responses | none |

  Applying a preset sets URL and style, fills model fields that are empty or still the previous preset's suggestion, and never touches keys. Pure data, in one file.
- `settings/ai-section.tsx` replaces `openai-section.tsx`; `sections.ts` entry `ai` (title `settings_ai_title`, `roles: ["admin"]`). Structure: preset select; `ConnectionFields` (URL, key, style, structured) used for the default and, inside a collapsed `<details>` per role, for a role's own connection; four `RoleRow`s (model input with `<datalist>` filled from `aiModels(slot)` on focus or by a « List models » button, effort select, voice transcription model for voice); Save; « Test » + live-check checkbox with its cost sentence; `TestReport` as a per-role checklist. Locked fields render `disabled` with `settings_ai_locked` text. Without `can_store`: key inputs hidden with the existing explanation. The submit builds `SaveAiSettings` from form state; a key input left empty is `api_key: null`; a changed URL with an empty key shows a one-line warning that the stored key will be removed.
- `lib/tutor/voice/session.ts`: `CALLS_URL` removed; `fetchSdp(offerSdp, secret, callsUrl)`; the session response type gains `calls_url`, read by `use-voice-session.ts` and passed down. The dashboard `AiBanner` and its message use « AI provider ».
- Catalog keys `settings_ai_*` in `messages/en.json` and `fr.json`, same variables; `settings_openai_*` removed; error codes of 3.6 are server-rendered.

### 3.11 Scripts

`smoke`, `probe`, `authoring_eval`, `document_eval`, `voice_smoke` build clients with `load_ai_config` + `build_clients` and print `provider host · model`. They keep their cost warnings. `probe`/`smoke` use `clients.tutor`; the evals use `clients.authoring` with the agent's `ai` source (a `SimpleNamespace(config=config)`).

## 4. Data models

No table, no migration. `app_settings` rows: `ai_settings` (3.3) and the legacy `openai_api_key` (013: `{"v":1,"ct":…,"last4":…}`, context `celestin:openai_api_key:v1`), the latter mirrored per 3.3 step 5. `AppSettingRow` docstring updated. `voice_usage.cost_estimate_usd` and `chapters.cost_estimate_usd` keep their meaning (0.0 when unpriced).

## 5. Error handling

| Situation | Behaviour |
|---|---|
| No role set resolves (no credential, no model) | `hub.config is None`: the seven AI routes answer `503 ai_not_configured`; banner; health `ai_configured:false` |
| Stored document corrupt or key undecryptable | that connection's key counts as absent, `unreadable` flag in the view, `ai_settings_unreadable` warning; no crash |
| Save: invalid URL / model / enum | `422 invalid_ai_settings` (fields named in logs only); nothing stored |
| Save: changes an env-locked field | `409 setting_from_environment` |
| Save: key rejected / server unreachable | `422 ai_key_rejected` / `502 provider_unavailable`; previous config kept |
| Save: no cipher but a key is submitted | `409 storage_unavailable` (as 013) |
| A provider call fails | translated to the domain errors of 3.6; streams end with `Failed`; authoring maps to its existing `provider` failure |
| Redirect from the provider | not followed; classified as unreachable |
| Voice requested with `voice` off | `503 voice_disabled` (existing) |
| Test: a check times out (45 s) | role `live.code = "unreachable"` |
| Concurrent saves | serialised by the service lock; the hub swap is atomic |

## 6. Testing strategy

Offline, no network; the live Groq run is manual and recorded (R9.3, NFR 4.4.6).

- **`tests/unit/test_ai_config.py`**: `normalise_base_url` (schemes, user-info, fragment, trailing slash, length, private hosts accepted), `Connection.is_openai`/repr redaction, `calls_url`, `priced`.
- **`test_ai_settings_service.py`** (replaces `test_openai_key_service.py`; uses `FakeProbe`, a scripted `ConnectionProbe`, and `Factory`): precedence per field (env explicit vs default vs stored, empty env values), role own connection from env, upgrade from a 013 row (legacy key becomes the default key; no `ai_settings` needed), mirror write/delete, save validation, env-locked refusal, key drop on URL change, probe only for changed connections, rejected/unreachable leave the old config and rows, `StorageUnavailable`, unreadable handling, AI-configured rule (keyless non-OpenAI configured; keyless OpenAI not), voice resolution rule, models listing, logs carry no secret.
- **`test_provider_hub.py`** (rewritten): `apply` swaps atomically, proxies route by role, a call in flight keeps its client, `AiNotConfigured` with none, voice proxy refuses when `realtime is None`.
- **`test_openai_adapter.py`** (extended): request bodies against OpenAI equal today's golden (including `prompt_cache_breakpoint`, tool `strict`); against another host both are absent and the input objects are not mutated; `reasoning` only when set; `json` mode request and parsing; events unchanged; error translation table of 3.6.
- **`test_chat_translate.py`**: golden message lists from `history.to_provider_input` shapes and `prompt_service.build_input` (developer/state placement, text, images, call + output pairs, consecutive calls, assistant text before a call), tools, `ThinkStripper` on split tags, `usage_dict` with missing fields, `extract_json`, `json_instruction`.
- **`test_openai_chat_adapter.py`**: streaming with a scripted chunk iterator (fragmented tool arguments, parallel calls, `finish_reason="length"`, usage chunk, reasoning fields ignored, `<think>`), `complete` (schema, json, truncation, `max_tokens` fallback, effort), error translation.
- **`test_openai_probe.py`** (extended): 404 listing → limited; 401, 403, timeout; `available` capped at 500; visibility.
- **`test_openai_realtime_adapter.py`**: client built on the connection's base URL.
- **`test_ai_test.py`**: report assembly, each live check's pass and every failure classification with scripted fakes, timeouts, no provider text, admin-only.
- **Integration**: `test_ai_settings.py` (replaces `test_openai_key.py`): roles, throttle, GET never returns a key, PUT round trip, 409/422 paths, models and test routes; `test_needs_key.py` adapted (needs-config); `test_voice_endpoint.py` (`calls_url`, voice off on a non-OpenAI default); `test_health` assertions; route-guard allow-list; `test_layering.py` allow-list updated (`_client.py`, `openai_chat.py`, `openai_probe.py`, `openai_realtime.py`, `openai_responses.py`, `_errors.py`); `test_error_messages_fr.py` and the catalog parity tests with the new codes; authoring agent/runner tests pass `role` and the `ai` source (`FakeCompletion` records `role`); `test_authoring_*` cost tests for the pricing rule.
- **Frontend**: `ai-section.test.tsx` (render per source, presets, locked fields, save payload, key warning on URL change, test report, English sweep), `ai-presets.test.ts`, voice session test with `calls_url`, `i18n:check`.
- **Manual** (before closing): Groq `openai/gpt-oss-120b` for tutor and authoring via the UI, the test action with live checks, `scripts.smoke`, one lesson turn with a tool call, one text-source authoring run (documents need a vision model); result into `documentation/ai-providers.md`'s table.

## 7. Performance considerations

The hub holds the config in memory; routes read it with one attribute access. The database is read at startup and on a save. Clients are built off the event loop (`run_in_threadpool`). The Chat adapter streams text deltas as received; only tool-call arguments are buffered, as with Responses. The probe lists models once per distinct connection; live checks run in parallel with small outputs. `ThinkStripper` is O(n) with a bounded carry buffer (the length of `</think>`).

## 8. Security considerations

- Keys: encrypted per slot with purpose-bound contexts; never in a DTO, log, error, health or test report; a connection's key goes only to its base URL; changing the URL drops the stored key unless a new key comes with it. Logs name hosts, never URLs with query strings or keys.
- `follow_redirects=False` on every client; `/models` listing capped at 500 ids and bounded by timeouts.
- SSRF to private addresses is an accepted administrator capability (R1.2), documented; routes are admin-only, throttled, same-origin.
- `prompt_cache_breakpoint` and `strict` are not sent to hosts that did not ask for them; `store=False` is sent everywhere.
- Invariants do not depend on the model: tools, checker and pack restriction are unchanged. A model that ignores tools simply produces no card; the test action's `no_tool_calls` makes that visible before students meet it.
- The legacy mirror row keeps an OpenAI key encrypted exactly as before; deleting the default key deletes it.

## 9. Monitoring and observability

Logs (JSON, existing logger): `ai_config_applied` (startup and each change: per role `host`, `model`, `style`; no keys), `ai_settings_changed` (`user_id`, roles and field names changed), `ai_settings_unreadable` (warning), `ai_not_configured` (warning, existing), `ai_test` (per role: `connection`, `live` code, duration). `turn_complete` already logs `model`, now the live one. `authoring_started` logs the live model. Provider failures keep `provider_*` codes, now distinguishing auth, model-not-found and rejected-request. `GET /api/health` reports effective models, `ai_configured` and `voice`.
