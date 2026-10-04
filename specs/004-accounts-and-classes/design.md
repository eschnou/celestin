# 004 — Design: accounts and classes

## 1. Overview

The backend gains a database and an identity. Users register and sign in; a server-side session rides in an httpOnly cookie (a bearer header carrying the same token is accepted for non-browser clients). A class catalog read from `courses/classes.yaml` replaces the single hardwired chapter: every chapter directory is loaded once, validated at startup, and served by id. Progress leaves the browser: a `progress` table keyed by (user, chapter) is read by the chat and voice controllers and written by the section tools through the turn context, in the same request that emits the section event.

The turn pipeline itself does not change shape. `TutorService.run_turn`, the registry, `services/path.py`, the SSE contract, the tool set, the reducer and the voice bridge are untouched. What changes is at the edges: who is asking (a dependency), which chapter (a catalog lookup), and where progress lives (a store handed to the tool context).

The frontend gains three public routes (`/`, `/login`, `/register`) and a pathless authenticated layout under which the class list, the class page and the lesson live. Authenticated routes render client-side only (`ssr: false`), so the guard runs where the cookie is, and the SSR shell needs no cookie forwarding.

Decisions that the requirements left open are in §10.

## 2. Architecture

```mermaid
flowchart LR
    subgraph Browser
        LOGIN[/login · /register]
        AUTH[_auth layout<br/>beforeLoad: me query → redirect]
        CLASSES[/classes<br/>enrolled · available]
        CLASS[/classes/$classId<br/>chapters + states]
        LESSON[/classes/$classId/chapters/$chapterId<br/>useTutorSession · useVoiceSession]
        AUTH --> CLASSES --> CLASS --> LESSON
    end

    subgraph Backend[FastAPI :8000]
        MW[SameOriginMiddleware<br/>BodySize · RequestId]
        DEPS[deps: CurrentUser · require_roles · RateLimits]
        AUTHR[routes/auth.py]
        CLSR[routes/classes.py]
        CHAT[routes/chat.py]
        VOICE[routes/voice.py]
        CAT[services/catalog.py<br/>ChapterCatalog: classes.yaml + chapter dirs]
        TS[TutorService]
        VS[VoiceService]
        TR[ToolRegistry + TurnContext.save]
        REPO[db/repositories.py<br/>Users · Sessions · Enrolments · Progress · VoiceUsage]
        DB[(SQLite · SQLAlchemy 2 · Alembic)]
        MW --> DEPS --> AUTHR & CLSR & CHAT & VOICE
        AUTHR --> REPO
        CLSR --> CAT & REPO
        CHAT --> CAT & TS --> TR --> REPO
        VOICE --> CAT & VS --> TR
        REPO --> DB
    end

    subgraph Files
        CLS[courses/classes.yaml]
        CH1[courses/chapitre_1/pack.md + curriculum.yaml]
        PROMPT[backend/prompts/tutor.fr.md]
    end

    LOGIN & AUTH -->|/api/auth/*| AUTHR
    CLASSES & CLASS -->|/api/classes/*| CLSR
    LESSON -->|/api/chat · /api/voice/*| CHAT & VOICE
    CAT --> CLS & CH1 & PROMPT
```

Runtime topology: unchanged for development (Vite proxies `/api`, cookies pass through the proxy). One new file on disk: the SQLite database at `DATABASE_URL` (default `sqlite:///./data/celestin.db` under `backend/`, gitignored).

### 2.1 Sequence: opening a chapter

```mermaid
sequenceDiagram
    participant B as Browser (lesson route)
    participant A as deps.CurrentUser
    participant C as routes/classes
    participant R as Repositories
    B->>C: GET /api/classes/maths-5e/chapters/suites (cookie)
    C->>A: session → user (student)
    C->>R: enrolment(user, maths-5e)? chapter ∈ class?
    C->>R: progress.load(user, suites) → {done, active}
    C-->>B: {chapter overview, progress}
    B->>B: useTutorSession(chapter, progress) → opening turn
    B->>C: POST /api/chat {class_id, chapter_id, history}
    Note over C: progress loaded again server-side; ctx.save bound to the store
```

## 3. Components and Interfaces

### 3.1 HTTP API

All routes under `/api`. Every route except those marked *public* requires a session and declares admitted roles; in this epic that is `student` everywhere except `logout` and `me` (any role). Errors are `{code, message}` with a French message, as today.

