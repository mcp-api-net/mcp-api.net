#!/usr/bin/env bash
#
# In-place deploy worker — always runs ON the server. Invoked two ways, both of
# which produce an identical result:
#   * directly by deploy/deploy.sh when that is run on the server itself, and
#   * piped over SSH by deploy/deploy.sh from a dev machine.
#
# Idempotent. Configurable via env (deploy.sh sets these):
#   REMOTE_DIR  REPO_URL  BRANCH  PROXY_CONTAINER
set -euo pipefail

REMOTE_DIR="${REMOTE_DIR:-/home/claude-agent/mcp-api-net}"
REPO_URL="${REPO_URL:-https://github.com/mcp-api-net/mcp-api.net.git}"
BRANCH="${BRANCH:-master}"
PROXY_CONTAINER="${PROXY_CONTAINER:-proxy-caddy}"

if [ ! -d "$REMOTE_DIR/.git" ]; then
  echo "    First deploy — cloning $REPO_URL"
  git clone "$REPO_URL" "$REMOTE_DIR"
fi

if ! git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$REMOTE_DIR"; then
  git config --global --add safe.directory "$REMOTE_DIR"
fi

cd "$REMOTE_DIR"

echo "    Syncing $BRANCH from origin…"
git fetch --all --prune
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -f .env ]; then
  echo "!!  No .env in $REMOTE_DIR — create one (see .env.example) before first run."
  exit 1
fi

echo "    Pulling image and (re)starting the web container…"
docker compose pull
docker compose up -d --remove-orphans

echo "    Reloading the shared Caddy proxy (picks up deploy/caddy fragments)…"
docker exec "$PROXY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile 2>/dev/null \
  || echo "    (proxy not running, fragment not yet mounted, or reload failed — check the proxy stack)"

echo "    Reclaiming disk (dangling images > 1 week)…"
docker image prune -f >/dev/null

docker compose ps
