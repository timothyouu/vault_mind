#!/usr/bin/env bash
# VaultMind startup — starts all three required processes concurrently.
# Usage: npm run vaultmind:start
# Requires: Redis Stack (bundled at ~/redis-stack/), Python 3, Node/npm

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REDIS_STACK_BIN="${HOME}/redis-stack/redis-stack-server-7.4.0-v3/bin"
REDIS_PORT="${REDIS_PORT:-6380}"

cd "$REPO_ROOT"

echo "=== VaultMind: starting all processes ==="

# 1. Redis Stack — includes RediSearch (vector search), RedisJSON, RedisBloom
echo "[1/3] Checking Redis Stack (port ${REDIS_PORT})..."
if "${REDIS_STACK_BIN}/redis-cli" -p "${REDIS_PORT}" ping &>/dev/null; then
    echo "      Redis Stack already running on port ${REDIS_PORT}"
else
    echo "      Starting Redis Stack with RediSearch..."
    "${REDIS_STACK_BIN}/redis-stack-server" \
        --port "${REDIS_PORT}" \
        --daemonize yes \
        --logfile /tmp/redis-stack.log \
        --dir /tmp
    sleep 2
    echo "      Redis Stack started on port ${REDIS_PORT}"
fi

# 2. Python watcher
echo "[2/3] Starting Python watcher (vaultmind-pipeline)..."
export VAULTMIND_VAULT_ROOT="${VAULTMIND_VAULT_ROOT:-$REPO_ROOT/vault}"
export REDIS_URL="${REDIS_URL:-redis://localhost:${REDIS_PORT}}"
mkdir -p "$VAULTMIND_VAULT_ROOT/nodes"
python3 -m vaultmind.watcher &
WATCHER_PID=$!
echo "      Watcher PID: $WATCHER_PID"

# 3. Next.js dev server
echo "[3/3] Starting Next.js dev server on port 3000..."
cd "$REPO_ROOT/webapp"
# Propagate REPO_ROOT so conflicts.ts resolves vault/nodes/ and the Python
# scanner subprocess use the correct repo root, not a guessed path from cwd.
REPO_ROOT="$REPO_ROOT" REDIS_URL="${REDIS_URL}" npm run dev &
NEXTJS_PID=$!
echo "      Next.js PID: $NEXTJS_PID"

echo ""
echo "=== All processes started ==="
echo "  Redis Stack: port ${REDIS_PORT} (RediSearch + RedisJSON + RedisBloom)"
echo "  Watcher:     PID $WATCHER_PID"
echo "  Next.js:     http://localhost:3000 (PID $NEXTJS_PID)"
echo ""
echo "Press Ctrl+C to stop all processes."

# Wait for all background processes
wait $WATCHER_PID $NEXTJS_PID
