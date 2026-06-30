#!/usr/bin/env bash
#
# Deploy mcp-api.net. Works from two places, no flags needed:
#
#   * From a dev machine (or the agent's box): pushes local commits, then runs the
#     deploy on the server over the `recall-server` SSH alias.
#   * On the server itself: deploys in place — no SSH hop.
#
# Either way the heavy lifting is deploy/_server_deploy.sh (git sync + Compose
# pull/up + Caddy reload), so both paths run identical logic. The container runs
# the published ghcr.io/mcp-api-net/mcp-api.net image; nothing is built from
# source on the server.
#
# Usage:  ./deploy/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER="$SCRIPT_DIR/_server_deploy.sh"

SSH_ALIAS="${MCP_API_NET_SSH_ALIAS:-recall-server}"
REMOTE_DIR="${MCP_API_NET_REMOTE_DIR:-/home/claude-agent/mcp-api-net}"
REPO_URL="${MCP_API_NET_REPO_URL:-https://github.com/mcp-api-net/mcp-api.net.git}"
BRANCH="${MCP_API_NET_BRANCH:-master}"
SERVER_HOST="${MCP_API_NET_SERVER_HOST:-setti-server}"
PROXY_CONTAINER="${MCP_API_NET_PROXY_CONTAINER:-proxy-caddy}"

# Already on the server → deploy in place, skipping the push + SSH hop.
if [ "$(hostname)" = "$SERVER_HOST" ]; then
  echo "==> On $SERVER_HOST — deploying $REMOTE_DIR in place…"
  REMOTE_DIR="$REMOTE_DIR" REPO_URL="$REPO_URL" BRANCH="$BRANCH" \
    PROXY_CONTAINER="$PROXY_CONTAINER" exec bash "$WORKER"
fi

# Dev machine → ship the code, then run the worker on the server over SSH. The
# worker is piped in over stdin, so the server runs this checkout's deploy logic
# (even before it has pulled it).
echo "==> Pushing local commits ($BRANCH)…"
git push origin "$BRANCH"

echo "==> Deploying on $SSH_ALIAS:$REMOTE_DIR…"
ssh "$SSH_ALIAS" \
  REMOTE_DIR="$REMOTE_DIR" REPO_URL="$REPO_URL" BRANCH="$BRANCH" PROXY_CONTAINER="$PROXY_CONTAINER" \
  'bash -s' < "$WORKER"

echo "==> Done. Live behind the shared Caddy proxy at https://mcp-api.net"
