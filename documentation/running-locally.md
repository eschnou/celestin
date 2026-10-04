# Running locally

To run the whole thing in one container instead, see [docker.md](./docker.md).

Two processes. The frontend proxies `/api` to the backend, so the browser only ever sees one origin
and CORS never enters the picture in development.

```sh
# terminal 1 — backend on :8000
cd backend
uv sync
uv run python -m scripts.migrate                                # once, and after new migrations (backs the SQLite file up first)
uv run uvicorn app.main:create_app --factory --reload --port 8000

# terminal 2 — frontend on :8080
cd frontend
npm install
npm run dev
```

To get a working lesson without pasting anything, seed a local test student with chapter 1:

```sh
cd backend
uv run python -m scripts.seed --email eleve@example.be --password 'mot-de-passe-solide' [--name Léa] [--language en]
```

It creates or updates the account, a « Mathématiques 5e » course and a ready chapter from
`courses/chapitre_1/` (no model call), prints the lesson URL, and can be run again: the chapter's
content is refreshed and its progress reset. It refuses a non-SQLite `DATABASE_URL` without
`--force`. With `--language en` it seeds an English « Mathematics Year 5 » course from the English
sequences fixture (`backend/tests/fixtures/chapters/sequences_en/`). Otherwise, register in the app, create a course and add a chapter from a PDF or photos.

