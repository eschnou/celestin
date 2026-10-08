# Docker image

The whole application in one image: the web app, the tutor service and the front door that routes between
them. Built from the repository root (`Dockerfile`), meant to be published to a registry such as Docker Hub
and run by anyone with an AI provider: an OpenAI key, a Groq key, or a model server of their own. Nothing has
to be configured to start it (spec 013).

## Run, set up, choose the provider

```sh
docker run -d --name celestin -p 8080:8080 -v ./data:/data celestin
```

1. **Run it.** No variable. Open <http://localhost:8080>: a fresh instance sends you to `/setup`.
2. **Set it up.** Create the administrator (your name, email and a password). The first visitor wins: do this
   right after the first start (see [the first-visitor risk](#the-first-visitor-risk)). You land on the
   administrator's dashboard.
3. **Choose the AI provider.** The dashboard's banner leads to the settings, « Fournisseur d'IA »: pick a preset
   (OpenAI is the default), paste the key and save. It is checked with the provider, stored encrypted, and used
   at once, with no restart. A local model server works too (no key; from the container, the host is
   `host.docker.internal`): see [ai-providers.md](./ai-providers.md). Students can register
   (`REGISTRATION_MODE=open`, the default) and start lessons.

`docker-compose.yml` is the same thing as a compose file. The data lives in the volume or folder mounted at
`/data`. `PORT=8100 docker compose up` publishes the single port on 8100 instead of 8080 (the container still listens
on 8080; `PORT` is read by Compose only and does not reach the application). `docker compose up --build` builds this
checkout instead of pulling the published image.

## What is inside

Three processes, started by `docker/entrypoint.sh` under `tini`. If one stops, the container stops, so the
orchestrator (`--restart`, compose, Kubernetes) restarts it.

| Process | Listens | What |
|---|---|---|
| Caddy (`docker/Caddyfile`) | `:8080` | The only published port. `/api/*` goes to the tutor service, everything else to the web server. Responses are not buffered on `/api` (the tutor's turns are server-sent events) and a request may take five minutes (a document read). |
| uvicorn (`app.main:create_app`) | `127.0.0.1:8000` | The tutor service, **one worker**: the rate limiters, the authoring runs, the key holder and the document workers live in the process. |
| Node (`.output/server/index.mjs`) | `127.0.0.1:3000` | The server-rendered web app, built with `NITRO_PRESET=node-server`. Its static files (KaTeX, icons, assets) are served by the same server. |

The browser sees one origin, as in development (where Vite proxies `/api`), so the same-origin check on
mutating API calls needs no configuration.

**Start-up**, in order: the entrypoint starts as root only to make `/data` writable by the application user
(uid 10001) when the mounted folder belongs to someone else, and drops to that user (`setpriv`); it stops with
a message if `/data` still is not writable. Then `python -m scripts.migrate` (a fresh volume gets its schema;
an upgrade is backed up, then migrated), then the three processes. Started with `--user`, there is no
ownership step and `/data` must be writable by that user.

## The data volume

| Path in `/data` | What |
|---|---|
| `celestin.db` | The SQLite database: accounts, courses, chapters, progress, the AI provider settings with their keys encrypted. Everything a student creates is a row in it. |
| `secrets/session_secret`, `secrets/encryption_key` | Generated on first boot, `0600`. See [first-run-setup.md](./first-run-setup.md). |
| `backups/` | A copy of the database taken before each pending migration (the newest 5), `0600` in a `0700` directory. |
| `caddy/` | Caddy's certificates and state (only used with a host name as `SITE_ADDRESS`). |

**A copy of the database file alone gives neither a session nor a provider key. A copy of the whole volume
contains the two secrets as well, so treat it like the server itself.** Back the volume up while the
container is stopped, or copy a file out of `backups/`:

```sh
docker stop celestin && cp -a ./data ./data.backup && docker start celestin
```

## Configuration

Everything is optional. Every variable of [running-locally.md](./running-locally.md) works as `-e NAME=value`,
and wins over what the interface stores (`OPENAI_API_KEY`, `OPENAI_BASE_URL` or a model set in the environment
makes that field of the « Fournisseur d'IA » section read-only). The image sets these defaults:

| Variable | Image default | Why |
|---|---|---|
| `DATABASE_URL` | `sqlite:////data/celestin.db` | The database lives on the `/data` volume. SQLite is the only supported database. |
| `SECRETS_DIR` | `/data/secrets` | The secrets are generated there on first boot. Set `SESSION_SECRET` to use your own session secret. |
| `COOKIE_SECURE` | `auto` | `Secure` only when the request came over HTTPS, so sign-in works on `http://localhost` and on a LAN address. |
| `TRUST_PROXY` | `true` | Caddy is always in front, and sets `X-Forwarded-For` and `X-Forwarded-Proto` (an outer proxy on a private network is believed about them). |
| `SITE_ADDRESS` | `:8080` | Caddy's address. Set a host name (`celestin.example.com`) and Caddy gets a certificate for it and listens on 80 and 443 (publish those ports; certificates are kept in `/data/caddy`). |

With `COOKIE_SECURE=auto`, behind an HTTPS proxy or with Caddy-managed TLS the cookie is `Secure`; on plain
HTTP it travels in clear, as the password does. Put a TLS proxy in front before exposing the instance beyond
a trusted network.

## Operating it

```sh
docker logs -f celestin        # one JSON line per event, each with a UTC `ts`; no prompt text unless DEBUG_LOG_PROMPTS=true
                               # a preparation: authoring_started, provider_call_progress (every 30 s), provider_call_done,
                               # authoring_stage, authoring_succeeded; on failure provider_call_failed (reason) and authoring_failed
docker exec -it celestin python -m scripts.create_admin --email admin@example.be   # another admin, or a lost password
docker exec celestin python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/health').read())"
```

The image has a `HEALTHCHECK` on `/api/health`; it passes while the instance waits for its first
administrator and while it has no AI provider (`ai_configured: false` in the answer says which).

**Upgrading** is pulling a newer image and recreating the container on the same volume: the migrations
run at start, after a backup. Pin a version tag rather than `latest`. A newer database refuses to start
under an older image (the existing schema check); restore a file from `backups/` or run the newer image.

## The first-visitor risk

`/setup` has no token: whoever opens a fresh instance first becomes its administrator. That is deliberate
(a small self-hosted project: convenience over strictness) and bounded: it exists only while the database
has no account at all, and closes for good with the first one. If the port is reachable by strangers before
you have finished, do one of: complete the setup immediately after `docker run`; start the container
unpublished (`-p 127.0.0.1:8080:8080`) and publish it after the setup; or create the administrator from the
command line before exposing it (`docker exec -it celestin python -m scripts.create_admin …`), which also
closes `/setup`.

## Publishing

`.github/workflows/image.yml` builds and publishes the image to the **GitHub Container Registry**
(`ghcr.io/<owner>/<repo>`). It needs no secret: the registry login is the workflow's own `GITHUB_TOKEN`.

| Event | What runs | Pushed tags |
|---|---|---|
| pull request to `main` | tests, image build, smoke test | none (nothing is published) |
| push to `main` | the same, then a multi-architecture build | `latest`, `sha-<commit>` |
| tag `v1.2.3` | the same | `1.2.3`, `1.2`, `latest`, `sha-<commit>` |

The jobs, in order: **test** (backend `pytest` on Python 3.12, the image's version; frontend `typecheck`,
`lint`, `test`), then **image**: the amd64 image is built and loaded, run through `docker/smoke.sh` (setup, a
restart, a read-only mount, an upgrade from an older database, an unprivileged user, a host name), and only
then the `linux/amd64,linux/arm64` image is built and pushed. A failing test or smoke check publishes
nothing. Servers are amd64 and Apple-silicon laptops arm64; every dependency has wheels for both. The arm64
half is built under QEMU, so the first run is slow; later runs reuse the layer cache.

**Once, on GitHub:**

1. Create the repository and push (`git remote add origin git@github.com:<owner>/<repo>.git`).
2. After the first successful run on `main`, open the repository's *Packages* → the image → *Package settings*
   and set the visibility to **Public**, so anyone can pull it without logging in (a package is private by
   default). The image is linked to the repository through its `org.opencontainers.image.source` label.

Pull requests, forks included, build and test but never publish. No other setting is needed.

```sh
docker pull ghcr.io/<owner>/<repo>:latest
docker run -d --name celestin -p 8080:8080 -v ./data:/data ghcr.io/<owner>/<repo>:latest
```

**Releasing a version:** `git tag v1.0.0 && git push origin v1.0.0`. Pin that tag (`:1.0.0`, or `:1.0` for
its patch releases) rather than `latest`: an upgrade runs migrations on the data volume.

**By hand**, or to Docker Hub as well (add a login step and a second entry in the workflow's `images:`):

```sh
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <namespace>/celestin:<version> -t <namespace>/celestin:latest --push .
docker build -t celestin:dev . && docker/smoke.sh celestin:dev     # what the workflow checks first
```

`docker/smoke.sh` makes no provider call; the tutor turn itself is checked by hand with a real key (the settings
screen's live check does it in a few clicks).

## What the image does not do

- **Scale out.** One container, one worker, SQLite: it serves a school or a class, not a platform. The
  in-process rate limiters, authoring runs and provider hub would need a shared store before a second replica.
- **Encrypt the volume.** The provider keys are encrypted in the database with a key that lives beside it on the
  volume: that protects a database copy, not the host. Use disk encryption and your orchestrator's secret
  store (`-e OPENAI_API_KEY=…`) if that matters to you.
- **Replace the Amplify build.** `npm run build` without `NITRO_PRESET` still produces the Amplify Hosting
  output, as before.
