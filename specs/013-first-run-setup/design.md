# 013 — First-run setup: design

Requirements: [requirements.md](./requirements.md). Section numbers below (R1 …) refer to it.

## 1. Overview

Four mechanisms, each small, composed in `create_app`:

1. **Setup state** — "no user exists" is the pending state. `AuthService` answers it, `POST /api/setup` ends it atomically, `register` refuses while it lasts. The frontend adds `/setup` and redirects the signed-out pages to it.
2. **Secrets** — `load_secrets(settings)` resolves the session secret and the encryption key from the environment or from files in `SECRETS_DIR`, generating the files on first boot.
3. **Provider hub** — a `ProviderHub` owns the three OpenAI clients and hands out three stable *proxies* (`hub.llm`, `hub.authoring_llm`, `hub.realtime`) that resolve the current client per call. Replacing the key swaps the clients under the proxies; nothing that captured a proxy (the authoring agent, the dependencies, tests' overrides) changes. An `OpenAIKeyService` resolves the effective key (environment > stored), stores it encrypted, and drives the hub.
4. **Operations** — `scripts.migrate` (backup, then `alembic upgrade head`), `COOKIE_SECURE=auto`, an entrypoint that fixes `/data` ownership and drops privileges, no required variable.

Deviations from the requirements, decided here:

| Requirement | Decision | Why |
|---|---|---|
| R7.2 « before any side effect … no upload is read » | A route dependency refuses with `503` before the route body runs. For the two upload routes FastAPI has already read the multipart body (bounded by `DOCUMENT_MAX_BYTES`) when dependencies run; it is discarded, nothing is stored or processed. | A path-matching ASGI guard would refuse earlier but couples a middleware to route patterns. |
| R7.2 « for an admin, the settings screen » | One message for everyone: ask whoever runs the instance to add the key. | Every refused route is a student route; an admin gets `403` there (spec 012), so an admin never sees this message. The admin's pointer is the dashboard banner (R7.5). |
| R5.7 « `ok` for a valid key » | The check also returns `limited: true` when the provider answers `403` to the models call. | A restricted key without the models scope is valid for the Responses API but gets `403` on `GET /v1/models` ([OpenAI community reports](https://community.openai.com/t/missing-scopes-model-request-on-restricted-api-key/1371602)). Rejecting it would lock out a working key. Only `401` is « rejected ». |
| R8.2 « trusted proxy » | Decided on `TRUST_PROXY` and `X-Forwarded-Proto`, in one helper, not on uvicorn's own `--proxy-headers`. | One rule shared with `client_host`; testable without a server. |

## 2. Architecture

```
 browser ──HTTP(S)──► Caddy :8080 ──/api/*──► uvicorn 127.0.0.1:8000 (one worker, FastAPI)
                         │                         │
                         └──everything else──► Node 127.0.0.1:3000 (SSR)   composition root (create_app)
                                                   │
  /data (volume)                                   ├─ Settings ─ load_secrets ─► Secrets{session_secret, encryption_key?}
   ├─ celestin.db   ◄──── repositories ────────────┤
   │    ├─ users, sessions, courses …               ├─ AuthService(secret) ── setup_required / setup / register
   │    └─ app_settings (openai_api_key: AES-GCM)   ├─ OpenAIKeyService ─ Cipher(encryption_key) ─ AppSettingsRepository
   ├─ secrets/  session_secret, encryption_key      │        │ effective key: env > stored
   ├─ backups/  celestin-<utc>-from-<rev>.db        │        ▼
   └─ caddy/    certificates                        └─ ProviderHub ── proxies ──► tutor / authoring+transcription / realtime
                                                           ▲  set_key(key | None) rebuilds the three clients atomically
 entrypoint: (root) chown /data → setpriv uid 10001 → scripts.migrate → uvicorn, node, caddy
```

Request flow of a refused AI route: `StudentDep` (401/403) → `require_ai` (`503 ai_not_configured`) → route body.

## 3. Components and interfaces

### 3.1 Settings (`app/config.py`)

```python
cookie_secure: bool | Literal["auto"] = True          # "auto": Secure iff the request arrived over HTTPS
secrets_dir: Path | None = None                       # "" → None (before-validator); relative → resolved like prompts_dir
migration_backups_kept: Annotated[int, Field(ge=1)] = 5
```

`require_session_secret()` and `require_api_key()` stay for the scripts. `create_app` no longer calls `require_api_key()`.

### 3.2 Secrets (`app/secret_files.py`, new; not `secrets.py`, which shadows the standard library name in reading)

```python
@dataclass(frozen=True)
class Secrets:
    session_secret: str
    encryption_key: bytes | None          # 32 bytes; None without SECRETS_DIR

class SecretFileError(RuntimeError): ...  # names the file and the remedy

def load_secrets(settings: Settings) -> Secrets
```

- `secrets_dir is None`: `session_secret = settings.require_session_secret()` (unchanged failure), `encryption_key = None`.
- Otherwise `secrets_dir.mkdir(mode=0o700, parents=True, exist_ok=True)`, best-effort `chmod 0o700`.
  - Session secret: `settings.session_secret` when it has ≥ 16 characters; else `session_secret` file; created when missing.
  - Encryption key: `encryption_key` file, created when missing; always read from the file (no environment override).
- File format: 64 lowercase hex characters and a newline (32 bytes of `secrets.token_bytes`). Created with `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)`; never opened for writing when it exists.
- Validation on read: `session_secret` ≥ 32 non-whitespace characters (a hand-made file is accepted); `encryption_key` exactly 64 hex characters. Unreadable or invalid → `SecretFileError(f"{path}: …; delete it to generate a new one (this signs everyone out / makes the stored OpenAI key unreadable)")`. Never regenerated silently.
- Called once, first thing in `create_app`; `AuthService` receives `secrets.session_secret` (new keyword `secret: str | None = None`; `None` keeps `settings.require_session_secret()`, so every existing construction and test is untouched).

### 3.3 Cipher (`app/services/cipher.py`, new)

`cryptography` (new dependency, `>=44`): `AESGCM` is the vetted authenticated primitive in the standard Python crypto library of record; Fernet (AES-128-CBC) is weaker and no simpler.

```python
class Cipher:
    def __init__(self, key: bytes) -> None            # 32 bytes
    def encrypt(self, plaintext: str, *, context: str) -> str    # urlsafe-b64(nonce12 || ciphertext || tag)
    def decrypt(self, token: str, *, context: str) -> str        # raises CipherError on any failure
```

A fresh 12-byte `os.urandom` nonce per call; `context` is the associated data (`"celestin:openai_api_key:v1"`), binding a ciphertext to its use. `InvalidTag`, bad base64 and wrong length all raise `CipherError`.

### 3.4 Persistence

`AppSettingRow` (`app/db/models.py`):

```python
class AppSettingRow(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)   # a user id, no foreign key
```

Migration `0009_app_settings.py`: `op.create_table` only (no change to an existing table, so no SQLite rebuild); `downgrade` drops it. Row `openai_api_key`, value JSON `{"v": 1, "ct": "<cipher token>", "last4": "ab12"}`.

`AppSettingsRepository(_Repo)`: `get(key) -> str | None`, `put(key, value, updated_by)` (upsert with `session.merge`), `delete(key) -> bool`. Added to `Repositories` as `app_settings`.

`UserRepository` gains:

```python
def any_exists(self) -> bool                       # select(exists(select(UserRow.id)))
def create_first_admin(self, email, name, password_hash, locale) -> User
```

`create_first_admin` is one statement, `INSERT … SELECT <literals> WHERE NOT EXISTS (SELECT 1 FROM users)` (`insert(UserRow).from_select(...)` over `select(literal(...))`), then `commit`. `rowcount == 0` → `SetupDone`. SQLite takes the write lock at the start of the statement, so the check and the insert are indivisible; a concurrent second statement waits and finds a row. (PostgreSQL would need `SERIALIZABLE` or an advisory lock; out of scope.)

### 3.5 Setup state and first admin (`AuthService`)

```python
def setup_required(self) -> bool       # False is cached for the life of the process; True is re-read every time
def setup(self, email, password, name, locale) -> tuple[User, str]
```

- `setup_required`: `if self._users_exist: return False; self._users_exist = self._repos.users.any_exists(); return not self._users_exist`. Users are never deleted, so the cached `False` stays true.
- `setup`: `normalise_email`, `name.strip()`, `check_password` → `WeakPassword`; `create_first_admin` (raises `SetupDone`); sets `_users_exist = True`; logs `setup_completed`; returns the user and `open_session(user)`.
- `register` calls `setup_required()` first and raises `SetupRequired` before the registration-mode check (R3.1).
- `login` is unchanged.

### 3.6 Provider hub (`app/providers/hub.py`, new) and probe

`app/providers/base.py` gains:

```python
@dataclass(frozen=True)
class ModelVisibility: model: str; visible: bool | None        # None: the key cannot tell
@dataclass(frozen=True)
class ProbeResult: status: Literal["ok", "rejected", "unreachable"]; limited: bool; models: list[ModelVisibility]

class KeyProbe(Protocol):
    async def check(self, api_key: str, models: Sequence[str] = ()) -> ProbeResult: ...
```

`app/providers/openai_probe.py` — `OpenAIKeyProbe`, the only new importer of `openai`:

- `AsyncOpenAI(api_key=…, timeout=15, max_retries=0)`; `await client.models.list()` (first page only).
- `openai.AuthenticationError` (401) → `rejected`. `openai.PermissionDeniedError` (403) → `ok`, `limited=True`, every model `visible=None`. `APIConnectionError`, `APITimeoutError` and any other `APIStatusError` (5xx) → `unreachable`. `RateLimitError` → `ok` (it authenticated).
- For each requested model (only the test action asks): `models.retrieve(id)`; `NotFoundError` → `visible=False`; success → `True`; `PermissionDeniedError` or anything else → `None`.
- No log line includes the key; exceptions are not re-raised with their text.

`ProviderHub`:

```python
class ProviderHub:
    def __init__(self, settings: Settings, factory: ClientFactory = build_clients) -> None
    llm: LLMClient                 # proxy; .stream(...) resolves the current client when called
    authoring_llm: CompletionClient
    realtime: RealtimeClient
    @property
    def configured(self) -> bool
    def set_key(self, api_key: str | None) -> None   # builds all three, then one attribute assignment under a lock
```

`build_clients(settings, key) -> Clients(llm, authoring, realtime)` is today's three constructions from `main.py`, moved (`OpenAIResponsesClient(key, settings.openai_model, settings.request_timeout_s)`, the authoring one with `authoring_model` / `authoring_call_timeout_s`, `OpenAIRealtimeClient`). A proxy method resolves `hub._clients` once at call start; `None` → `AiNotConfigured`. A stream or call in flight keeps the client object it resolved; the previous clients are left to be garbage collected (their connections close when unreferenced).

`create_app` wiring: `app.state.hub = hub`; `app.state.llm = hub.llm`; `app.state.realtime = hub.realtime`; `app.state.authoring_llm = hub.authoring_llm`; `AuthoringAgent(app.state.authoring_llm, …)` as before. Dependencies, `use_fake_authoring` and the `dependency_overrides` of the tests are unchanged.

### 3.7 Key service (`app/services/openai_key.py`, new)

```python
@dataclass(frozen=True)
class KeyState: source: Literal["environment","stored","none"]; last4: str | None; stored_unreadable: bool; can_store: bool
@dataclass(frozen=True)
class ModelReport: role: Literal["tutor","authoring","transcription","voice"]; model: str; visible: bool | None
@dataclass(frozen=True)
class TestReport: status: Literal["ok","rejected","unreachable"]; limited: bool; models: list[ModelReport]

class OpenAIKeyService:
    def __init__(self, repo, cipher: Cipher | None, hub: ProviderHub, probe: KeyProbe, settings: Settings) -> None
    def load(self) -> None                                   # startup: hub.set_key(resolved key)
    def state(self) -> KeyState
    async def store(self, raw_key: str, actor_id: str) -> KeyState
    def remove(self, actor_id: str) -> KeyState
    async def test(self) -> TestReport
```

- Resolution: `settings.openai_api_key.strip()` if non-empty → `environment`; else the stored row decrypted → `stored`; decrypt failure or `cipher is None` with a row → `stored_unreadable=True`, source `none`.
- `store`: strip; empty, whitespace inside or > 256 chars → `InvalidOpenAIKey`; environment key set → `KeyFromEnvironment`; `cipher is None` → `StorageUnavailable`; `probe.check(key)` → `rejected` → `OpenAIKeyRejected`, `unreachable` → `ProviderUnavailable`; encrypt; `repo.put`; `hub.set_key(key)`; log `openai_key_changed`. A failure at any step leaves the previous key effective (the hub is swapped last). An `asyncio.Lock` serialises store and remove.
- `remove`: environment → `KeyFromEnvironment`; `repo.delete`; `hub.set_key(None)`; log.
- `test`: effective key or, if none, `status="rejected"` is not claimed: raises `AiNotConfigured`. Otherwise `probe.check(key, models)` for the distinct configured models (tutor `openai_model`, authoring `authoring_model`, transcription `transcription_model`, voice `voice_model` when `voice_enabled`).
- `cipher` is `Cipher(secrets.encryption_key)` or `None`.

### 3.8 Backend routes and dependencies

- `app/api/session.py` (new, moved out of `auth.py`): `is_https(request, settings)`, `cookie_secure(request, settings)`, `set_session_cookie(response, request, token, settings)`, `clear_session_cookie(response, request, settings)`, `user_dto(user)`, `signed_in(user, token, request, settings, status)`.

  ```python
  def is_https(request, settings) -> bool:
      scheme = request.url.scheme
      if settings.trust_proxy:
          proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
          if proto in ("http", "https"): scheme = proto
      return scheme == "https"
  def cookie_secure(request, settings) -> bool:
      return is_https(request, settings) if settings.cookie_secure == "auto" else bool(settings.cookie_secure)
  ```
- `app/api/routes/setup.py` (new, prefix `/setup`): `POST /api/setup` (`SetupRequest`: `RegisterRequest` fields) → throttled with `register_limiter` exactly like registration → `auth.setup` in a thread pool → `signed_in(..., 201)`. Public.
- `auth.py`: `GET /auth/config` → `{registration, setup_required}`; `register`, `login`, `logout` use the `session` helpers.
- `admin.py`: `GET/PUT/DELETE /admin/openai-key`, `POST /admin/openai-key/test`, all `AdminDep`. Mutations and test are throttled with `login_limiter.allow(f"openai-key:{admin.id}")` (the password route's pattern). Responses never contain more than `KeyState`/`TestReport`.
- `deps.py`: `get_hub`, `get_key_service`, and

  ```python
  def require_ai(request: Request, _user: StudentDep) -> None:
      if not request.app.state.hub.configured: raise AiNotConfigured()
  AiReady = Depends(require_ai)
  ```

  `dependencies=[AiReady]` on: `POST /chat`, the discussion turn route, `POST /voice/session`, `POST /courses/{id}/chapters`, `PUT …/document`, `PUT …/source`, `POST …/retry`.
- `health.py`: adds `ai_configured`; `voice` becomes `settings.voice_enabled and hub.configured`.
- `main.py`: `load_secrets` first; engine and repositories; `Cipher | None`; `ProviderHub(settings)`; `OpenAIKeyService(...).load()`; `AuthService(..., secret=secrets.session_secret)`; `create_app(settings, engine, *, probe: KeyProbe | None = None)` (the probe is injectable for tests; default `OpenAIKeyProbe()`). Lifespan: logs `ai_not_configured` once; the hourly sweep also logs `setup_pending` while `auth.setup_required()`.
- `app/services/authoring/agent.py`: `PROVIDER_ERRORS` gains `AiNotConfigured`, so a key removed mid-run fails the run through the existing provider-failure path (retryable).

### 3.9 Migrations tooling

`app/db/backup.py` (new):

```python
def sqlite_path(url: str) -> Path | None                       # None for memory or non-SQLite
def backup_database(db: Path, revision: str, *, keep: int, now: datetime | None = None) -> Path
```

`sqlite3.connect(db).backup(dest_connection)` (online backup API, consistent with WAL) into `<db dir>/backups/celestin-<YYYYmmddTHHMMSSZ>-from-<revision>.db.tmp`, `chmod 0600`, `os.replace` to the final name; directory `0700`; then keep the `keep` newest `celestin-*.db` by name. Any `OSError`/`sqlite3.Error` propagates.

`scripts/migrate.py` (new): `settings = get_settings()`; `engine = make_engine(url)`; `current = current_revision(engine)`, `head = expected_head()`; when `current` and `current != head` and `sqlite_path(url)`: backup, log `migration_backup`; non-SQLite: log that no backup is made; then `command.upgrade(alembic_config(url), "head")`. Exit code 1 and a message on failure; the database is untouched when the backup fails. `alembic upgrade head` by hand is unchanged.

### 3.10 Image

- `docker/entrypoint.sh`:

  ```bash
  if [ "$(id -u)" = 0 ]; then
    mkdir -p /data
    [ "$(stat -c %u /data)" = 10001 ] || chown -R 10001:10001 /data 2>/dev/null || true
    setpriv --reuid=10001 --regid=10001 --clear-groups test -w /data || fail "/data is not writable …"
    exec setpriv --reuid=10001 --regid=10001 --clear-groups /usr/local/bin/entrypoint.sh "$@"
  fi
  [ -w /data ] || fail "…"                 # started with --user
  mkdir -p /data/caddy
  cd /app/backend && python -m scripts.migrate
  … uvicorn / node / caddy / wait -n as today
  ```

  The `OPENAI_API_KEY` and `SESSION_SECRET` checks are removed. `chown` only runs when the top directory's owner differs (a large volume is not walked at each start); a failing `chown` (some host mounts) is tolerated when the unprivileged user can write anyway.
- `Dockerfile`: no `USER` line; ENV adds `SECRETS_DIR=/data/secrets`, `COOKIE_SECURE=auto`; `libcap2-bin` and `setcap cap_net_bind_service=+ep /usr/local/bin/caddy` so `SITE_ADDRESS` with a host name can bind 80 and 443 unprivileged (no `--no-new-privs`). `HEALTHCHECK` unchanged.
- `docker-compose.yml`: no required variable, no `COOKIE_SECURE`.
- `docker/smoke.sh` (new): runs a given image on a temporary bind mount owned by a different uid, waits for health, checks `GET /api/auth/config` → `setup_required: true`, `POST /api/setup`, `GET /api/auth/me`, `GET /api/health` → `ai_configured: false`, restarts the container and checks the data survived. No OpenAI call.

### 3.11 Frontend

- `lib/auth.ts`: `AuthConfig = { registration: RegistrationMode; setupRequired: boolean }`; `authConfigQuery` returns it (`setup_required === true`); `SETUP_URL = "/api/setup"`; `setupAdmin(email, password, name): Promise<User>`.
- `routes/setup.tsx` (public, SSR like `/register`): reads `authConfigQuery`; while pending renders the shell with nothing in it; `setupRequired === false` → `<Navigate to="/login" replace />`; else `AuthShell` with the title and subtitle of the setup messages and `SetupForm`. On success: `setQueryData(meQuery.queryKey, user)`, invalidate `authConfigQuery.queryKey` and `["health"]`, navigate to `/admin`.
- `components/celestin/auth-forms.tsx`: the three account fields are extracted as `AccountFields` and used by `RegisterForm` and the new `SetupForm` (same `makeRegisterSchema`, same password rule, different submit label and `aria-label`).
- `routes/login.tsx` and `routes/register.tsx`: read `config.data?.registration`; when `config.data?.setupRequired` render `<Navigate to="/setup" replace />`. Existing mode logic unchanged.
- `settings/sections.ts`: `SettingsSection.roles?: Role[]`; `SettingsPage` renders `sections.filter(s => !s.roles || s.roles.includes(user.role))`; new `openaiSection` (`roles: ["admin"]`) appended to `SECTIONS`.
- `settings/openai-section.tsx` (new): `useQuery(openaiKeyQuery)`; shows the source and « ends with {last4} »; a password input (`type="password"`, `autoComplete="off"`, `name` absent, `spellCheck={false}`) cleared after a save; buttons « Save », « Test the key », « Remove » (confirm through the existing `ConfirmDialog`); read-only with an explanation when `source === "environment"`; a note and no form when `can_store` is false; a warning when `stored_unreadable`. The test result lists status, the `limited` note and each model with visible / not visible / unknown. Errors go through `apiMessage`.
- `lib/admin.ts`: `OpenAIKeyState`, `OpenAIKeyTest`, `OPENAI_KEY_KEY = ["admin", "openai-key"]`, `openaiKeyQuery`, `saveOpenAIKey(key)`, `removeOpenAIKey()`, `testOpenAIKey()`. Every mutation invalidates `OPENAI_KEY_KEY` and `["health"]`.
- `lib/tutor/health.ts`: `Health = { voice: boolean; aiConfigured: boolean }`; `aiConfigured` defaults to `true` when the field is missing (an older backend).
- `routes/_auth/admin/index.tsx`: `AiBanner` above the users panel when `useHealth().data?.aiConfigured === false`, with a link to `/settings`.
- Messages (both catalogs, `i18n:check`): `setup_head_title`, `setup_title`, `setup_subtitle`, `setup_submit`, `setup_form`; `settings_openai_*` (title, help with the link to platform.openai.com/api-keys, input label, source environment / stored / none, last4, save, saved, test, remove, removed, env note, cannot-store note, unreadable warning, test ok / rejected / unreachable / limited, model visible / not visible / unknown, models heading); `admin_ai_banner`, `admin_ai_banner_link`.

## 4. Data models

| Item | Shape |
|---|---|
| `app_settings` | `key` PK `String(64)`, `value` Text, `updated_at` timestamptz, `updated_by` `String(32)` null. Row `openai_api_key`: `{"v":1,"ct":"…","last4":"ab12"}` |
| `AuthConfigResponse` | `{registration, setup_required: bool}` |
| `SetupRequest` | `{email: EmailStr, password: 1..200, name: 1..80}`, `extra="forbid"` |
| `OpenAIKeyStateDTO` | `{source, last4: str\|null, stored_unreadable: bool, can_store: bool}` |
| `SaveOpenAIKeyRequest` | `{key: str}`, `extra="forbid"` (length checked by the service, so the refusal is the catalog's `invalid_openai_key`) |
| `OpenAIKeyTestDTO` | `{status, limited, models: [{role, model, visible: bool\|null}]}` |
| Health | adds `ai_configured: bool`; `voice` = enabled and configured |
| Files | `secrets/session_secret`, `secrets/encryption_key` (64 hex + newline, `0600`); `backups/celestin-<UTC>-from-<rev>.db` (`0600`, directory `0700`) |

## 5. Error handling

New `TutorError` subclasses in `app/domain/errors.py`, messages in both catalogs (`app/domain/messages/{fr,en}.py`) and rows in `tests/fixtures/error_messages_fr.json`:

| Code | Status | English message |
|---|---|---|
| `setup_done` | 409 | Setup is already done. Sign in. |
| `setup_required` | 409 | This instance has no administrator yet. Finish the setup first. |
| `ai_not_configured` | 503 | Célestin isn't set up yet. Ask whoever runs this instance to add the OpenAI key. |
| `invalid_openai_key` | 422 | That key doesn't look right. |
| `openai_key_rejected` | 422 | OpenAI rejected this key. Check that it is complete and active. |
| `key_from_environment` | 409 | The key is set by the server's environment (OPENAI_API_KEY); it can't be changed here. |
| `storage_unavailable` | 409 | This server can't store a key (no secrets directory). Set OPENAI_API_KEY instead. |

Existing codes reused: `weak_password`/`422` (setup), `rate_limited`, `provider_unavailable` (unreachable provider during a save), `forbidden`/`not_authenticated`.

Startup failures (`SecretFileError`, `MissingSessionSecret`, `SchemaOutdated`, an unwritable `/data`, a failed backup) stop the process with a one-line message naming the file or setting and the remedy; the entrypoint exits non-zero and the container stops. A removed key mid-run: the proxy raises `AiNotConfigured`; a tutor turn ends through the existing SSE error path; an authoring run fails through `PROVIDER_ERRORS` and is retryable. An undecryptable stored key is a state (`stored_unreadable`), not an exception: the hub has no key and the application runs in the needs-key state.

## 6. Testing strategy

Offline, with fakes; no test touches the network or a real key.

- **Fakes**: `FakeProbe(status, limited, models)` recording the keys it was given; a `ClientFactory` that records the keys and returns fake clients; `create_app(..., probe=FakeProbe)`.
- **Setup** (`tests/integration/test_setup.py`): pending → `config.setup_required`; `POST /api/setup` creates an enabled admin with a cookie; second call `409 setup_done`; two concurrent calls on a file database create one admin; weak password `422`; throttled; same-origin enforced; `register` `409 setup_required` in the three modes while pending; users without an admin → `409 setup_done`; `create_admin`/`seed` end the state. `AuthService.setup_required` caches `False`.
- **Secrets** (`tests/unit/test_secret_files.py`): generation and modes (`0600` file, `0700` directory), existing file reused, wrong size → `SecretFileError`, environment wins for the session secret, the encryption key always from the file, independence (delete one, the other keeps working), `SECRETS_DIR` unset → today's behaviour.
- **Cipher** (`test_cipher.py`): round trip, tamper, wrong key, wrong context → `CipherError`; nonces differ.
- **Hub** (`test_provider_hub.py`): unconfigured proxy → `AiNotConfigured`; `set_key` swaps all three; a call that resolved its client before the swap finishes on the old one, the next call uses the new one; `set_key(None)` returns to unconfigured.
- **Key service and routes** (`test_openai_key.py`): admin-only (student and parent `403`); state never contains the key; store → probe called, encrypted row (the plaintext is absent from the file database), hub configured, `last4`; rejected `422` and unchanged; unreachable `502` and unchanged; invalid input `422`; environment key → source `environment`, `PUT`/`DELETE` `409`; no cipher → `can_store` false, `409`; tampered ciphertext → `stored_unreadable`; remove; test action report including `limited`; throttling; no log record contains the key (caplog).
- **Needs-key** (`test_needs_key.py`): app with no key starts; the seven routes answer `503 ai_not_configured` with no row created; the read routes still work; health `ai_configured` false and `voice` false; saving a key makes the same routes reach the fake LLM without recreating the app; an authoring run whose key disappears fails retryably.
- **Cookie** (`test_cookie_secure.py`): `true`, `false`, `auto` over HTTP and over `X-Forwarded-Proto: https` with `trust_proxy` on, and the header ignored with it off; `delete_cookie` follows the same rule.
- **Migrate** (`test_migrate.py`): backup made and migrated (backup opens and holds the old revision), fresh database untouched, at head nothing, retention keeps `keep`, backup failure aborts before migrating, modes `0600`/`0700`; `test_migrations.py`: a populated `0008` upgrades to `0009` with every course, chapter and progress row intact, and downgrades.
- **Route guards**: `/api/setup` joins `PUBLIC`; a new test asserts the seven AI routes carry `require_ai`.
- **Catalog**: both catalogs have the new keys and the same `{fields}`; `error_messages_fr.json` rows added; the English-prompt accent test already ignores the name.
- **Existing suites**: the `anon_client` fixture and the registration tests that run on an empty database are updated — `anon_client` creates one bystander student directly, and a `fresh_client` fixture (no users) serves the setup tests. Call sites are listed in the tasks.
- **Frontend**: `setup.test.tsx` (form, success path to `/admin`, redirect to `/login` when not pending), `registration-modes.test.tsx` updated for the new config shape plus redirect to `/setup`, `settings-page.test.tsx` (the OpenAI section for an admin only; source variants; save, test, remove; the key is never rendered back; the field is cleared), `admin-page.test.tsx` (banner), English-sweep and `i18n:check` for the new keys, `health` default.
- **Image**: `docker/smoke.sh` on a bind mount owned by another uid, plus the manual R10.8 run with a real key.

## 7. Performance considerations

- Per-request cost is unchanged: the proxies add one attribute read; `require_ai` reads one boolean; `setup_required()` is a cached `False` after the first user. The database is read for the key only at startup and on admin actions.
- A key change builds three client objects and swaps one reference; no pause, no restart.
- `scripts.migrate` copies the database only when a migration is pending; SQLite's backup API copies page by page while readers continue.
- `chown -R` runs only when the volume's top-level owner is wrong.

## 8. Security considerations

- **The key**: encrypted with AES-256-GCM, a fresh nonce, associated data binding it to its purpose; `encryption_key` is a different file from `session_secret`; the plaintext exists only in process memory and in the request that carries it. Routes return `last4` at most. The probe never logs or re-raises provider text; `translate()` already maps SDK errors to catalog codes. `caplog` tests assert the key is absent from every record.
- **Secrets at rest**: `O_EXCL`, `0600`, directory `0700`, from `secrets.token_bytes`; never overwritten; failure to read stops startup rather than regenerating. A database copy has neither secret.
- **First visitor wins**: bounded to the empty `users` table; the insert is conditional in SQL, so no race can create a second admin; registration is closed while pending so no one can end the state as a student; an instance with users never exposes `/setup`.
- **Admin-only**: key routes use `AdminDep`; the route-guard test enforces the role list; the settings section's role filter is cosmetic.
- **Cookie**: `auto` believes `X-Forwarded-Proto` only when `TRUST_PROXY` is set; the image's Caddy overwrites it for untrusted clients and accepts it from private-range proxies. `HttpOnly` and `SameSite=Lax` unchanged. On plain HTTP the cookie travels in clear (documented).
- **Same-origin** applies to `/api/setup` and the key routes (`SameOriginMiddleware`); they are throttled.
- **Container**: root only for `chown`/`setpriv`; all three long-running processes run as uid 10001; the file capability on Caddy is limited to `cap_net_bind_service`. Backups are `0600` in a `0700` directory and excluded from the build context.
- **Dependency**: `cryptography` is a maintained, widely audited library with wheels for both architectures (no compiler in the build).

## 9. Monitoring and observability

JSON logs (`app/logging_config.py`), event names in `extra`:

| Event | Level | Fields | When |
|---|---|---|---|
| `setup_pending` | WARNING | `path: "/setup"` | startup, then hourly while no user exists |
| `setup_completed` | INFO | `user_id` | first admin created |
| `ai_not_configured` | WARNING | — | startup without an effective key |
| `openai_key_changed` | INFO | `user_id`, `action: set\|removed` | store / remove |
| `secrets_generated` | INFO | `files: [names]` | first boot (names only) |
| `migration_backup` | INFO | `path`, `from_revision`, `kept` | before a pending migration |
| `auth_rate_limited` | WARNING | `route: setup\|openai-key` | existing event, new routes |

`GET /api/health` reports `ai_configured` and `voice`; the container `HEALTHCHECK` stays on HTTP 200, which the needs-key and setup-pending states satisfy. No metric or log line carries the key, its length, an email or a password.

## 10. Documentation

New `documentation/first-run-setup.md` (setup state, secrets, hub and key service, needs-key behaviour, `COOKIE_SECURE=auto`, `scripts.migrate`, files on the volume), added to `documentation/index.md`. Updated: `docker.md` (rewritten around run → setup → key), `admin.md` (the setup route as the one deviation from « only the script »; the OpenAI section), `accounts-and-courses.md` (config answer, cookie rule), `running-locally.md` (fresh runs start setup-pending; the new variables), `CLAUDE.md` and `frontend/CLAUDE.md` (variables no longer required; new files), the spec 012 README (deviation note), `specs/index.md`.
