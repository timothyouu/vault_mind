#!/usr/bin/env bash
# VaultMind startup — starts all three required processes concurrently.
# Usage: npm run vaultmind:start
# Requires: Docker (for Redis), Python 3, Node/npm

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== VaultMind: starting all processes ==="

# 1. Redis via docker compose (idempotent)
echo "[1/3] Starting Redis..."
if command -v docker &>/dev/null; then
    docker compose up -d
    echo "      Redis started via Docker"
else
    echo "      WARNING: Docker not found. Start Redis manually: redis-server"
    echo "      Or install Docker and re-run."
fi

# 2. Python watcher
echo "[2/3] Starting Python watcher (vaultmind-pipeline)..."
export VAULTMIND_VAULT_ROOT="${VAULTMIND_VAULT_ROOT:-$REPO_ROOT/vault}"
mkdir -p "$VAULTMIND_VAULT_ROOT/nodes"
python3 -m vaultmind.watcher &
WATCHER_PID=$!
echo "      Watcher PID: $WATCHER_PID"

# 3. Next.js dev server
echo "[3/3] Starting Next.js dev server on port 3000..."
cd "$REPO_ROOT/webapp"
# Propagate REPO_ROOT so conflicts.ts resolves vault/nodes/ and the Python
# scanner subprocess use the correct repo root, not a guessed path from cwd.
REPO_ROOT="$REPO_ROOT" npm run dev &
NEXTJS_PID=$!
echo "      Next.js PID: $NEXTJS_PID"

echo ""
echo "=== All processes started ==="
echo "  Redis:   port 6379 (Docker) or external"
echo "  Watcher: PID $WATCHER_PID"
echo "  Next.js: http://localhost:3000 (PID $NEXTJS_PID)"
echo ""
echo "Press Ctrl+C to stop all processes."

# Wait for all background processes
wait $WATCHER_PID $NEXTJS_PID
