# Spec: VaultMind Technical Implementation

> Source of truth for the technical build. Product/architecture rationale lives in the
> proposal (`vaultmind_proposal.md` — PDF version, 20pp, the current one). This document
> does not re-argue the product; it pins the **byte-level contracts** four sessions build against.

---

## Goal

The proposal settled the product and architecture. What it left as prose — "the hook drops
turns into a lightweight queue," "finalize API contracts between the four agents," "define
the `.md` node schema" — is exactly what blocks four sessions from building in parallel without
colliding.

This spec's one job is **parallel-safe seams**: freeze every interface that crosses a
session-boundary (queue format, agent message contracts, node + file schemas,
`scanForSecrets` signature, hook configs, the live-event bus) into concrete shapes, so each
owner builds and tests in isolation against mocks and integrates around hour 10 with no
rework. Success = **nobody is ever blocked waiting on someone else's undecided interface**,
and the seams are *demonstrated* working (Bucket 5), not merely documented.

Everything off that path — per-session task clarity (→ `WORKSTREAMS.md`) and demo-path
hardening (→ the late buckets) — is downstream of frozen seams, not a substitute for them.

---

## User

Four parallel sessions against this repo — three Devin Cloud sessions (P1, P2, P3), one
dedicated Devin session for the foundation (Buckets 2–4), and one human Claude Code session
(P4). What each session needs from this spec:

- **Devin session — Foundation (Buckets 2–4).** Frozen contracts + fixtures, `scanForSecrets`,
  runtime skeleton. Reads `SPEC.md` in full; hard-stop per bucket with human review before the
  next begins. Bucket 5 (walking skeleton) is wired by this session and triggered live by the
  team — passing it triggers the P1–P3 Devin sessions.
- **Devin session P1 — Ingestion.** Hooks, transcript reading, queue production,
  `SessionState.md`, compaction/SessionEnd detection. Needs the `QueueItem` shape, the
  `SessionState.md` format, and the fixture transcript to build against.
- **Devin session P2 — Extraction & writing.** Scribe, Note Creator, IntentLog append,
  write-time scan. Needs the node schema, the `QueueItem`/`ScribeResult`/`NodeWritten`
  contracts, the IntentLog append contract, and `scanForSecrets`.
- **Devin session P3 — Linking & control plane / Fetch.AI.** Connector + Orchestrator uAgent
  (Agentverse, ASI:One, in-flight tracker) + handoff + Redis vector/memory. Needs the
  `NodeWritten`/`LinkResult`/`TurnProgress` contracts, the node + file schemas, the ASI:One
  intent definitions, and the fixture vault. **Heaviest, highest-stakes stream — owns the
  most-judged deliverable; task order front-loads the uAgent + ASI:One intents, with
  vector-search depth as the release valve if it slips (never the Agentverse publish).**
  Human carve-outs (require account credentials — never hand to Devin): Agentverse
  registration, ASI:One shared-chat URL, demo video.
- **Human Claude Code session — Web app (P4).** Needs the node schema, all four file formats,
  the `NodeChangedEvent` enum, the five display states, and a fixture vault + mock events.
  **Sole human-driven stream — no Devin session. Deliberate: Best UI/UX is a judged prize
  category that benefits from direct human taste.**

