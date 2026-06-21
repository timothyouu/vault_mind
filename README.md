# VaultMind

Persistent, structured project memory in Obsidian-compatible Markdown. All transferable between LLM tools (Claude Code, Codex, Gemini) without needing late-stage summarization.

A multi-agent pipeline watches your Claude Code / Codex sessions and writes a git-native vault of decisions, constraints, goals, and questions as you work. A Next.js web app lets you review, approve, and hand off that vault to a receiving agent. A Fetch.AI Orchestrator uAgent sits on ASI:One so you can query project state or trigger handoff via natural language.

---

## Architecture

```
Claude Code / Codex hooks
        │  Stop / SessionEnd
        ▼
  Python watcher  ──(Redis Streams)──►  Scribe → Note Creator → Connector
        │                                                              │
        │                                              vault/nodes/*.md (disk)
        │                                                              │
        └──────────────────(Redis pub/sub)──────────────────────────► SSE
                                                                       │
                                                                  Next.js app
                                                                  (port 3000)
                                  Orchestrator uAgent (Fetch.AI / ASI:One)
```

**Stack:** Python 3.11+ · Next.js 15 / React 19 · Redis (Streams + pub/sub + vector) · Fetch.AI uAgents · Arize (LLM observability)

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | pipeline + hooks |
| Node.js | 18 | webapp |
| Docker | any recent | Redis via `docker compose` |
| Git | any | pre-commit hook for secret scanning |

---

## Quickstart (running the product)

1. **Clone and install**

   ```bash
   git clone <repo-url>
   cd vault_mind
   pip install -e .
   cd webapp && npm install && cd ..
   ```
 
The `-e` flag installs the Python package in editable mode, so changes you make to the source are picked up immediately without reinstalling.

2. **Set environment variables**

   Copy the example and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   Required:

   ```
   ANTHROPIC_API_KEY=sk-ant-...       # Scribe extraction + evaluator judge
   ARIZE_SPACE_KEY=...                # Arize LLM observability
   ARIZE_API_KEY=...                  # Arize LLM observability
   REDIS_URL=redis://localhost:6379   # default; change if using external Redis
   ```

   Optional:

   ```
   VAULTMIND_VAULT_ROOT=/path/to/vault   # defaults to <repo>/vault
   REPO_ROOT=/path/to/repo               # used by webapp conflict resolver
   ```
   
> `VAULTMIND_VAULT_ROOT` is useful if you want the vault to live outside the repo — for example, inside an Obsidian vault you already have open. The app will still track it the same way.

3. **Start everything**

   ```bash
   npm run vaultmind:start
   ```

   This starts three processes concurrently:
   - **Redis** on port 6379 via `docker compose up -d` (RedisInsight UI on port 8001)
   - **Python watcher** (`python -m vaultmind.watcher`) — pipeline consumer loop
   - **Next.js dev server** at http://localhost:3000

4. **Wire the hooks**

   Add the hook configs so VaultMind captures your sessions:

   **Claude Code** — `.claude/settings.json`:
   ```json
   {
     "hooks": {
       "Stop": [{ "hooks": [{ "type": "command", "command": "python3 .vaultmind/hooks/on_stop.py", "async": true }] }],
       "SessionEnd": [{ "hooks": [{ "type": "command", "command": "python3 .vaultmind/hooks/on_session_end.py", "async": true }] }]
     }
   }
   ```

   **Codex** — `.codex/hooks.json`:
   ```json
   {
     "hooks": {
       "Stop": [{ "hooks": [{ "type": "command", "command": "python3 .vaultmind/hooks/on_stop.py" }] }]
     }
   }
   ```

5. **Open the app** at http://localhost:3000 and start a Claude Code or Codex session — nodes will appear in real time.

---

## Developer setup

Everything above, plus:

1. **Install dev dependencies**

   ```bash
   pip install -e ".[dev]"
   ```

2. **Install the pre-commit hook** (blocks commits that contain secrets in `vault/`)

   ```bash
   git config core.hooksPath .git/hooks
   cp .vaultmind/hooks/pre-commit .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

3. **Run tests**

   ```bash
   pytest
   ```

4. **Run the webapp in isolation** (without the Python pipeline)

   ```bash
   cd webapp
   npm run dev
   ```

5. **Scan a vault node for secrets manually**

   ```bash
   python -m vaultmind.secrets vault/nodes/<node>.md
   ```

   Exits 0 always; prints a JSON array of matches (`[]` = clean). The pre-commit hook reads this and exits 1 itself if matches are present.

---

## Project structure

```
vault_mind/
├── vaultmind/            # Python package — pipeline, hooks, agents
│   ├── contracts.py      # Pydantic v2 message contracts (frozen — do not edit)
│   ├── secrets.py        # scanForSecrets — one implementation
│   ├── watcher.py        # Redis Streams consumer loop
│   ├── scribe/           # LLM extraction agent
│   ├── notecreator/      # writes vault/nodes/*.md
│   ├── connector/        # links related nodes
│   ├── orchestrator/     # Fetch.AI uAgent (ASI:One face + handoff)
│   ├── ingest/           # hook → queue producer (P1)
│   ├── evals/            # end-to-end pipeline evaluator
│   └── hooks/            # on_stop.py, on_session_end.py, pre-commit
├── webapp/               # Next.js 15 app (TypeScript, Tailwind, App Router)
│   ├── types.ts          # TS contracts mirroring contracts.py (frozen — do not edit)
│   └── src/app/
│       ├── page.tsx            # vault live view (SSE)
│       ├── merge/page.tsx      # conflict resolution UI
│       └── api/
│           ├── events/         # SSE endpoint → Redis pub/sub
│           └── conflicts/      # conflict list + per-node resolve
├── vault/                # the live vault (git-tracked Markdown)
│   ├── nodes/            # turn-nodes: YYYY-MM-DD-HHMM-<slug>.md
│   ├── IntentLog.md      # append-only developer intent
│   ├── SessionState.md   # compaction + session-end events
│   └── VaultIndex.md     # static read-order map for receiving agents
├── fixtures/             # fixture transcript + fixture vault for tests
├── scripts/start.sh      # starts Redis + watcher + Next.js
├── docker-compose.yml    # Redis (redis-stack with RedisSearch)
├── pyproject.toml
└── package.json          # root — vaultmind:start script
```

---

## Key rules (enforced by the codebase)

- **Disk is the source of truth.** Redis events are minimal triggers; the app re-reads files on every event.
- **One `scanForSecrets` implementation.** Always `vaultmind/secrets.py` — the webapp shells out to it, never reimplements it.
- **Node bodies are immutable after write.** The Connector edits only frontmatter `related`; it never touches the body.
- **No silent commits or handoffs.** Commits are manual; a detected secret blocks both commit and handoff.
- **`IntentLog.md` is the developer's own words.** Only Auto Mode may write an `ai-detected` entry, and it must be labeled as such.

See `SPEC.md` for the full technical contracts and `WORKSTREAMS.md` for the build execution plan.
