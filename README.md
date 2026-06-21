# VaultMind

Persistent, structured project memory in Obsidian-compatible Markdown — transferable between LLM tools (Claude Code, Codex, Gemini) without late-stage summarization. A multi-agent pipeline writes a git-native vault as you work; a trust UI lets you review and hand off.

---

## Redis Stack — beyond caching

VaultMind uses **Redis Stack** as its single nervous system, leveraging Redis far beyond a cache:

| Feature | How VaultMind uses it |
|---|---|
| **Redis Streams** | `vaultmind:turns` — turn queue between the hook ingestion layer and the extraction pipeline (consumer group, ACK, idempotency) |
| **Redis Pub/Sub** | `vaultmind:events` — live node-changed events from the pipeline to the Next.js SSE endpoint; `vaultmind:progress` — per-turn stage progress to the Orchestrator |
| **RediSearch + RedisVL** | Vector index `vaultmind:nodes` — semantic similarity search over vault nodes using `all-MiniLM-L6-v2` embeddings (384-dim, cosine, FLAT index). The Connector uses this to find related nodes beyond title heuristics. |
| **RedisJSON** | Structured storage for node metadata |
| **RedisBloom** | Probabilistic deduplication of turns |

### Redis Stack modules loaded

```
search       — RediSearch 2.10  (vector search, FT.CREATE / FT.SEARCH)
ReJSON       — RedisJSON  2.x   (JSON.SET / JSON.GET)
bf           — RedisBloom 2.8   (BF.ADD / BF.EXISTS)
timeseries   — RedisTimeSeries  (pipeline metrics)
redisgears_2 — RedisGears 2.x   (event-driven processing)
```

### Vector search (RedisVL)

```python
from vaultmind.memory import VaultMemory

mem = VaultMemory()  # connects to REDIS_URL

# Index a node after it's written to disk
mem.upsert(node_id, title, body, node_type)

# Semantic search — used by the Connector to find related nodes
results = mem.search("database authentication decisions", k=5)
# → [MemoryResult(node_id=..., title=..., score=0.82), ...]
```

---

## Architecture

```
Claude/Codex transcript
        │
        ▼ (hook: on_stop / on_session_end)
vaultmind:turns  ◄─── Redis Stream
        │
        ▼ (watcher consumer group)
   Scribe (Anthropic)  →  Note Creator  →  vault/nodes/*.md
                                │
                                ▼ NodeWritten
                          Connector (heuristic + RedisVL vector search)
                                │
                                ▼ LinkResult
                         Orchestrator (Fetch.AI uAgent)
                                │
                         vaultmind:events  ◄─── Redis Pub/Sub
                                │
                                ▼ SSE
                         Next.js webapp (localhost:3000)
```

---

## Quick start

```bash
# 1. Start Redis Stack (RediSearch + RedisJSON + RedisBloom)
npm run vaultmind:start
# or manually:
~/redis-stack/redis-stack-server-7.4.0-v3/bin/redis-stack-server --port 6380 --daemonize yes

# 2. Activate virtualenv
source .venv/bin/activate

# 3. Source env vars
source .env

# 4. Start the pipeline watcher
python3 -m vaultmind.watcher

# 5. Start the web app
cd webapp && npm run dev
# → http://localhost:3000
```

### Push a test turn

```bash
source .venv/bin/activate && source .env
python3 - <<'EOF'
import json, redis, uuid
r = redis.from_url("redis://localhost:6380", decode_responses=True)
item = {
    "turn_id": str(uuid.uuid4()),
    "source_tool": "claude-code",
    "session_id": str(uuid.uuid4()),
    "transcript_path": "/path/to/vault_mind/fixtures/transcript.jsonl",
    "turn_text": {"user": "test", "assistant": "test response"},
    "enqueued_at": "2026-06-21T12:00:00Z"
}
r.xadd("vaultmind:turns", {"data": json.dumps(item)})
print("Queued.")
EOF
```

---

## Stack

- **Python pipeline** — FastAPI hooks, Pydantic v2 contracts, Anthropic Scribe
- **Redis Stack** — Streams + Pub/Sub + RediSearch (vector) + RedisJSON
- **RedisVL** — Python client for RediSearch vector index
- **Sentence Transformers** — `all-MiniLM-L6-v2` embeddings (offline, 384-dim)
- **Next.js 15** — TypeScript, Tailwind, App Router, SSE subscriber
- **Fetch.AI uAgents** — Orchestrator uAgent with ASI:One Chat Protocol
- **Arize** — LLM observability across the full pipeline

## Running tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```
