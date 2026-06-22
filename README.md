# VaultMind

**Persistent, structured project memory for AI coding tools — written as plain Markdown, owned by you, transferable between agents without summarization.**

---

## Why VaultMind exists

### The problem
When you build software with an AI coding agent (Claude Code, Codex, Gemini), the *reasoning* lives in
the chat: the decisions you made, the constraints you ruled out, the goals you set, the questions still
open. That context dies in three ways:

1. **It's locked in one tool.** Your Claude Code history doesn't transfer to Codex. Switching agents means
   re-explaining the project from scratch.
2. **It's destroyed by compaction.** Long sessions get summarized, and summarization throws away exactly
   the nuance (*why* you rejected option B) that matters most later.
3. **It's never reviewable.** There's no durable, human-auditable record of *what the project knows about
   itself* — only an ephemeral transcript.

### The solution
VaultMind watches your coding sessions and continuously writes a **git-native vault of structured
knowledge nodes** — decisions, constraints, goals, and open questions — in **Obsidian-compatible
Markdown**. Because the vault is just files on disk:

- **It's portable.** Any agent (or human) can read it. Handoff = "here are the files," not "let me
  summarize."
- **It's lossless.** Knowledge is captured turn-by-turn as you work, never late-stage-summarized.
- **It's yours and auditable.** Every node is a reviewable Markdown file under version control, and a
  web UI lets you inspect, link, resolve conflicts, and approve handoff before anything leaves your machine.

A multi-agent pipeline does the writing. A **Fetch.AI Orchestrator uAgent** (published on Agentverse /
ASI:One) lets you query project state or trigger handoff in natural language. A secret scanner blocks any
credential from ever reaching disk, a commit, or a handoff.

---

## Tech stack