| Route | Auth | Request | Response |
|---|---|---|---|
| `GET /health` | public | — | `{status, model, voice, voice_model, classes: int, chapters: int, prompt_loaded: bool}` |
| `POST /auth/register` | public, rate-limited | `{email, password, name}` | `201 {user}` + session cookie |
| `POST /auth/login` | public, rate-limited | `{email, password}` | `200 {user}` + session cookie |
| `POST /auth/logout` | any role | — | `204`, cookie cleared, session row deleted |
| `GET /auth/me` | any role | — | `{user}` |
| `GET /classes` | student | — | `{enrolled: [ClassSummary], available: [ClassCard]}` |
| `POST /classes/{class_id}/enrol` | student | — | `204` (idempotent) |
| `GET /classes/{class_id}` | student, enrolled | — | `ClassDetail` |
| `GET /classes/{class_id}/chapters/{chapter_id}` | student, enrolled | — | `ChapterView` (overview + progress) |
| `DELETE /classes/{class_id}/chapters/{chapter_id}/progress` | student, enrolled | — | `204` |
| `POST /chat` | student, enrolled | `{class_id, chapter_id, history}` | SSE, unchanged event set |
| `POST /voice/session` | student, enrolled, rate-limited per user | `{class_id, chapter_id, history}` | as 003 |
| `POST /voice/tool` | student, enrolled | `{session_id, call_id, name, arguments, class_id, chapter_id}` | as 003, `progress` still echoed |
| `POST /voice/usage` | student | as 003 | `204` |

`GET /api/chapters/current` is removed. "Enrolled" means: the user has an enrolment in `class_id` and the catalog lists `chapter_id` in that class; otherwise `404 not_found` (never 403, so class membership is not probeable).

Cookie: name `celestin_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` when `settings.cookie_secure` (default `True`; `.env` sets `COOKIE_SECURE=false` for `http://localhost`). `Max-Age` = `session_idle_days`. The same token in `Authorization: Bearer <token>` is accepted by the dependency, for clients that cannot hold a cookie.

### 3.2 Authentication (`app/services/auth_service.py`, `app/api/deps.py`)

```python
class AuthService:
    def __init__(self, users: UserRepository, sessions: SessionRepository, hasher: PasswordHasher, settings: Settings): ...
    def register(self, email: str, password: str, name: str) -> tuple[User, str]:   # (user, raw token)
    def login(self, email: str, password: str) -> tuple[User, str]:                # raises InvalidCredentials
    def logout(self, token: str) -> None
    def authenticate(self, token: str) -> User | None                               # touches last_seen_at at most hourly
```

- Email normalised `strip().lower()`; validated with `pydantic.EmailStr`.
- Password policy in `domain/password.py`: `check_password(password, email, name) -> str | None` (French message): length ≥ 10; must not contain the local part of the email or the name (case-insensitive, length ≥ 3).
- Hashing: `pwdlib.PasswordHash` with `Argon2Hasher(memory_cost=settings.argon2_memory_kib, time_cost=settings.argon2_time, parallelism=settings.argon2_parallelism)`. `login` calls `verify_and_update`; a returned new hash is stored (parameter migration). Unknown email → verify against a constant dummy hash so timing does not differ.
- Token: `secrets.token_urlsafe(32)`; the table stores `sha256(token)` only. Cookie and bearer carry the raw token.
- Renewal: `authenticate` updates `last_seen_at` when older than one hour; expiry rule: `now > last_seen_at + idle_days` or `now > created_at + absolute_days` → row deleted, `None` returned.

Dependencies:

```python
def current_user(request, repo) -> User:                  # cookie or bearer; 401 NotAuthenticated
def require_roles(*roles: Role) -> Callable[..., User]:   # 403 Forbidden when user.role not in roles
StudentDep = Annotated[User, Depends(require_roles("student"))]
AnyUserDep = Annotated[User, Depends(require_roles("student", "parent", "admin"))]
def enrolled_chapter(class_id, chapter_id, user, catalog, enrolments) -> ChapterRef   # 404 unless enrolled and listed
```

`VoiceAccess` from 003 is replaced by `StudentDep`; the voice limiter key becomes `user.id`. R2.4 ("no route without roles") is a test in `tests/unit/test_route_guards.py`: for every route of the app not in `PUBLIC = {"/api/health", "/api/auth/register", "/api/auth/login", "/api/docs", "/api/openapi.json"}`, the dependant tree must contain a `require_roles` marker (the closure carries `__celestin_roles__`).

