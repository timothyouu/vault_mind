#!/usr/bin/env bash
# VaultMind pre-commit hook — scans staged vault/ files for secrets.
# Installed at .git/hooks/pre-commit
# Source: vaultmind/hooks/pre-commit.sh
set -euo pipefail

# python3 on Linux/Mac; Windows may only have 'python'
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Error: Python not found in PATH" >&2
    exit 1
fi

FAILED=0

# Get list of staged vault/ files
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep '^vault/' || true)

if [ -z "$STAGED" ]; then
    exit 0
fi

for FILE in $STAGED; do
    if [ ! -f "$FILE" ]; then
        continue
    fi
    # python -m vaultmind.secrets always exits 0; we read the JSON
    RESULT=$($PYTHON -m vaultmind.secrets "$FILE")
    COUNT=$(echo "$RESULT" | $PYTHON -c "import sys,json; data=json.load(sys.stdin); print(len(data))")
    if [ "$COUNT" -gt 0 ]; then
        echo "$RESULT" | $PYTHON -c "
import sys, json
data = json.load(sys.stdin)
for m in data:
    print(f\"{sys.argv[1]}:{m['line']}  {m['description']}\")
" "$FILE"
        FAILED=1
    fi
done

if [ "$FAILED" -eq 1 ]; then
    echo ""
    echo "Commit blocked: secret(s) detected in staged vault/ files."
    echo "Fix the flagged file(s) and re-commit."
    exit 1
fi
exit 0