All Devin sessions follow: **hard-stop per bucket** (complete one bucket, post diff, halt until
human approves + merges, then proceed); **halt-on-ambiguity** (if a contract appears
underspecified or needs changing, stop and surface the question — never guess or invent an
interface); **stay-in-lane** (touch only your session's owned files, never edit
`contracts.py` / `types.ts` or another session's files). Per-session file ownership, mock
strategies, the blocking timeline (as checkpoints, not deadlines), and suggested task order
live in `WORKSTREAMS.md`.

---

## Acceptance Criteria

### AC-1 — Node schema (complete, with example)

Turn-nodes live at `vault/nodes/<YYYY-MM-DD-HHMM>-<slug>.md`; the basename **is** the
wikilink target. Frontmatter, with one complete example:

```markdown
---
id: 2026-06-21-1432-supabase-rls-policies   # == filename basename; stable [[link]] target
type: decision                               # decision | constraint | goal | question | scope
title: Use Supabase RLS for row-level auth   # short human label (Scribe-generated)
created: 2026-06-21T14:32:07-07:00           # ISO 8601 + tz; stamped by Note Creator at write
source_tool: claude-code                     # claude-code | codex
source_session: 00893aaf-19fa-41d2-8238      # session_id from the hook
intent_ref: 2026-06-21 14:32                 # IntentLog entry key current at write-time (copied)
status: approved                             # approved | pending   (review lifecycle ONLY)
related:                                      # [[wikilinks]] — CONNECTOR-OWNED, starts empty
  - "[[2026-06-21-1015-db-schema-users-table]]"
  - "[[Constraints]]"
flags: []                                     # e.g. [post-compaction], [secret-detected]
---
Decided to enforce per-row access with Supabase Row-Level Security rather than
checking ownership in app code, so the DB is the single source of truth for authz.

> "let's just do RLS so we don't re-check ownership in every endpoint"
```

- **`type` enum:** `decision | constraint | goal | question` for turn-nodes; `scope` is
  reserved for three seeded singleton anchors (`ProjectGoal.md`, `Constraints.md`,
  `TechStack.md`) at vault root, which rarely change.
- **`status` carries the review lifecycle ONLY** — `pending | approved`. Auto Mode writes
  `approved`; Review Mode writes `pending` until a checkpoint approves it. (See AC-7 for the
  derived display states.)
- **Load-bearing invariant:** the **Connector writes ONLY frontmatter `related`; it never
  touches the body.** The body is the Scribe's extraction, byte-for-byte immutable after the
  Note Creator writes it. This is the structural form of "no downstream LLM touches the
  Scribe's content."
- **Body is deliberately loose:** Scribe-authored markdown; convention is "one-line claim +
  optional grounding quote." The exact prose template is the Scribe owner's call, not locked.

### AC-2 — Vault layout + the three special files (finalized formats)

```
<repo>/vault/
  nodes/                 # turn-nodes: <YYYY-MM-DD-HHMM>-<slug>.md
  ProjectGoal.md  Constraints.md  TechStack.md   # scope anchors (type: scope), seeded at init
  IntentLog.md           # append-only, developer's intent over time
  VaultIndex.md          # static entry point / structure map
  SessionState.md        # deterministic session-event + compaction flags
```

**`IntentLog.md`** — append-only, newest on top, exactly one entry marked Current:

```markdown
# Session Intent Log

## 2026-06-21 14:32 — Current
"Help me finish the auth flow, I think the Supabase RLS policies are wrong"
— claude-code · developer

## 2026-06-21 10:15
"Get the database schema finalized before lunch"
— claude-code · developer

## 2026-06-20 22:40
"Just get the basic Next.js scaffold running"
— codex · ai-detected
```

- Stable key = the `YYYY-MM-DD HH:MM` heading; a node's `intent_ref` stores exactly that
  string. New entry **prepends**; the prior `— Current` is stripped; the new one gets it.
- Attribution line `— <tool> · <origin>`, where `origin ∈ developer | ai-detected`. This makes
  the Auto-Mode autonomous-write exception **auditable on the page**.

**`VaultIndex.md`** — static, written once at init, the receiving agent's first read:

```markdown
# Vault Index — <project>
Read order for a receiving agent:
1. ProjectGoal.md, Constraints.md, TechStack.md — standing project frame
2. Current entry in IntentLog.md (top, marked "Current") — what to do next
3. SessionState.md — context-degradation flags; check before trusting recent nodes
4. nodes/ — atomic decisions/constraints/goals/questions, linked via `related`

Conventions: links live in each node's `related:` frontmatter as `[[basename]]`;
`intent_ref` = the IntentLog entry key current when the node was written.
```

**`SessionState.md`** — deterministic, watcher-written, never inferred from content:

```markdown
# Session State
- 2026-06-21 14:05 · claude-code · ⚠ context compacted (trigger: auto, pre-tokens: 162k)
- 2026-06-21 14:32 · claude-code · session ended (reason: prompt_input_exit)
- 2026-06-20 22:10 · codex · session idle-timeout (inferred)
```

- Written from literal transcript fields (`subtype:"compact_boundary"` + `compactMetadata`;
  Claude Code `SessionEnd` `reason`). Nodes written shortly after a compaction get
  `flags: [post-compaction]`.
- **Review Mode's checkpoint consumes this file**: a checkpoint fires when the web app opens,
  when a `session ended` row appears, or on explicit "review now."

**Shared-write handling:** `IntentLog.md` (written by P2's `ai-detected` path *and* P4's
manual/handoff path) and `SessionState.md` use **one documented append contract** (prepend +
strip/set Current) executed as **write-temp-then-atomic-rename guarded by a `.lock`
sentinel**. Low-frequency, human-paced; the contract is named, not hoped for.

### AC-3 — Agent message contracts (finalized)

**Control-flow model:** the hot path `Scribe → Note Creator → Connector` runs **in-process in
the Python watcher** (direct calls, no per-turn network hops). **Only the Orchestrator is a
uAgent.** It is notified at every stage (not just the end), is the point-of-record + in-flight
tracker, and is the ASI:One face + handoff trigger.

**`QueueItem`** — Redis Stream `vaultmind:turns` (P1 writes → P2 reads); consumer group **`vaultmind-workers`** (created once by the watcher at startup — P1's producer must never create it):
```
turn_id          unique per turn (session_id + seq)
source_tool      claude-code | codex
session_id       from hook stdin
transcript_path  string | null            # null is possible on Codex
turn_text        {"user":"…","assistant":"…"}   # verbatim fresh turn
enqueued_at      ISO 8601
```
The hook puts the **verbatim turn text directly in the queue** — the Scribe never re-reads the
transcript, so Codex's possibly-null `transcript_path` is a P1-internal problem, not a seam
that breaks P2.

**`ScribeResult`** — Scribe → Note Creator (in-process); basis for the Orchestrator
"turn-started" notice:
```json
{
  "turn_id": "...", "source_tool": "claude-code", "source_session": "...",
  "extractions": [
    { "type": "decision", "title": "...", "slug": "...",
      "body": "<immutable, Scribe-authored markdown>" }
  ],
  "intent_shift": null
}
```
`extractions` is **0..n** (empty = nothing noteworthy, no node written). `intent_shift` is
**turn-level**; when non-null it routes by mode (Auto → append to IntentLog as `ai-detected`;
Review → surface as a suggestion).

**`NodeWritten`** — Note Creator → Connector (in-process, the P2↔P3 seam):
```json
{ "id": "2026-06-21-1432-supabase-rls-policies",
  "path": "vault/nodes/2026-06-21-1432-supabase-rls-policies.md",
  "type": "decision", "title": "...", "status": "approved",
  "flags": [], "intent_ref": "2026-06-21 14:32" }
```

**`LinkResult`** — Connector → Orchestrator (point of record):
```json
{ "id": "...", "related": ["[[...]]", "[[Constraints]]"],
  "status": "approved", "linked_at": "2026-06-21T14:32:09-07:00" }
```

**`NodeChangedEvent`** — Redis pub/sub `vaultmind:events` → web app, pushed to browser via SSE:
```json
{ "event": "created|linked|updated|deleted|secret-detected|intent-updated|session-event",
  "id": "...", "ts": "2026-06-21T14:32:09-07:00" }
```
Deliberately **minimal** — "something changed, here's the id." On receipt the web app
**re-reads the file from disk + reruns `git status`** (disk is source of truth), so the event
can never drift from disk. **`secret-detected` is a display-cache signal, not a block** — the
write succeeded; consumers must not infer write-failure or pipeline-`failed` from it.

**`TurnProgress`** — Redis pub/sub `vaultmind:progress` → Orchestrator (failure visibility):
```json
{ "turn_id": "...", "stage": "started|extracted|written|linked|done|failed",
  "node_ids": ["..."], "ts": "2026-06-21T14:32:09-07:00", "error": null }
```

**Orchestrator ↔ ASI:One** — natural language in/out via Chat Protocol. Contract = the
supported intents (see AC-8 for full worked examples):
- "what are we working on / project state?" → current IntentLog + scope anchors + N recent nodes
- "is the vault ready to hand off? / trigger handoff" → runs handoff-time `scanForSecrets` +
  pending-node check → `ready` or `blocked: <file>:<line>`
- "list open questions" → `type: question` nodes

### AC-4 — Failure visibility (who notices a mid-chain failure)

A Connector crash after the Note Creator writes must not leave a silently-orphaned node.

- **The watcher owns the ACK.** Reads each `QueueItem` via a Redis Stream **consumer group**,
  `XACK`s only after the *whole* chain succeeds. Crash before that → item stays in the Pending
  Entries List, reclaimed via `XAUTOCLAIM` on restart. Turns are never silently dropped.
- **The Orchestrator notices.** It consumes `TurnProgress` and keeps an in-flight table
  `{turn_id → last stage + ts}`. A turn at `written` but not `done` past a timeout is flagged
  **`stuck`** → Arize + project state.
- **Idempotent resume.** Per-turn marker `vaultmind:turn:<turn_id>` records `stage + node_ids`;
  redelivery resumes from the last completed stage (node id derives from the fixed
  `enqueued_at`, stable across retries). No duplicate nodes.
- **Disk is the backstop.** An orphan has `related: []` — visibly isolated in the graph; a
  startup reconciliation pass re-links any node with empty `related`.

#### AC-4b — End-to-end pipeline evaluator (Arize eval track)

**What it judges.** **One** LLM-as-judge evaluator runs after each complete turn (`done` stage)
and scores the **whole chain** end-to-end — extraction → linking → consistency — against the
original turn text and the resulting vault state. This is the proposal's "one evaluator that
watches the whole pipeline rather than three separate ones per call site." It scores on three
axes (extraction itself contributes two sub-scores):

| axis | stage judged | question | scale |
|---|---|---|---|
| **recall** | Scribe | Did the Scribe surface every noteworthy decision / constraint / goal / question a human reviewer would flag? | 0–1 float |
| **precision** | Scribe | Are the extracted nodes warranted by the turn text, or did the Scribe hallucinate / over-extract? | 0–1 float |
| **link_relevance** | Connector | Are the `related` wikilinks the Connector created actually warranted, or did it link unrelated nodes? | 0–1 float |
| **grounding** | downstream | Does the written node + its links stay consistent with what's actually in the vault, or did something drift from the source? (1 = fully grounded) | 0–1 float |

`extraction_quality` = harmonic mean of recall + precision (the Scribe sub-score). The headline
metric is **`pipeline_quality`** = harmonic mean of the three axes
(`extraction_quality`, `link_relevance`, `grounding`).

> **Connector is judged, not assumed-LLM.** The Connector ships heuristic-first (vector as the
> release valve — see Stack & Constraints / Out of Scope), so `link_relevance` scores the
> Connector's *output*, not an LLM
> call inside it. The evaluator measures link quality regardless of how the links were produced.

**Where the prompt lives.** `vaultmind/evals/pipeline_eval_prompt.md`, bundled inside the
`vaultmind` Python package (loaded via `importlib.resources`, same pattern as
`secret-patterns.json`). The prompt is the single source of truth — never inline a copy. It
receives, for the completed turn: the verbatim `turn_text` from the `QueueItem`; the list of
extracted `(type, title, body)` tuples from the `ScribeResult`; the `related` wikilinks from the
`LinkResult`; and the titles/bodies of the linked-to nodes (read from disk so `grounding` is
judged against real vault state, not a claim). It returns structured JSON:

```json
{
  "recall": 0.85,
  "precision": 1.0,
  "extraction_quality": 0.92,
  "link_relevance": 0.80,
  "grounding": 1.0,
  "pipeline_quality": 0.89,
  "missed": ["the constraint about not logging PII was present but not captured"],
  "spurious": [],
  "bad_links": []
}
```

`missed`, `spurious`, and `bad_links` are human-readable strings — they surface in Arize spans
and are the basis for prompt iteration, not downstream logic.

**How it wires into Arize.** The evaluator runs as a child span of the existing `turn` trace
(the same trace that carries stuck-detection flags). Scores are logged as span attributes:
`eval.recall`, `eval.precision`, `eval.extraction_quality`, `eval.link_relevance`,
`eval.grounding`, `eval.pipeline_quality`. The `missed` / `spurious` / `bad_links` lists are
logged as a JSON attribute `eval.detail`. This means every Arize turn trace already shows the
failure-visibility signals (AC-4) *and* the end-to-end pipeline-quality score in one view — no
separate dashboard.

**Before / after improvement deliverable.** The polish-hours checklist item is fulfilled by:
1. Running the evaluator against the **fixture vault** (Bucket 2) with the initial Scribe prompt
   and Connector linking logic → log baseline `pipeline_quality` (and the per-axis scores) to Arize.
2. After any iteration on the **live** Scribe prompt *or* Connector linking logic, re-running
   against the same fixture → Arize's trace comparison surfaces the delta on whichever axis moved.
3. The demo beat: show the Arize dashboard with at least two runs visible so judges can read the
   before/after `pipeline_quality` trend (and the axis that improved) without narration.

**"Iteration" means the live system, not a demo copy.** The Scribe's prompt and the Connector's
linking logic are what the production pipeline loads/runs at runtime (owners B and C own the exact
paths, but one file/one implementation each, no forks). The evaluator scores those; if an axis is
low, you edit that real artifact and re-run; the Arize delta reflects a real improvement to the
shipped system. A parallel "eval-only" copy is explicitly prohibited — it would make the
before/after comparison a rehearsed artifact rather than evidence, and judges can ask "is this what
it actually runs?"

**Constraints:**
- The evaluator is **read-only and fire-and-forget** — it never edits nodes or feeds back into
  the pipeline. A low score is an observability signal, not a retry trigger.
- It runs **after** `XACK` (the turn is already committed to disk); a slow judge never stalls
  the hot path.
- **One evaluator, one prompt file** watching the whole chain. Do **not** split it into per-agent
  sub-evaluators (one for the Scribe, one for the Connector) — the proposal's whole "one pass,
  covering the whole process" claim is the deliverable; the single turn-level `pipeline_quality`
  score with its per-axis breakdown is how that one evaluator stays end-to-end.
- **Model:** `claude-haiku-4-5-20251001` via the Anthropic Python SDK (`ANTHROPIC_API_KEY` from
  env). Fast and cheap for a fire-and-forget judge; switch to `claude-sonnet-4-6` only if
  haiku's recall scores prove insufficient after the baseline Arize run.

### AC-5 — `scanForSecrets` (signature + three call sites)

**One Python implementation, period.** (The Orchestrator already runs the handoff scan for
ASI:One, so a second TS copy would be a divergent implementation of a security control — a
secret caught at commit but missed at handoff. The web app calls the one Python impl by
shelling out: `python -m vaultmind.secrets <path>` → JSON on stdout.)

```python
def scan_for_secrets(content: str) -> list[SecretMatch]:
    """Empty list = clean. No LLM, no I/O beyond loading patterns once."""

# SecretMatch:
{ "pattern_id": "supabase-service-role-jwt",
  "description": "Supabase service_role JWT",
  "line": 12, "col": 16,
  "excerpt": 'service_key = "eyJ…[redacted]…"' }   # secret masked so the scanner never re-leaks it
```

Returns **matches, not a boolean** — every call site needs the detail. Patterns live in
`secret-patterns.json` **bundled inside the `vaultmind` Python package** (loaded via
`importlib.resources`, so it's cwd-independent and not casually editable from `vault/`).
`flags` is kept separate from `regex` so patterns stay a portable subset.

| call site | invoked by | scans | on match |
|---|---|---|---|
| **write-time** | Note Creator (Py, hot path) | the node being written | writes node anyway, sets `flags:[secret-detected]`, publishes `secret-detected` — **does not block** |
| **commit-time** | git pre-commit hook (Py) | staged `vault/` files (`git diff --cached`) | **blocks commit** (exit 1), prints `path:line  description` |
| **handoff-time** | web app (subprocess→Py) **and** Orchestrator ASI:One intent (Py) | all live `vault/` nodes | **blocks handoff**, returns `path:line  description`; vault never exposed |

- **Write-time flags, never blocks** — the node must land on disk so the developer can edit out
  the secret. The hard gates are commit + handoff; handoff fires even when no commit ever
  happened (Auto Mode).
- **Mode-independent.** Auto vs Review changes note review; it never changes this. A secret
  blocks commit + handoff in both modes.
- **Display vs gate:** display uses the maintained `flags` cache (fast); gates run a **live**
  re-scan (authoritative). Every web-app edit-save re-scans that one node and updates the flag.
- **CLI contract:** `python -m vaultmind.secrets <path>` always exits **0** (clean or matches)
  and prints a JSON array to stdout (`[]` for no matches). The pre-commit hook reads the JSON and
  exits **1** itself if the list is non-empty — the hook, not the CLI, is the git gate. The web
  app reads the JSON directly (not the exit code). Never change this to exit 1 on match — callers
  depend on the always-0 contract.

### AC-6 — Hook configs (finalized) + the session-end resolution

`.claude/settings.json`:
```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 .vaultmind/hooks/on_stop.py", "async": true } ] }
    ],
    "SessionEnd": [
      { "hooks": [ { "type": "command", "command": "python3 .vaultmind/hooks/on_session_end.py", "async": true } ] }
    ]
  }
}
```

`.codex/hooks.json`:
```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 .vaultmind/hooks/on_stop.py" } ] }
    ]
  }
}
```

**Session-end signal — resolved by reading both official hook references (not assumed):**

| | Claude Code | Codex |
|---|---|---|
| `Stop` (per turn) | yes | yes |
| `SessionEnd` (distinct) | **yes** — `reason ∈ clear,logout,prompt_input_exit,resume,bypass_permissions_disabled,other`; side-effect only | **no** — only `Stop` at turn scope |
| async hooks | **yes** (`async:true`, `timeout`) | **no** — parsed but all hooks block |
| stdin `transcript_path` | always present | may be **null**; also gives `turn_id` |

**Consequence (the spec states the asymmetry plainly):** Review Mode's "session ended"
checkpoint uses the real `SessionEnd` hook on Claude Code; on Codex there is no such hook, so
it falls back to the watcher's **idle-timeout heuristic** (no new `Stop` within **300 seconds
(5 minutes)** → `session idle-timeout (inferred)` in `SessionState.md`) or the other two checkpoints
(web-app-open / explicit). Codex hooks can't run async and may hand a null `transcript_path`,
so `on_stop.py` must stay minimal and produce `turn_text` regardless. *(Sources:
code.claude.com/docs/en/hooks; developers.openai.com/codex/hooks. Re-confirm at build — Codex
hooks are evolving. Codex also requires the project `.codex/` layer to be trusted.)*

### AC-7 — Node display states (five; what the web app builds against)

Frontmatter persists **only** `status: pending | approved` (review lifecycle). The web app
**derives** the rendered state live, with this precedence (most urgent wins):

| display state | source of truth | blocks? | UI |
|---|---|---|---|
| `conflicted` | git conflict markers in file | commit + handoff | red, side-by-side picker |
| `blocked` | **live** `scanForSecrets` match | commit + handoff | red, "secret at `<file>:<line>`" |
| `awaiting-review` | frontmatter `status: pending` | handoff (until approved) | amber, approve/edit |
| `uncommitted` | `git status` differs from HEAD | nothing (commit is manual) | blue dot |
| `clean` | `approved` + committed + scan-clean | — | green |

(Renamed from the proposal's "pending" — we now have two independent reasons a node isn't
done: `awaiting-review` vs `uncommitted`. Conflating them would mislead the web app owner.)

### AC-8 — Worked ASI:One intents (Fetch.AI track has direct judging weight)

**A — project state.** *"What's the current state of this project?"*
```
TaskFlow — current focus (since 2026-06-21 14:32):
  "Help me finish the auth flow, I think the Supabase RLS policies are wrong"
Standing frame:
  • Goal: multi-tenant task app, email auth, ship MVP this week   (ProjectGoal.md)
  • Stack: Next.js + Supabase Postgres + Redis                    (TechStack.md)
  • Constraints: RLS is the authz source of truth; no PII in logs (Constraints.md)
Recent nodes (3 of 14):
  1. [decision]  Use Supabase RLS for row-level auth          — 14:32
  2. [decision]  Users table: id, email, org_id, created_at   — 10:15
  3. [question]  Should org-switch invalidate sessions?       — 09:50
⚠ Context compacted at 14:05 (claude-code); 2 nodes after it are flagged for review.
```

**B — handoff readiness (blocked case is the demo beat).** *"Is the vault ready to hand off?"*
```
Not ready — handoff is BLOCKED.
🔴 Secret detected (scanned just now):
   vault/nodes/2026-06-21-1408-supabase-keys.md:12   pattern: "supabase service_role JWT"
🟠 2 nodes still awaiting review (Review Mode).
I will not expose the vault to a receiving agent while a secret is present.
Fix the flagged node in the web app, then ask again.
```
…then, once fixed, *"trigger handoff"*:
```
Ready ✅  — 14 nodes, all approved, scan clean.
Carry-forward intent: "Help me finish the auth flow…" (2026-06-21 14:32) — still current? (yes/no)
Receiving agent: read VaultIndex.md → current IntentLog entry → nodes/.
Vault marked available at 14:36.
```

**C — open questions.** *"What are the open questions?"*
```
3 open questions:
  1. Should org-switching invalidate active sessions?   — 09:50, under current intent
  2. Soft-delete tasks, or hard-delete?                 — 06-20 21:10
  3. Rate-limit strategy for the public API            — 06-20 18:40, not under current intent
Each is a type:question node in nodes/.
```

### AC-9 — `CLAUDE.md` exists and points, not duplicates

A short `CLAUDE.md` that points to `SPEC.md` and `WORKSTREAMS.md` (no duplicated content) plus
the project-wide standing rules that apply regardless of who's working — at minimum:
- Never let any downstream LLM call (Note Creator, Connector) touch content the Scribe
  extracted. The Connector edits only frontmatter `related`.
- Always run `scanForSecrets` before any disk write (write-time), commit (pre-commit hook), and
  handoff (handoff trigger).
- Disk is the source of truth; events are minimal triggers to re-read disk.
- `IntentLog.md` defaults to the developer's own words; only Auto Mode may write `ai-detected`,
  and it must be labeled.

---

## Out of Scope

- **Stretch handoff targets:** Devin REST-API integration.
- **Dynamic `VaultIndex.md`** (BFS "most-relevant-now" traversal) — the static map ships; the
  dynamic variant is stretch only.
- **Vector-search depth/tuning** beyond basic Redis vector retrieval — the Connector ships on
  heuristic linking; vector quality is the late-polish release valve.
- **Team / merge-conflict polish** beyond the side-by-side picker on standard git markers.
- **Project-level additive secret-pattern override** (`vault/.secret-patterns.json`) — noted as
  a future option; base patterns ship bundled.
- **Auto-commit** — VaultMind never commits on the developer's behalf; commits stay manual.
- **Locking the Scribe's prompt or body-prose template** — that's the Scribe owner's call; the
  spec locks the I/O contract, not the wording.
- **Building the four streams themselves** — these buckets deliver the shared foundation + docs;
  the streams are the sessions' work, guided by `WORKSTREAMS.md`.

---

## Stack & Constraints

**Non-negotiable (sponsor-mandated / project premise):**
- **Redis** — vector search / agent memory. Also serves as the queue (Streams), the event bus
  (pub/sub `vaultmind:events`), and the progress bus (`vaultmind:progress`). One dependency,
  one nervous system.
- **Fetch.AI uAgents + Agentverse + ASI:One** — the **Orchestrator** is a real, published
  uAgent with the Chat Protocol, discoverable/usable via ASI:One. (uAgent built locally from
  hour 0; Agentverse publish is the late-but-mandatory deliverable.)
- **Arize** — LLM observability wired across the whole pipeline and the web-app server, plus the
  one end-to-end evaluator (AC-4b). The genuine **LLM calls** — the Scribe's extraction, the
  Orchestrator's ASI:One replies, and the evaluator's own judge call — are traced as LLM spans;
  the deterministic/heuristic steps (Note Creator write, Connector linking, hooks) are traced as
  plain spans whose *output* the evaluator scores. Cross-cutting, not a separate stream.

  **Frozen Arize naming — all sessions must match exactly or the dashboard fragments:**

  | key | value |
  |---|---|
  | env vars | `ARIZE_SPACE_KEY`, `ARIZE_API_KEY` |
  | Arize project name | `vaultmind` |
  | service: P1 | `vaultmind-ingest` |
  | service: P2 + P3 (watcher process) | `vaultmind-pipeline` |
  | service: P4 (Next.js server routes) | `vaultmind-webapp` |
  | root span name (per turn) | `turn` (attribute: `turn_id`) |
  | evaluator child span | `turn.eval` |
  | evaluator score attributes | `eval.recall`, `eval.precision`, `eval.extraction_quality`, `eval.link_relevance`, `eval.grounding`, `eval.pipeline_quality`, `eval.detail` |

  The Arize init wrapper (Bucket 4) exports a single `init_arize(service_name: str)` function;
  each session calls it with the service name from the table above. Never invent a different
  name — the Arize UI correlates spans across streams by these keys.
- **Claude Code + Codex** — the two tracked surfaces, via their `Stop`/`SessionEnd` hooks.

**Open — recommended and adopted:**
- **Two runtimes, one seam line.** Whole pipeline + hooks + Orchestrator = **Python**; web app =
  **TypeScript / Next.js full-stack** (App Router route handlers + SSE; no separate Express).
  The only cross-language seams are `vault/*.md` on disk and Redis.
- **Queue = Redis Streams** (consumer groups + ACK + replay), not a bare list.
- **Live updates = Redis pub/sub → SSE** (fallback: web app watches `vault/` via chokidar).
- **`scanForSecrets` = single Python implementation**; web app shells out for the handoff scan.
- Graph viz: `react-force-graph`.

---

## Task Breakdown

These five buckets establish the shared foundation before the four streams begin. Bucket 1
(this doc set) is already done. **Buckets 2–4 are executed by a dedicated Devin session** —
same hard-stop-per-bucket rules as P1–P3, human review required before each next bucket begins.
**Bucket 5 is Devin-wired but human-witnessed** — the full team observes the live fire together,
and passing it is the single gate that triggers the P1–P3 Devin sessions. The four streams
follow afterward, per `WORKSTREAMS.md`.

- **Bucket 1 — Project docs.** `WORKSTREAMS.md` + `CLAUDE.md`, and commit `SPEC.md` alongside.
  All three files land here. `CLAUDE.md` stays short (points to the other two + the standing
  rules in AC-9, no duplication).

- **Bucket 2 — Frozen contracts + fixtures.** Repo + `vaultmind`-package skeleton;
  `contracts.py` (**Pydantic v2 `BaseModel`** for all six message shapes) + mirrored `types.ts`
  (identical field names and types); the four file templates (scope nodes, VaultIndex,
  IntentLog, SessionState); and the **fixture transcript + fixture vault** every stream mocks
  against. *This is the bucket that freezes the seams.*

  **`fixtures/transcript.jsonl` — required content (one `QueueItem` JSON per line):**
  - Turn 1: yields a `decision` node (Supabase RLS policy choice — use the AC-8 example verbatim)
  - Turn 2: yields a `constraint` node (no PII in logs)
  - Turn 3: yields a `question` node (should org-switch invalidate sessions? — AC-8 example)
  - Turn 4: contains a literal Supabase service-role JWT string — the seeded demo secret for
    the Intent-B handoff-blocked demo beat (Bucket 3 adds this; Bucket 2 reserves the slot
    with a `TODO: seed secret here` comment in the file)

  **`fixtures/vault/` — required content:**
  - One node of each `type`: decision, constraint, goal, question (use AC-8 names/dates verbatim
    so AC-8's worked examples run against the fixture without modification)
  - The three scope anchors: `ProjectGoal.md`, `Constraints.md`, `TechStack.md` (populated with
    the AC-8 standing-frame content)
  - `IntentLog.md` with at least two entries (AC-8 current + one prior)
  - One node with `flags: [secret-detected]` (the Supabase-keys node from AC-8 Intent-B) — body
    contains a masked placeholder; Bucket 3 replaces it with the seeded real pattern

- **Bucket 3 — `scanForSecrets` + git hook.** Python util + `secret-patterns.json` + the
  `python -m vaultmind.secrets` entrypoint + the pre-commit hook + tests for all three
  call-site behaviors + one seeded demo secret for the ASI:One Intent-B beat.

- **Bucket 4 — Runtime skeleton.** Redis (docker-compose); the two hook configs; the
  watcher-loop skeleton (consumer-group + ACK + idempotency + `TurnProgress`, with stubbed
  plug-in points for Scribe/NoteCreator/Connector); the Arize init wrapper;
  `npm run vaultmind:start`. **This single command starts exactly three processes concurrently:**
  (1) `docker compose up -d` (Redis — idempotent if already running), (2) `python -m
  vaultmind.watcher` (the pipeline consumer loop, creates `vaultmind-workers` consumer group at
  startup), and (3) `next dev` (the web app on port **3000**). All three must be running before
  Bucket 5's live-fire test begins.

- **Bucket 5 — Walking skeleton (seam proof).** Stubs wired end-to-end so the seams are
  *demonstrated* parallel-safe before any owner commits real hours.

  **Definition of done (the gate — observed live, together, in one sitting):** with
  `npm run vaultmind:start` running, the fixture transcript is fed in (real `Stop` hook against
  a fixture session, or the producer replaying it), and the team watches **all of the following
  fire for a single turn, ending with the browser's minimal view appending a stub node with no
  manual refresh:**
    1. fixture turn → real `QueueItem` in `vaultmind:turns` (verify via `XRANGE`)
    2. watcher consumes via consumer group and `XACK`s (verify `XPENDING` drains)
    3. stub Scribe → Note Creator writes a real `vault/nodes/*.md` that parses against AC-1
    4. Note Creator → stub Connector populates `related`
    5. Connector publishes `node-changed` on `vaultmind:events`
    6. web app SSE delivers it → **minimal view updates live, no refresh**
    7. Orchestrator's in-flight table shows the turn reaching `done` via `TurnProgress`

  **Secondary (proves the AC-4 failure-visibility seam, cheap):** kill the stub Connector after
  step 3 → confirm the `QueueItem` stays in `XPENDING` (not lost) and the Orchestrator flags the
  turn `stuck` after the timeout.

  **Explicitly not required here:** real Scribe/Connector logic, the real graph UI, vector
  search, Agentverse publish — those are stream work. Each owner replaces their stub.

  Why interpretation-1 (live fire), not independent shape-checks: independent shape confirmation
  cannot catch a wiring bug (e.g., a misconfigured SSE subscription) — it goes green while real
  integration still fails at hour 11. The bucket exists to test the live wiring, so the gate is
  the live fire.