### 3.3 Same-origin middleware (`app/api/middleware.py`)

For any non-`GET`/`HEAD`/`OPTIONS` request without an `Authorization` header: allow if `Sec-Fetch-Site` ∈ {`same-origin`, `none`} or, when absent, if `Origin` (or `Referer` host) equals the request host. Otherwise `403 cross_origin`. Bearer requests skip the check: a header cannot be forged cross-site. `CORSMiddleware` stays optional and, when enabled, `allow_credentials=True` with an explicit origin list.

### 3.4 Rate limits

`SlidingWindow` from 003, three instances on `app.state`: `login_limiter` keyed by IP and by email (two `allow` calls, both must pass), `register_limiter` keyed by IP, `voice_limiter` keyed by user id. Settings: `auth_attempts_per_window` (10), `auth_window_s` (900), `voice_sessions_per_hour` (6). Refusal: `429 rate_limited` with the existing French message style.

### 3.5 Class catalog (`app/services/catalog.py`, `app/domain/catalog.py`)

`courses/classes.yaml`:

```yaml
classes:
  - id: maths-5e
    title: Mathématiques 5e
    subject: Mathématiques
    level: 5e secondaire
    description: Le cours de l'année, chapitre par chapitre, tel que le professeur le donne.
    open: true
    chapters: [chapitre_1]        # directory names under courses/
```

Domain (`domain/catalog.py`, pydantic, `extra="forbid"`): `ClassDef{id: Slug, title, subject, level, description, open: bool, chapters: list[str] (min 1, unique)}`, `Catalog{classes: list[ClassDef]}` with unique class ids. `parse_catalog(text, path)` raises `CatalogInvalid(path, detail)`.

`ChapterSource` replaces the chapter part of `CourseService`: two `_MtimeCachedFile`s (pack, curriculum) and the parsed-once-per-mtime curriculum, exactly the current code minus the prompt. `PromptSource` is the prompt file alone. `ChapterCatalog`:

```python
class ChapterCatalog:
    def __init__(self, courses_dir: Path, prompt_path: Path): ...   # reads classes.yaml, builds one ChapterSource per referenced directory, validates all at construction
    prompt: PromptSource
    def classes(self) -> list[ClassDef]
    def get_class(self, class_id) -> ClassDef | None
    def chapter(self, chapter_id) -> ChapterSource          # KeyError → CurriculumUnavailable at the route
    def chapters_of(self, class_id) -> list[ChapterSource]  # catalog order
    def contains(self, class_id, chapter_id) -> bool
```

Construction fails with `CatalogInvalid` naming the file on: unknown directory, duplicate chapter id across directories (both paths named), a curriculum error (already `CurriculumInvalid`). The catalog file is read once at startup (R4.4.3); chapter files keep the mtime cache.

`TutorService` and `VoiceService` take the catalog and a chapter id: `build_input(chapter_id, entries, ctx)` and `session_config(chapter_id)`, `seed(chapter_id, entries, ctx)`, `execute_tool(chapter_id, name, arguments, ctx)`. Their internals substitute `self._courses.get_pack()` with `self._catalog.chapter(chapter_id).pack()` and so on. The prompt is shared.

### 3.6 Progress through the tool context (`tools/context.py`, `tools/section.py`)

```python
@dataclass
class TurnContext:
    curriculum: Curriculum
    progress: Progress
    save: Callable[[Progress], None] | None = None   # bound by the controller to the store

    def commit(self, progress: Progress) -> None:
        """Persist, then adopt. A failing store leaves ctx.progress untouched and
        raises ToolValidationError, so the loop emits no event (NFR 4.4.2)."""
```

`start_section` and `complete_section` call `ctx.commit(new_progress)` instead of assigning `ctx.progress`. With `save=None` (unit tests, scripts) `commit` just assigns. The controllers bind `save=lambda p: progress_repo.save(user.id, chapter_id, p)`. The failure message: « Je n'ai pas pu enregistrer ta progression. Réessaie. » A review (`start_section` on a done section) commits nothing, as today.

`TurnContext.from_progress` (003) keeps its signature; the controllers build the context from the loaded row: `TurnContext.from_progress(curriculum, row.done, row.active, save=...)`.

### 3.7 Repositories (`app/db/`)

