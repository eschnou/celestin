#!/bin/bash
# Smoke test of a built image, with no variable and no OpenAI call (spec 013 R10).
#
#   docker/smoke.sh celestin:dev            # PORT=18080 by default
#
# 1. a fresh bind mount, owned by another user: the container fixes it, drops privileges, waits for its first
#    administrator; setup, restart (the data and the secrets survive), a read-only mount refused;
# 2. a database left at the previous revision: migrated, with a backup beside it;
# 3. as an unprivileged user (--user), and with a host name as SITE_ADDRESS (Caddy binds 80 and 443).
set -euo pipefail

image=${1:?usage: docker/smoke.sh <image>}
port=${PORT:-18080}
name=celestin-smoke-$$
work=$(mktemp -d)
failures=0

say() { printf '\n== %s\n' "$*"; }
ok() { printf '   ok   %s\n' "$*"; }
bad() { printf '   FAIL %s\n' "$*"; failures=$((failures + 1)); }
check() { # check "description" command...
  local what=$1; shift
  if "$@" >/dev/null 2>&1; then ok "$what"; else bad "$what"; fi
}
json() { python3 -c "import sys, json; d = json.load(sys.stdin); print(d$1)"; }
as_root() { docker run --rm --entrypoint "$1" -v "$work/data:/data" "$image" "${@:2}"; }

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run --rm --entrypoint chown -v "$work:/work" "$image" -R "$(id -u):$(id -g)" /work >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

wait_healthy() {
  for _ in $(seq 1 90); do
    if curl -fs "http://localhost:$port/api/health" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  docker logs "$name" 2>&1 | tail -20
  return 1
}

say "1. a fresh bind mount owned by another user"
mkdir "$work/data"
as_root chown -R 12345:12345 /data
docker run -d --name "$name" -p "$port:8080" -v "$work/data:/data" "$image" >/dev/null
check "the container becomes healthy with no variable" wait_healthy
check "/data was handed to the application user" test "$(docker exec "$name" stat -c %u /data)" = 10001
check "the processes run as that user, not as root" test "$(docker exec "$name" ps -o user= -C uvicorn,python 2>/dev/null | sort -u | tr -d ' \n')" != root
health=$(curl -s "http://localhost:$port/api/health")
check "no AI is configured yet" test "$(echo "$health" | json "['ai_configured']")" = False
check "the instance waits for its first administrator" test "$(curl -s "http://localhost:$port/api/auth/config" | json "['setup_required']")" = True
check "the web page is served through the front door" curl -fs "http://localhost:$port/login"
check "registration waits for the administrator" test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:$port/api/auth/register" -H 'content-type: application/json' -d '{"email":"s@x.be","name":"S","password":"mot-de-passe-solide"}')" = 409
jar="$work/cookies"
code=$(curl -s -o /dev/null -w '%{http_code}' -c "$jar" -X POST "http://localhost:$port/api/setup" -H 'content-type: application/json' -d '{"email":"ada@example.be","name":"Ada","password":"mot-de-passe-solide"}')
check "setup creates the administrator (HTTP $code)" test "$code" = 201
check "the cookie is not Secure over plain HTTP (COOKIE_SECURE=auto)" bash -c "! grep -q 'TRUE.*celestin_session' <(awk '\$4 == \"TRUE\"' '$jar')"
check "the session works" test "$(curl -s -b "$jar" "http://localhost:$port/api/auth/me" | json "['user']['role']")" = admin
check "setup is closed for good" test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:$port/api/setup" -H 'content-type: application/json' -d '{"email":"eve@example.be","name":"Eve","password":"mot-de-passe-solide"}')" = 409
check "the secrets are private files" test "$(docker exec "$name" stat -c '%a' /data/secrets/session_secret /data/secrets/encryption_key | tr '\n' ' ')" = "600 600 "
check "the secrets directory is private" test "$(docker exec "$name" stat -c %a /data/secrets)" = 700

docker restart "$name" >/dev/null
check "it comes back healthy after a restart" wait_healthy
check "setup is still closed after the restart" test "$(curl -s "http://localhost:$port/api/auth/config" | json "['setup_required']")" = False
check "the old session still works: the secret and the data survived" test "$(curl -s -b "$jar" "http://localhost:$port/api/auth/me" | json "['user']['email']")" = ada@example.be
check "signing in again works" test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:$port/api/auth/login" -H 'content-type: application/json' -d '{"email":"ada@example.be","password":"mot-de-passe-solide"}')" = 200
docker rm -f "$name" >/dev/null

out=$(docker run --rm -v "$work/data:/data:ro" "$image" 2>&1 || true)
check "a read-only mount stops the container with the reason" grep -q "is not writable" <<<"$out"

say "2. a database at the previous revision"
rm -rf "$work/data" && mkdir "$work/data"
as_root chown -R 10001:10001 /data
docker run --rm --user 10001:10001 -v "$work/data:/data" --entrypoint python -w /app/backend "$image" -c "
from alembic import command
from app.db.schema import alembic_config
import sqlite3
url = 'sqlite:////data/celestin.db'
command.upgrade(alembic_config(url), '0008')
with sqlite3.connect('/data/celestin.db') as c:
    c.execute(\"insert into users (id, email, name, password_hash, role, locale, enabled, created_at) values ('u1', 'old@example.be', 'Old', 'x', 'student', 'fr', 1, '2026-01-01 00:00:00')\")
" >/dev/null 2>&1
docker run -d --name "$name" -p "$port:8080" -v "$work/data:/data" "$image" >/dev/null
check "the container migrates and becomes healthy" wait_healthy
check "a backup of the 0008 database was made" test "$(docker exec "$name" sh -c 'ls /data/backups/celestin-*-from-0008.db | wc -l')" = 1
check "the backup is private" test "$(docker exec "$name" sh -c 'stat -c %a /data/backups /data/backups/celestin-*-from-0008.db | tr "\n" " "')" = "700 600 "
check "the account survived" test "$(docker exec "$name" python -c "import sqlite3; print(sqlite3.connect('/data/celestin.db').execute('select email from users').fetchone()[0])")" = old@example.be
check "the instance has an account, so no setup" test "$(curl -s "http://localhost:$port/api/auth/config" | json "['setup_required']")" = False
docker rm -f "$name" >/dev/null

say "3. an unprivileged user, and a host name"
rm -rf "$work/data" && mkdir "$work/data"
as_root chown -R 12345:12345 /data
docker run -d --name "$name" --user 12345:12345 -p "$port:8080" -v "$work/data:/data" "$image" >/dev/null
check "started with --user it runs as that user" wait_healthy
docker rm -f "$name" >/dev/null
docker run -d --name "$name" -e SITE_ADDRESS=localhost -v "$work/data:/data" "$image" >/dev/null
sleep 15
for p in 80 443; do
  check "with SITE_ADDRESS=localhost Caddy listens on $p as the unprivileged user" docker exec "$name" python -c "import socket; socket.create_connection(('127.0.0.1', $p), 3)"
done
docker rm -f "$name" >/dev/null

echo
if [ "$failures" = 0 ]; then echo "smoke: all checks passed"; else echo "smoke: $failures check(s) FAILED"; exit 1; fi