| Layer | Technology |
|---|---|
| **Pipeline & agents** | Python 3.11+, Pydantic v2 (frozen message contracts) |
| **LLM extraction** | Anthropic SDK — `claude-sonnet-4-6` (Scribe extraction + merge recommendations + eval judge) |
| **Queue / events / vector** | Redis Stack (Streams = work queue, pub/sub = event bus, RediSearch = vector index) |
| **Semantic memory** | RedisVL + `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim, runs fully offline) |
| **Observability** | Arize via `arize-otel` + OpenTelemetry spans across every pipeline stage |
| **Web app** | Next.js 15, React 19, TypeScript (strict), Tailwind, App Router, Server-Sent Events |
| **Conversational agent** | Fetch.AI `uagents` + `uagents-core` Chat Protocol, Agentverse mailbox, ASI:One |
| **Agent bridge** | Flask + flask-cors (HTTP ↔ uAgent queue bridge) |
| **Tests** | pytest, pytest-asyncio, fakeredis |

The only cross-language seams are `vault/*.md` on disk and Redis. **Disk is always the source of truth** —
Redis events are minimal "re-read this id" triggers, never payloads.

---

## Architecture

```
 Claude Code / Codex session
        │  Stop / SessionEnd hooks
        ▼
  ingest/ (producer) ──XADD──► Redis Stream  vaultmind:turns
                                     │  XREADGROUP (consumer group)
                                     ▼
                              watcher.py  (consumer loop, Arize-traced)
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                         ▼
        scribe/                 notecreator/              connector/
   (LLM extraction)        (writes vault/nodes/*.md)   (links `related`,
                            + atomic IntentLog            vector + heuristic)
                                     │
                              vault/*.md on disk  ◄── secrets.py scan (write-time)
                                     │
                       Redis pub/sub  vaultmind:events / :progress
                                     │
            ┌────────────────────────┴───────────────────────────┐
            ▼                                                     ▼
   Next.js web app (SSE, port 3000)                  Orchestrator uAgent
   home · setup · graph · intent · merge        (Fetch.AI / Agentverse / ASI:One)
            ▲                                                     ▲
            └────────── /api/agent ──► Flask bridge ──► uAgent ──┘
```

---

## What's in the box

### `vaultmind/` — Python pipeline, agents, hooks

| Module | Role |
|---|---|
| `contracts.py` | Pydantic v2 message contracts shared by every stage (**frozen — do not edit**). |
| `secrets.py` + `secret-patterns.json` | The single `scanForSecrets` implementation. Everything else shells out to it — never reimplements it. |
| `watcher.py` | Redis Streams consumer loop. Consumer group, pending-entry reclaim on crash, ACK-only-after-success, Arize spans per stage, runs the eval. Exposes `SCRIBE_FN` / `NOTE_CREATOR_FN` / `CONNECTOR_FN` plug-in seams. |
| `ingest/` | Hook → queue producer: `reader.py`, `cursor.py` (resume point), `producer.py` (XADD), `session_state.py`. |
| `scribe/` | LLM extraction (`extract()`, `prompt.md`) — turns a transcript turn into structured `Extraction`s via `claude-sonnet-4-6`. |
| `notecreator/` | `write_nodes()` (wraps the Scribe's text verbatim), `atomic_write()`, `append_intentlog_entry()`. |
| `connector/` | `link_node()` — heuristic (title/type/scope-anchor) + vector linking; **only ever edits the `related:` frontmatter, never the body.** |
| `memory/` | `VaultMemory` — RedisVL vector index over node bodies for semantic "related node" search. |
| `handoff/` | `check_handoff_readiness()` (handoff-time secret scan) + `assemble_entry_point()`. |
| `orchestrator/` | `handle_intent()` (3 ASI:One intents), `InFlightTracker` (stuck-turn detection), `run_orchestrator()` (the uAgent w/ Chat Protocol + Redis progress subscription). |
| `evals/` | `run_eval()` + `pipeline_eval_prompt.md` — LLM-judge evaluation of pipeline output. |
| `arize_init.py` | OpenTelemetry / Arize tracer setup and span-name constants. |
| `hooks/` | `claude_settings.json`, `codex_hooks.json`, `pre-commit.sh`. |
| `templates/` | `turn_node.md`, `scope_node.md`, `IntentLog.md`, `SessionState.md`, `VaultIndex.md`. |

> **Pipeline status:** the production agents in `scribe/`, `notecreator/`, and `connector/` are fully
> implemented and tested. The `watcher.py` hot path ships wired to lightweight stub plug-ins
> (`stub_scribe` / `stub_note_creator` / `stub_connector`) so it runs offline; the real agents drop into
> the same `SCRIBE_FN` / `NOTE_CREATOR_FN` / `CONNECTOR_FN` seams.

### `webapp/` — Next.js 15 trust UI

| Path | Role |
|---|---|
| `src/app/page.tsx` | **Home** — live vault view, SSE-driven node list. |
| `src/app/setup/page.tsx` | **Setup** — copy-paste hook install wizard for Claude Code & Codex. |
| `src/app/graph/page.tsx` | **Graph** — interactive node/link graph of the vault. |
| `src/app/intent/page.tsx` | **Intent log** — `IntentLog.md` viewer (developer's own words). |
| `src/app/merge/page.tsx` | **Merge** — GitHub-dark conflict-resolution UI: per-hunk accept/reject, "write your own," one-click VaultMind-AI recommendations, secret-scan-blocked panel. |
| `src/components/AgentChat.tsx` + `src/lib/useAgent.ts` | Chat panel that talks to the Fetch.AI agent. |
| `src/app/api/events/` | SSE endpoint — subscribes to Redis `vaultmind:events`. |
| `src/app/api/nodes/` | Reads + parses `vault/nodes/*.md`. |
| `src/app/api/conflicts/` | List / detail / `resolve` / `recommend` (AI merge suggestions via Anthropic). |
| `src/app/api/agent/` | Proxies chat messages to the Flask bridge. |
| `src/lib/conflicts.ts` | Server-only git-conflict parser; delegates secret scan to `python3 -m vaultmind.secrets`. |
| `agent_bridge.py` | Flask HTTP API (port 5002) ↔ uAgent (port 8002) ↔ Orchestrator. |
| `types.ts` | TS contracts mirroring `contracts.py` (**frozen — do not edit**). |

### `vault-mind-orchestrate/` — deployable Fetch.AI agent
Standalone `agent.py` (mailbox + `publish_agent_details`) that registers on **Agentverse** so the
Orchestrator is reachable from **ASI:One** chat. Has its own `Makefile`, `requirements.txt`, and tests.

### `vault/` — the live vault (git-tracked Markdown)
```
vault/
├── nodes/           # turn-nodes & scope-nodes: YYYY-MM-DD-HHMM-<slug>.md
├── IntentLog.md     # append-only, the developer's own words
├── SessionState.md  # compaction + session-end events
└── VaultIndex.md    # static read-order map for a receiving agent
```

### `tests/` — ~20 pytest files
Bucket parity, secret scanning, P1 ingest (cursor/producer/reader/session-state), P2 scribe/notecreator,
P3 connector/evaluator/handoff/orchestrator, concurrent-write safety, watcher Arize spans, and end-to-end
integration (pipeline, handoff, secrets, session).

---

## Quickstart

### Prerequisites
| Tool | Min version | Used for |
|---|---|---|
| Python | 3.11 | pipeline + hooks |
| Node.js | 18 | webapp |
| Redis Stack | latest | Streams + pub/sub + RediSearch (Docker or local) |
| Git | any | pre-commit secret-scan hook |

### 1. Install
```bash
git clone <repo-url>
cd vault_mind
pip install -e .            # editable install of the vaultmind package
cd webapp && npm install && cd ..
```

### 2. Configure environment
Copy the example and fill in your keys:
```bash
cp .env.example .env
```
| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Scribe extraction, merge recommendations, eval judge |
| `ARIZE_SPACE_KEY` / `ARIZE_API_KEY` | ✅ | Arize LLM observability |
| `REDIS_URL` | – | Defaults to local Redis (`redis://localhost:6379`, or `6380` for the local Redis-Stack path) |
| `VAULTMIND_VAULT_ROOT` | – | Vault location; defaults to `<repo>/vault`. Point it at an Obsidian vault if you like. |
| `REPO_ROOT` | – | Repo root for the webapp's conflict resolver |
| `AGENT_SEED_PHRASE` / `AGENTVERSE_KEY` | – | Only needed to run/publish the Fetch.AI Orchestrator agent |

### 3. Start Redis Stack
VaultMind needs **Redis Stack** (plain Redis won't do — the Connector's vector index requires RediSearch).
Pick one:

```bash
# Option A — Docker (recommended; maps 6379 + RedisInsight UI on 8001)
docker compose up -d

# Option B — local Redis-Stack server (what scripts/start.sh expects, on port 6380)
redis-stack-server --port 6380 --daemonize yes
```
Set `REDIS_URL` to match (`redis://localhost:6379` for Docker, `redis://localhost:6380` for local).

### 4. Start everything
```bash
npm run vaultmind:start
```
Starts Redis Stack, the Python watcher (`python -m vaultmind.watcher`), and the Next.js dev server at
**http://localhost:3000** concurrently (`scripts/start.sh` on Unix, `scripts/start.ps1` on Windows). If
Redis is already running from step 3, the script detects it and skips re-launching.

To run the pieces by hand instead:
```bash
python -m vaultmind.watcher          # pipeline consumer loop
cd webapp && npm run dev             # web app on :3000
```

### 5. Wire the session hooks
Open **http://localhost:3000/setup** for a copy-paste wizard, or add directly:

**Claude Code** — `.claude/settings.json`
```json
{
  "hooks": {
    "Stop":       [{ "hooks": [{ "type": "command", "command": "python3 .vaultmind/hooks/on_stop.py", "async": true }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "python3 .vaultmind/hooks/on_session_end.py", "async": true }] }]
  }
}
```

**Codex** — `.codex/hooks.json` (Stop only)
```json
{ "hooks": { "Stop": [{ "hooks": [{ "type": "command", "command": "python3 .vaultmind/hooks/on_stop.py" }] }] } }
```

### 6. Use it
Start a Claude Code or Codex session — nodes appear live on the home page, the Graph view fills in, and the
Intent log records your decisions. Review conflicts on the Merge page and approve handoff when ready.

---

## Optional: the conversational Orchestrator agent

The Fetch.AI Orchestrator lets you query project state and trigger handoff in natural language — both from
the in-app chat and from **ASI:One**. It's optional; the pipeline and web app work without it.

### Run it locally (in-app chat)
Two processes power the in-app chat panel:
```bash
# 1. The Orchestrator uAgent (subscribes to Redis progress, answers intents)
python run_orchestrator.py

# 2. The Flask bridge the web app's /api/agent route proxies to (port 5002 ↔ uAgent 8002)
pip install -r webapp/requirements-bridge.txt
python webapp/agent_bridge.py
```
The `AgentChat` panel in the web app will now reach the agent.

### Publish it to Agentverse / ASI:One
The standalone agent lives in **`vault-mind-orchestrate/`** and is ASI:One-ready out of the box
(`mailbox=True`, `publish_agent_details=True`):
```bash
cd vault-mind-orchestrate
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make run            # starts on :8000, logs its address + Agentverse inspector URL
```
Connect the agent through the inspector URL it prints, then chat with it via ASI:One. Publishing requires
your own `AGENTVERSE_KEY` and `AGENT_SEED_PHRASE` (see `register_agents.py`) — these are account-owned
credentials and are never committed.

---

## Developer setup
```bash
pip install -e ".[dev]"                     # dev deps (pytest, fakeredis)
pytest                                       # run the suite
cd webapp && npm run dev                      # webapp in isolation

# manual secret scan on a node (exits 0, prints JSON array of matches; [] = clean)
python -m vaultmind.secrets vault/nodes/<node>.md
```

Install the pre-commit secret-scan hook (blocks commits containing secrets in `vault/`):
```bash
cp .vaultmind/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

---

## Invariants enforced by the codebase
- **Disk is the source of truth.** Redis events are triggers; the app re-reads files + `git status` on
  every event.
- **One `scanForSecrets`** (`vaultmind/secrets.py`). Write-time, commit-time, and handoff-time all use it.
  A detected secret blocks the write, the commit, **and** the handoff.
- **Node bodies are immutable after write.** The Note Creator wraps the Scribe's extraction verbatim; the
  Connector edits only `related` frontmatter — never the body.
- **No silent commits or handoffs.** Commits are manual; nothing leaves your machine without review.
- **`IntentLog.md` is the developer's own words.** Only Auto Mode may add an `ai-detected` entry, and it
  must be labeled.
- **Concurrent-write safety.** Appends to `IntentLog.md` / `SessionState.md` use atomic
  write-temp-rename + a `.lock` sentinel.

See **`SPEC.md`** for the full technical contracts and **`WORKSTREAMS.md`** for the build execution plan.