A fresh run — an empty database — is **waiting for its first administrator** (spec 013): the first visit to
`/login` leads to `/setup`, where you create the administrator; registration is refused until then.
`scripts.seed` and `scripts.create_admin` create accounts directly and end that state. To start the way the
Docker image does, with no key in the environment: set `SECRETS_DIR=./data/secrets` and leave
`OPENAI_API_KEY` empty, and choose the provider and paste its key in the settings screen (« Fournisseur d'IA »).

`create_app` is a factory, so `--factory` is required. There is no module-level `app` on purpose:
importing one would run startup validation at import time and break the test suite.

To get an administrator (the dashboard at `/admin`; there is no other way to become one):

```sh
uv run python -m scripts.create_admin --email admin@example.be --password 'mot-de-passe-solide' [--name Admin]
```

## Configuration

Copy `.env.example` to `.env`, in `backend/` or at the repository root. Either is read; `backend/.env`
wins if both exist, and both are gitignored.

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | — | Optional (specs 013, 014). The key of the default connection when set, read-only in the settings; without it the app starts, and an administrator pastes a key in the settings screen (needs `SECRETS_DIR`) while the AI routes answer `503 ai_not_configured`. A server that is not OpenAI's may need none. The scripts below still read it from here. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | The default connection's address: any OpenAI-compatible server (`https://api.groq.com/openai/v1`, `http://localhost:11434/v1` for Ollama). |
| `AI_API_STYLE`, `AI_STRUCTURED_OUTPUTS` | `responses`, `schema` | The default connection's API style (`responses` or `chat`) and structured-output mode (`schema` or `json`). See [ai-providers.md](./ai-providers.md). |
| `<ROLE>_BASE_URL`, `_API_KEY`, `_API_STYLE`, `_STRUCTURED_OUTPUTS` | empty | A role's own connection (`TUTOR_`, `AUTHORING_`, `TRANSCRIPTION_`, `VOICE_`): setting `<ROLE>_BASE_URL` takes that role off the default connection. Voice needs a Realtime server of its own unless the default is OpenAI's. |
| `SESSION_SECRET` | — | 16+ characters. Signs session tokens; startup aborts without it **unless `SECRETS_DIR` is set**, which generates one on first boot. |
| `SECRETS_DIR` | unset | A folder where `session_secret` and `encryption_key` are generated (`0600`) on first boot, and where the encrypted-key feature finds its key. The Docker image sets `/data/secrets`. See [first-run-setup.md](./first-run-setup.md). |
| `REGISTRATION_MODE` | `open` | `open`, `closed` (nobody can sign up) or `verification` (sign-up, but an admin enables the account first). Restart to change it. See [admin.md](./admin.md). |
| `COOKIE_SECURE` | `true` | Set `false` for `http://localhost`, or the browser drops the session cookie. `auto` is Secure only when the request came over HTTPS (the Docker image's default). |
| `MIGRATION_BACKUPS_KEPT` | `5` | Backups of the SQLite file kept by `python -m scripts.migrate` before a pending migration. |
| `DATABASE_URL` | `sqlite:///./data/celestin.db` | Run `uv run alembic upgrade head` once, and after every pull that adds a migration. A database created before the subjects became four categories (mathematics, sciences, languages, general) must be recreated: migration `0003` was edited in place, before any release, so its subject constraint changed and a course saved as `physics` no longer fits (delete `data/celestin.db`, then `alembic upgrade head`). |
| `PROMPTS_DIR` | `backend/prompts` | Tutor, subject, template and authoring prompts; checked at startup. |
| `OPENAI_MODEL` | `gpt-6.1-sol` | The tutor model (any model name the provider serves). `gpt-6-astra` (the flagship) if pedagogical quality disappoints, `gpt-6-luna` (much cheaper) if cost or latency matters. The other roles' models and efforts: `AUTHORING_*`, `TRANSCRIPTION_*`, `VOICE_*`, `TUTOR_REASONING_EFFORT` (empty = not sent; the built-in efforts apply to OpenAI only). |
| `MAX_TOOL_ROUNDS` | `6` | Rounds of tool use per turn before the turn ends with a notice. |
| `MAX_MESSAGE_CHARS` | `4000` | Per learner message. |
| `MAX_HISTORY_ENTRIES` | `400` | Per request. |
| `HISTORY_TOKEN_BUDGET` | `30000` | Transcript trimming threshold. The prompt prefix is never trimmed. |
| `CORS_ORIGINS` | empty | Comma-separated. Only needed if you stop using the proxy. |
| `DEBUG_LOG_PROMPTS` | `false` | Off by default: prompt and pack content stay out of the logs. |
| `MAX_COURSES_PER_STUDENT`, `MAX_CHAPTERS_PER_COURSE` | `30`, `40` | Courses per student, chapters per course. |
| `CHAPTER_TEXT_MIN_CHARS`, `CHAPTER_TEXT_MAX_CHARS`, `PACK_MAX_CHARS` | `300`, `100000`, `60000` | Edited text, transcription and pack sizes. |
| `MAX_BODY_BYTES` | `1048576` | Request bodies above it are refused before parsing, declared or streamed. |
| `DOCUMENT_MAX_BYTES`, `DOCUMENT_MAX_PAGES`, `DOCUMENT_MIN_PIXELS` | `26214400`, `50`, `800` | Uploads: size (the two upload routes' body cap), pages, short side of a photo. |
| `DOCUMENT_WORKERS`, `DOCUMENT_RENDER_TIMEOUT_S` | `2`, `60` | Processes that render pages; time per upload. |
| `TRANSCRIPTION_MODEL`, `TRANSCRIPTION_REASONING_EFFORT`, `TRANSCRIPTION_DETAIL` | `gpt-6.1-sol`, `low`, `high` | Reading the pages. |
| `TRANSCRIPTION_DPI`, `TRANSCRIPTION_MAX_SIDE_PX` | `150`, `1800` | PDF render resolution; longest side sent. |
| `TRANSCRIPTION_BATCH_PAGES`, `TRANSCRIPTION_CONCURRENCY`, `TRANSCRIPTION_MAX_OUTPUT_TOKENS` | `2`, `4`, `16000` | Pages per call; calls in flight per run; per call. |
| `TRANSCRIPTION_VERIFY_HANDWRITING` | `false` | A second look at handwritten figures; +75 % transcription cost, no gain measured. |
| `TRANSCRIPTION_PRICE_IN`, `_CACHED`, `_OUT` | `2.0`, `0.10`, `10.0` | USD per million tokens (`gpt-6.1-sol`'s). |
| `AUTHORING_MODEL`, `AUTHORING_REASONING_EFFORT` | `gpt-6.1-sol`, `medium` | The authoring agent, independent of the tutor model. |
| `AUTHORING_MAX_OUTPUT_TOKENS`, `AUTHORING_MAX_REPAIRS` | `32000`, `2` | Per call; repairs per stage. |
| `AUTHORING_TIMEOUT_S`, `AUTHORING_CALL_TIMEOUT_S` | `900`, `300` | Whole run, transcription included; one provider call. |
| `AUTHORING_CONCURRENT_PER_STUDENT`, `AUTHORING_RUNS_PER_DAY`, `AUTHORING_MAX_CONCURRENT` | `2`, `20`, `4` | Per-student limits; process-wide provider load. |
| `AUTHORING_PRICE_IN`, `_CACHED`, `_OUT` | `2.0`, `0.10`, `10.0` | USD per million tokens (`gpt-6.1-sol`'s), for the stored cost estimate. |
| `VOICE_ENABLED` | `true` | Voice mode (spec 003). When false the mic stays inert and `/api/voice/session` answers 503. |
| `VOICE_MODEL` | `gpt-realtime-2.1` | `gpt-realtime-2.1-mini` for the cheap comparison. Voice is on only with a Realtime-capable connection (spec 014). |
| `VOICE_NAME`, `VOICE_SPEED` | `marin`, `1.0` | Realtime voice and speed (0,25–1,5). |
| `VOICE_SESSION_MAX_S`, `VOICE_IDLE_S` | `1500`, `180` | Hard cap and idle cut-off of a spoken session. |
| `VOICE_SESSIONS_PER_HOUR` | `6` | Per signed-in user. |
| `VOICE_SECRET_TTL_S` | `90` | Lifetime of the ephemeral browser credential. Other `VOICE_*` keys: see `documentation/voice.md`. |

## Checks

```sh
cd backend  && uv run pytest                       # no network
cd frontend && npm test && npm run typecheck && npm run lint   # npm test compiles the messages and checks both languages first
```

These scripts talk to the real API and cost money, so none runs by default:

```sh
cd backend
uv run python -m scripts.smoke            # two turns on chapter 1; fails loudly if prompt caching stopped working
uv run python -m scripts.probe            # the R9 guardrail probes, writes probe-transcript.md
uv run python -m scripts.probe --charts   # chart probes (008) on the statistics fixture chapter, probe-transcript-charts.md
uv run python -m scripts.probe --flowcharts   # flowchart probes, on chapter 1 (synthesis section); probe-transcript-flowcharts.md
uv run python -m scripts.probe --figures      # figure probes, on the geometrie_analytique, inequations and statistique fixtures; probe-transcript-figures.md
uv run python -m scripts.probe --plots        # plot probes, on chapter 1 and the mru fixture (sciences); probe-transcript-plots.md
uv run python -m scripts.voice_smoke      # mints one Realtime client secret; proves the voice session config is accepted
uv run python -m scripts.authoring_eval   # authors the sample material; outputs in backend/.eval/ (~0,60 USD)
uv run python -m scripts.document_eval --pdf ../courses/chapitre_1.pdf   # reads and authors a document (~1 USD); --render-only is free
```

`smoke`, `probe` and the voice scripts run on files, not the database: `--chapter-dir` (default
`courses/chapitre_1`) and `--subject` (default `mathematics`) pick the chapter. The drawing probe
sets pick their own chapters instead: `--charts` the statistique fixture, `--flowcharts` chapter 1,
`--figures` the geometrie_analytique, inequations and statistique fixtures, `--plots` chapter 1 and
the mru fixture (all under `backend/tests/fixtures/chapters/` except chapter 1); `--chapter-dir`
runs a whole set on one chapter instead.

`smoke` is the fastest way to tell whether a change broke the cached prefix: it exits non-zero when
the second turn reports zero cached tokens. After changing a board block's schema, also run
`voice_smoke`: the Realtime session receives the same tool declarations, and only the real API says
whether it accepts them.

## Confirming it works

Sign in as the seeded student and open « Mes cours ». « Reprendre » or « Ouvrir » leads to chapter 1;
« Commencer » opens the lesson, where Célestin greets you in French, opens section 1 (« Leçon ») and puts
a card on the board. To check authoring, create a course, add a chapter from `courses/chapitre_1.pdf`
(16 scanned pages) or a few phone photos, and watch the row go from « Lecture des pages… (n/N) » to
« En préparation… » to « pas commencé » (about four minutes for the 16 pages).

Page rendering uses `pypdfium2` and Pillow (wheels, no system library) in worker processes. If an
upload answers « Ce document n'a pas pu être lu. », look for `document_render_failed` in the log.