```
app/db/base.py          engine + session factory from DATABASE_URL; SQLite pragmas (foreign_keys=ON, journal_mode=WAL)
app/db/models.py        SQLAlchemy 2 declarative models (§4.1)
app/db/repositories.py  UserRepository, SessionRepository, EnrolmentRepository, ProgressRepository, VoiceUsageRepository
app/db/migrations/      Alembic environment and versions
```

Repositories are synchronous, take a `Session` (one per request via a dependency that commits on success and rolls back on exception). Routes call them through `starlette.concurrency.run_in_threadpool` for the reads on the request path; the section tools' `commit` runs the one small write inline (SQLite, sub-millisecond). This is the documented seam to revisit for PostgreSQL (§10.6).

`ProgressRepository`:

```python
def load(self, user_id, chapter_id) -> ProgressRow | None
def save(self, user_id, chapter_id, progress: Progress) -> None      # upsert, updated_at=now
def clear(self, user_id, chapter_id) -> None
def for_class(self, user_id, chapter_ids) -> dict[str, ProgressRow]  # one query
```

`SessionRepository.purge_expired()` runs at startup and once per hour from a background task started in the lifespan.

### 3.8 Migrations and startup

Alembic in `backend/alembic.ini` + `app/db/migrations`; `uv run alembic upgrade head` creates the file and the schema. `create_app` opens the engine and compares `MigrationContext.get_current_revision()` to `ScriptDirectory.get_current_head()`; on mismatch it raises `SchemaOutdated("… run: uv run alembic upgrade head")`. Tests build the schema with `Base.metadata.create_all` on an in-memory engine and one test asserts the Alembic head matches the metadata (`alembic.autogenerate.compare_metadata` returns no diff).

Lifespan (replacing the plain factory body): open engine, check schema, build catalog, start the purge task; on shutdown dispose the engine. `create_app` keeps its factory signature.

### 3.9 Controllers

`routes/auth.py`: the four routes; `register` and `login` set the cookie through a helper `set_session_cookie(response, token, settings)`; `logout` deletes the row and sets `Max-Age=0`.

