# syntax=docker/dockerfile:1

# Célestin in one image: the web app (Node), the tutor service (Python) and Caddy in front.
#   docker build -t celestin .
#   docker run -p 8080:8080 -v celestin-data:/data celestin     # then open http://localhost:8080
# See documentation/docker.md.

# --- the web app: a standalone Node server (nitro preset node-server) ---
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NITRO_PRESET=node-server
RUN npm run build

# --- the tutor service's dependencies ---
FROM python:3.12-slim-bookworm AS api
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# --- the image ---
FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini libcap2-bin \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin celestin \
    && mkdir /data && chown celestin /data
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=caddy:2 /usr/bin/caddy /usr/local/bin/caddy
# So that Caddy, run as the unprivileged user, can bind 80 and 443 when SITE_ADDRESS is a host name.
RUN setcap cap_net_bind_service=+ep /usr/local/bin/caddy
COPY --from=api /opt/venv /opt/venv
COPY backend/alembic.ini /app/backend/
COPY backend/app /app/backend/app
COPY backend/prompts /app/backend/prompts
COPY backend/scripts /app/backend/scripts
COPY --from=web /web/.output /app/web
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Nothing here is required of the operator (spec 013): the secrets are generated into /data/secrets, the
# administrator and the AI provider are entered in the browser. COOKIE_SECURE=auto: Secure only over HTTPS.
# The container starts as root, fixes /data's ownership and drops to uid 10001 (docker/entrypoint.sh).
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/celestin.db \
    SECRETS_DIR=/data/secrets \
    COOKIE_SECURE=auto \
    XDG_DATA_HOME=/data/caddy \
    XDG_CONFIG_HOME=/data/caddy \
    TRUST_PROXY=true
WORKDIR /app/backend
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
ENTRYPOINT ["tini", "--", "entrypoint.sh"]
