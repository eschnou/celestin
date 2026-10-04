#!/bin/bash
# One container, three processes: the tutor service (uvicorn), the web server (node) and Caddy in front
# of both. If any of them stops, the container stops, and the orchestrator restarts it.
#
# Nothing is required from the operator (spec 013): the secrets are generated into /data/secrets on the first
# boot, the administrator is created in the browser, the AI provider is chosen there too. It starts as root
# for one reason, to make a mounted /data writable by the application user, and then drops to that user.
set -euo pipefail

APP_UID=10001
fail() { echo "celestin: $1" >&2; exit 1; }
as_app() { setpriv --reuid="$APP_UID" --regid="$APP_UID" --clear-groups "$@"; }

if [ "$(id -u)" = 0 ]; then
  mkdir -p /data
  # Only when the top directory is somebody else's: a large volume is not walked at every start. Some host
  # mounts refuse a chown; what matters is whether the application user can write, checked next.
  if [ "$(stat -c %u /data)" != "$APP_UID" ]; then
    chown -R "$APP_UID:$APP_UID" /data 2>/dev/null || true
  fi
  as_app test -w /data \
    || fail "/data is not writable by the application user (uid $APP_UID). Mount a volume or a folder there that it can write to (docker run -v ./data:/data ...)."
  exec setpriv --reuid="$APP_UID" --regid="$APP_UID" --clear-groups /usr/local/bin/entrypoint.sh "$@"
fi

# Started with --user: no ownership to fix, only a directory to check.
[ -w /data ] || fail "/data is not writable by uid $(id -u). Mount a volume or a folder there that this user can write to."
mkdir -p /data/caddy

cd /app/backend
python -m scripts.migrate

uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log &
NITRO_HOST=127.0.0.1 NITRO_PORT=3000 node /app/web/server/index.mjs &
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &

# tini forwards SIGTERM here; pass it on and wait for the children to finish.
trap 'kill $(jobs -p) 2>/dev/null || true' TERM INT
wait -n
status=$?
kill $(jobs -p) 2>/dev/null || true
wait || true
exit "$status"