`routes/classes.py`: builds `ClassSummary` (enrolled classes with `chapters_done/total` and `last_chapter` = the chapter with the newest `updated_at` among the class's chapters, or null), `ClassCard` (open, not enrolled), `ClassDetail` (chapters with `state ∈ {not_started, in_progress, done}`, `done_count`, `section_count`, `last: bool`), `ChapterView` (the current `ChapterResponse` plus `progress`). `enrol` inserts if absent; a closed or unknown class → `404`.

`routes/chat.py`: `enrolled_chapter` dependency, load progress, build `TurnContext` with `save`, `build_input(chapter_id, …)`; the SSE part is unchanged. `routes/voice.py`: same for `/session` (seed from stored progress) and `/tool` (context with `save`; the echoed `progress` field stays for the browser's benefit).

`routes/health.py`: `classes`, `chapters`, `prompt_loaded`; `sections` and `pack_loaded` go.

### 3.10 Frontend: routes and guard

```
src/routes/__root.tsx                        shell (unchanged), context {queryClient}
src/routes/index.tsx                         beforeLoad: redirect to /classes
src/routes/login.tsx                         public, ssr: true
src/routes/register.tsx                      public, ssr: true
src/routes/_auth.tsx                         ssr: false; beforeLoad: requireUser(queryClient, location) → context {user}; renders AppBar + <Outlet/>; non-student → NotYetPage
src/routes/_auth/classes/index.tsx           « Mes classes »
src/routes/_auth/classes/$classId/index.tsx  class page
src/routes/_auth/classes/$classId/chapters/$chapterId.tsx   the lesson (today's index.tsx body)
```

`lib/auth.ts`: `meQuery` (`queryKey: ["me"]`, `staleTime: Infinity`, `retry: false`), `fetchMe` (401 → `null`), `login`, `register`, `logout` (each posts JSON with `credentials: "same-origin"`, the default), and

```ts
export async function requireUser(queryClient, location): Promise<User> {
  const user = await queryClient.ensureQueryData(meQuery);
  if (!user) throw redirect({ to: "/login", search: { redirect: location.href } });
  return user;
}
```

After login/register: `queryClient.setQueryData(["me"], user)` then `router.navigate({ to: search.redirect ?? "/classes" })`. Logout: `queryClient.clear()` then navigate to `/login`. `useIsDesktop`, the lesson components and the chapter map are unchanged.

Handling a lost session mid-lesson (R4.4.4): `readError` in `lib/tutor/client.ts` returns `code: "not_authenticated"`; the tutor column renders that error entry with a « Se connecter » link (`Link to="/login" search={{redirect: location.href}}`).

### 3.11 Frontend: lesson data and progress

- `lib/tutor/chapter.ts`: `chapterQuery(classId, chapterId)` → `ChapterView` (overview + progress). `lib/tutor/classes.ts`: `classesQuery`, `classQuery(classId)`, `enrol(classId)`, `resetChapter(classId, chapterId)`.
- `client.ts`: `streamTurn({classId, chapterId, history}, signal)`; no `progress` in the body. `voice/client.ts`: `createVoiceSession({classId, chapterId, history})`, `executeTool(sessionId, call, {classId, chapterId})`.
- `useTutorSession(chapter, { classId, chapterId, initialProgress })`: initial state from `initialProgress`; the `saveProgress` effect and `progress-store.ts` are deleted; `resetProgress` calls `resetChapter` then restarts. On first load of the new build, `localStorage` keys starting with `celestin.progress.` are removed once (a three-line effect in `_auth.tsx`).
- `use-voice-session.ts`: `snapshot()` no longer needs progress for the seed; the tool queue passes `{classId, chapterId}` instead of `progress`. The hook otherwise unchanged.
- `path.ts`, the reducer, `chapter-strip`, `chapter-map`, `whiteboard`, `tutor-column` unchanged, except a slim top bar in the lesson route: « ← Mes classes », class title · chapter title, user name, « Se déconnecter ».

### 3.12 Frontend: pages

- `login.tsx` / `register.tsx`: one form each, `react-hook-form` + `zod` (both already dependencies), French labels and errors, the password rule under the field, a link to the other page. Errors from the API shown under the form.
- `classes/index.tsx`: two sections per R4; each enrolled class card shows `chapters_done/total` and « Reprendre : {last_chapter.title} » linking to the lesson, or « Commencer » linking to the class page. Available cards have « Rejoindre ».
- `classes/$classId/index.tsx`: chapter rows with state badge and count, « Reprendre » / « Commencer » / « Revoir » per state; the last-worked row marked « en cours ».
- `_auth.tsx`: `AppBar` (« Célestin », user name, « Se déconnecter ») on the class pages only; the lesson keeps its own top bar to save height.

### 3.13 Configuration (`config.py`)

| Key | Default | Purpose |
|---|---|---|
| `database_url` | `sqlite:///./data/celestin.db` | SQLAlchemy URL; relative to `backend/` |
| `session_secret` | — | required at startup (used to HMAC the token hash: `sha256(secret + token)`, so a leaked DB alone cannot mint sessions) |
| `session_idle_days` / `session_absolute_days` | 30 / 90 | R1.6 |
| `cookie_secure` | `true` | `false` for `http://localhost` |
| `argon2_memory_kib` / `argon2_time` / `argon2_parallelism` | 19456 / 2 / 1 | OWASP minimum |
| `auth_attempts_per_window` / `auth_window_s` | 10 / 900 | R1.8 |
| `courses_dir` | `<repo>/courses` | replaces `course_pack_path` and `curriculum_path` |
| `trust_proxy` | `false` | kept from 003 |

`.env.example` gains `SESSION_SECRET=` and `COOKIE_SECURE=false`. `VOICE_*` unchanged.

## 4. Data Models

### 4.1 Tables (`app/db/models.py`)

| Table | Columns | Notes |
|---|---|---|
| `users` | `id` String(32) PK (uuid4 hex), `email` String(254) unique not null, `name` String(80) not null, `password_hash` String(255), `role` String(16) not null (`student`/`parent`/`admin`, checked in code and by a CHECK constraint), `created_at` DateTime(tz) | |
| `sessions` | `id` String(32) PK, `user_id` FK users ON DELETE CASCADE, `token_hash` String(64) unique, `created_at`, `last_seen_at`, index on `user_id` | expiry computed from the two timestamps |
| `enrolments` | `user_id` FK, `class_id` String(40), `created_at`; PK (`user_id`, `class_id`) | `class_id` references the catalog, not a table |
| `progress` | `user_id` FK, `chapter_id` String(40), `done` JSON (list of section ids), `active` String(40) nullable, `updated_at`; PK (`user_id`, `chapter_id`) | mirrors `Progress` |
| `voice_usage` | `id` Integer PK autoincrement, `user_id` FK, `session_id` String(12), `reason` String(8), `duration_s` Integer, `responses` Integer, six token columns Integer, `cost_estimate_usd` Float, `created_at` | what 003 only logged |

Types chosen for SQLite/PostgreSQL portability: `String`, `Integer`, `Float`, `JSON`, `DateTime(timezone=True)`; ids as hex strings, no dialect-specific types.

### 4.2 Domain (`app/domain/`)

- `user.py`: `Role = Literal["student", "parent", "admin"]`; `User(id, email, name, role)` frozen dataclass (no hash).
- `catalog.py`: `ClassDef`, `Catalog` (§3.5).
- `password.py`: `check_password`.
- `progress.py`: unchanged `Progress`.
- `errors.py`: `NotAuthenticated` (401 `not_authenticated`, « Connecte-toi pour continuer. »), `Forbidden` (403 `forbidden`, « Cet espace n'est pas encore disponible pour ton rôle. »), `InvalidCredentials` (401 `invalid_credentials`, « Email ou mot de passe incorrect. »), `EmailTaken` (409 `email_taken`, « Cette adresse ne peut pas être utilisée. »), `WeakPassword` (422 `weak_password`, the rule's message), `NotFound` (404 `not_found`, « Cette page n'existe pas. »), `RateLimited` (429, replacing `VoiceRateLimited`), `CrossOrigin` (403 `cross_origin`), `CatalogInvalid`, `SchemaOutdated` (startup only).

### 4.3 Wire DTOs (`app/api/schemas/`)

```python
# auth.py
class RegisterRequest(_Model): email: EmailStr; password: Annotated[str, Field(min_length=10, max_length=200)]; name: Annotated[str, Field(min_length=1, max_length=80)]
class LoginRequest(_Model):    email: EmailStr; password: Annotated[str, Field(max_length=200)]
class UserDTO(_Model):         id: str; email: str; name: str; role: Role
class UserResponse(_Model):    user: UserDTO

# classes.py
class ChapterStateDTO(_Model): id, title, section_count: int, done_count: int, state: Literal["not_started","in_progress","done"], last: bool
class ClassCard(_Model):       id, title, subject, level, description
class ClassSummary(ClassCard): chapters_done: int, chapters_total: int, last_chapter: ChapterRefDTO | None
class ChapterRefDTO(_Model):   id, title
class ClassesResponse(_Model): enrolled: list[ClassSummary]; available: list[ClassCard]
class ClassDetail(ClassCard):  chapters: list[ChapterStateDTO]
class ChapterView(ChapterResponse): progress: ProgressDTO      # ChapterResponse from 002 unchanged

# chat.py
class ChatRequest(_Model): class_id: Slug; chapter_id: Slug; history: list[Entry]     # progress removed
# voice.py
class VoiceSessionRequest(ChatRequest): ...
class VoiceToolRequest(_Model): session_id, call_id, name, arguments, class_id: Slug, chapter_id: Slug   # progress removed
```

`ProgressDTO` survives as a response type only.

### 4.4 Frontend types (`lib/tutor/types.ts`, `lib/auth.ts`)

`User`, `ClassCard`, `ClassSummary`, `ClassDetail`, `ChapterState`, `ChapterView` mirror §4.3. `HistoryEntry`, `TranscriptEntry`, `TutorEvent`, `Progress` unchanged.

## 5. Error Handling

| Where | Failure | Behaviour |
|---|---|---|
| Startup | `SESSION_SECRET` missing | abort with the variable named (like the API key) |
| Startup | schema behind Alembic head | `SchemaOutdated` naming `uv run alembic upgrade head` |
| Startup | `classes.yaml` missing/invalid, unknown chapter dir, duplicate chapter id, broken curriculum | `CatalogInvalid` / `CurriculumInvalid` naming the file (and both paths for a duplicate) |
| Any route | no or expired session | `401 not_authenticated`; the frontend guard redirects to `/login?redirect=…`; mid-lesson, the error entry carries a « Se connecter » link |
| Any route | wrong role | `403 forbidden`; the frontend shows the not-yet page |
| Mutating route | cross-origin browser request | `403 cross_origin` (never reached by the app) |
| `register` | email taken, weak password | `409 email_taken`, `422 weak_password`, French, shown under the field |
| `login` | unknown email or wrong password | `401 invalid_credentials`, same message and timing for both |
| `login`/`register` | over the limit | `429 rate_limited` |
| `enrol` / class / chapter routes | unknown or closed class, not enrolled, chapter not in class | `404 not_found` |
| `chat` / `voice` | progress row missing | not an error: the empty record; the row is created on the first commit |
| section tool | store write fails | `ToolValidationError` (French), `ctx.progress` unchanged, no event; logged at `error` with the exception |
| `reset` | store write fails | `500 internal`, transcript untouched |
| DB | connection lost | `500` from the session dependency's rollback; logged; nothing partially committed |

Client-visible messages stay French and generic; emails, hashes, tokens and stack traces stay in the logs.

## 6. Testing Strategy

Backend (`pytest`, offline):

- `tests/conftest.py`: an in-memory SQLite engine per test (`sqlite://`, `StaticPool`, `create_all`), overriding the session dependency; `make_client` gains `user=` to pre-seed and sign in (returns the cookie); `FakeLLM`/`FakeRealtime` as before.
- `tests/unit/test_catalog.py`: `classes.yaml` parsing; fixtures under `tests/fixtures/catalog/` for unknown dir, duplicate chapter id (two dirs, same `id`), closed class; real `courses/` loads with one class and one chapter.
- `tests/unit/test_password.py`: policy cases; `test_auth_service.py`: register/login/logout/expiry/renewal with a fake clock; parameter re-hash; dummy verify on unknown email (hasher spy called once either way).
- `tests/unit/test_repositories.py`: each repository's round trip; `for_class` returns one dict; `purge_expired`.
- `tests/unit/test_route_guards.py`: every non-public route carries `require_roles`; `student`-only routes return 403 for a `parent` user.
- `tests/unit/test_section_tools.py`: `commit` persists through `save`; a raising `save` leaves progress untouched and raises `ToolValidationError`.
- `tests/unit/test_migrations.py`: Alembic head equals the models' metadata.
- `tests/integration/test_auth_endpoint.py`: register → cookie → `me` → logout → 401; login with bearer; bad password 401; email taken 409; weak password 422; 429 after the budget; cross-origin POST 403 (`Origin: https://evil.example`), same-origin passes, bearer skips the check; `Secure` present/absent per setting.
- `tests/integration/test_classes_endpoint.py`: list before/after enrol; idempotent enrol; closed class 404; class detail states and `last`; chapter view with progress; reset; **isolation**: user B's cookie cannot read or reset user A's progress and sees her own empty record.
- `tests/integration/test_chat_endpoint.py`: golden transcripts updated to `{class_id, chapter_id, history}`; a `start_section` round persists `active` (read back through the repository); a refused start persists nothing; a failing store yields `{"ok": false}` to the model and no event; the state message is built from the stored progress, not the request.
- `tests/integration/test_voice_endpoint.py`: session seed from stored progress; tool persists; usage row written with the user id; limiter keyed by user (two users, one budget each).
- `scripts/smoke.py` and `scripts/voice_smoke.py` take `--chapter <id>` (default the first catalog chapter) and a `--user` created on the fly in a temporary database.

Frontend (`vitest`):

- `lib/__tests__/auth.test.ts`: `fetchMe` 401 → null; `requireUser` throws a redirect carrying `location.href`; login/register/logout request shapes.
- `lib/tutor/__tests__/client.test.ts`: body is `{class_id, chapter_id, history}`; `not_authenticated` code surfaces.
- `components/celestin/__tests__/use-tutor-session.test.ts`: initial progress from props; reset calls the API then restarts; no `localStorage` access (spy asserts zero calls).
- `routes/__tests__/login.test.tsx`, `register.test.tsx`: field errors, API error under the form, redirect target after success.
- `routes/__tests__/classes.test.tsx`, `class.test.tsx`: cards, states, « Reprendre » target, enrol call.
- `voice` tests: tool queue passes `{classId, chapterId}`.

Manual: register on the laptop, complete a section, sign in on the tablet, see the same section active; sign out; a `parent` row edited by hand sees the not-yet page.

## 7. Performance Considerations

- Per turn: one `SELECT` (progress, plus the enrolment check as one more `SELECT` or a join), one `UPSERT` only when a section tool ran. Both on SQLite, local.
- `authenticate` writes `last_seen_at` at most once per hour per session; the other requests are one indexed read on `token_hash`.
- Argon2id at the OWASP minimum takes ~50–100 ms per hash on a laptop; only `register`, `login` and the dummy verify pay it, and they run in the threadpool so the event loop is not blocked.
- The prompt prefix is per chapter and carries nothing user-specific (NFR 4.2.2); the state message may carry the first name. `scripts/smoke.py --chapter` proves the cache hit per chapter.
- The catalog is in memory; class pages are dictionary lookups plus one `for_class` query.
- Authenticated routes are `ssr: false`, so a first paint is the shell plus a client fetch of `me`; the public pages keep SSR.

## 8. Security Considerations

- Passwords: Argon2id, parameters in settings, `verify_and_update` re-hash on login, dummy verify on unknown email, no password in logs (the request logger never logs bodies).
- Sessions: 256-bit random token, stored as `HMAC-SHA256(session_secret, token)`; a database leak yields no usable session; sign-out deletes the row; idle and absolute expiry; hourly purge.
- Cookie: `HttpOnly`, `SameSite=Lax`, `Secure` (configurable off for localhost), `Path=/`. Bearer accepted as an alternative; bearer requests skip the same-origin check because they cannot be forged cross-site.
- CSRF: the same-origin middleware on every mutating `/api` route (§3.3) plus `SameSite=Lax`; test with a foreign `Origin`.
- Authorisation: every progress, enrolment and voice query is scoped by `user.id` from the session; ids never come from the client. Class membership is checked by the `enrolled_chapter` dependency, refusing with 404.
- Enumeration: registration and login answer the same for known and unknown emails in message and timing; the rate limit keys on email as well as IP so a distributed guess is still bounded per address.
- Roles: `require_roles` is mandatory by test (R2.4); registration cannot set a role.
- Secrets: `OPENAI_API_KEY`, `SESSION_SECRET` from `.env`; startup refuses without either.
- Logs: `user_id` and `session_id`; never email, token or password.

## 9. Monitoring and Observability

| Event | Fields |
|---|---|
| `auth_register` | `user_id` |
| `auth_login_ok` / `auth_login_failed` | `user_id` (ok only), `client_key` |
| `auth_logout` | `user_id` |
| `auth_rate_limited` | `route`, `client_key` |
| `enrolled` | `user_id`, `class_id` |
| `progress_saved` | `user_id`, `chapter_id`, `active`, `done_count` (emitted by `commit`) |
| `progress_reset` | `user_id`, `chapter_id` |
| `progress_save_failed` | `user_id`, `chapter_id`, exception |
| `turn_complete`, `voice_*` | gain `user_id` and `chapter_id` |
| `sessions_purged` | `count` |
| `schema_outdated` / `catalog_invalid` | startup, with the path |

`/api/health` reports `classes` and `chapters`. Voice usage is now a table as well as a log line, so cost per student per week is a query.

## 10. Decisions

1. **Server-side session table, opaque token, httpOnly cookie** (open question 1). Revocation on sign-out and idle renewal fall out of the table; a JWT would need a denylist for the same. The token is also accepted as a bearer (open question 2), so a native client later needs no new mechanism.
2. **SQLite with SQLAlchemy 2 and Alembic** (open question 4). One learner's household is a single process on one box; the schema uses portable types and no dialect features, so `DATABASE_URL=postgresql+psycopg://…` is the move when the deployment changes. The Cloudflare target of the frontend build does not constrain the backend.
3. **Progress keyed by (user, chapter)** (open question 3). The catalog may list a chapter in two classes, and they share the record; a repeat year is a reset, not a second record. Adding `class_id` to the key later is a migration of one column.
4. **Synchronous repositories, threadpool for reads, inline write in the section tools.** Making the tool handlers async touches the registry, the turn loop and every test; the write is a single upsert on a local file. Revisit with PostgreSQL.
5. **`ssr: false` on the authenticated layout.** The guard then runs where the cookie is, no server-side cookie forwarding, no server functions. Public pages keep SSR.
6. **Same-origin check by `Sec-Fetch-Site`/`Origin` rather than a CSRF token.** No token plumbing in the frontend; every modern browser sends `Sec-Fetch-Site`; the fallback covers the rest.
7. **Catalog file read once at startup, chapter files by mtime.** Adding a class is a restart; editing a pack is not, as today.
8. **`last_chapter` derived from `progress.updated_at`**, no extra write on chapter open. A chapter opened without a section change is not "last"; acceptable, since the opening turn normally starts a section.
9. **`/api/chapters/current` removed** rather than kept as an alias; the lesson has a class and chapter in its URL now.
10. **`VoiceAccess` retired** in favour of `StudentDep`; the voice limiter keys by user, as R6.7 asks.
