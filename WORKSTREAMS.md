# WORKSTREAMS — VaultMind

How to read this: `SPEC.md` is the contract (schemas, the six message shapes, `scanForSecrets`,
hook configs). This file is **who runs what session, what each can build in isolation, when each
seam goes live, and the order to work in.** When in doubt about a shape, SPEC.md wins.

Paths are relative to the tool repo root (`/home/tim/vault_mind`, which *is* `vaultmind-cli`;
it installs into a user's project as `.vaultmind/`). The exact tree is finalized in Bucket 2;
the package is `vaultmind/`, the web app is `webapp/`, shared fixtures live in `fixtures/`.

**Foundations-first gate.** No stream session starts until Buckets 2–5 land. Buckets 2–4 are
executed by a dedicated Devin session (hard-stop per bucket, human review at each boundary).
Bucket 5 is Devin-wired and human-witnessed — the team runs the live fire together; passing it
triggers the P1–P3 Devin sessions. The frozen contracts (`vaultmind/contracts.py` +
`webapp/types.ts`), `scanForSecrets`, the runtime skeleton, and the **fixture transcript
(`fixtures/transcript.jsonl`) and fixture vault (`fixtures/vault/`)** are what every stream
session mocks against.

---

## Devin Session — Foundation (Buckets 2–4)

Executes the shared foundation before any stream begins. Same hard-stop-per-bucket rules as
P1–P3: complete one bucket, post the diff, wait for human review and merge, then proceed.

- **Bucket 2:** repo + `vaultmind`-package skeleton; `contracts.py` + mirrored `types.ts`; the
  four file templates; fixture transcript + fixture vault every stream mocks against.
- **Bucket 3:** `scanForSecrets` Python util + `secret-patterns.json` + pre-commit hook + tests
  for all three call-site behaviors + seeded demo secret.
- **Bucket 4:** Redis docker-compose; hook configs; watcher-loop skeleton (consumer-group + ACK
  + idempotency + `TurnProgress`, stubbed plug-in points); Arize init; `npm run vaultmind:start`.
- **Bucket 5 (wired by this session, witnessed by the team):** wire stubs end-to-end per the DoD
  in `SPEC.md`. The team runs the live fire together; passing it triggers the P1–P3 sessions.

**Devin execution rules:** halt-on-ambiguity (if any contract is underspecified or appears to
need changing, stop and surface the question — never guess); stay-in-lane (once P1–P3 begin,
this session is done — do not modify stream files).

---

## Devin Session P1 — Ingestion

Gets raw turns flowing. Front-loaded; mostly stable once turns flow.

- **Owns:** `vaultmind/hooks/on_stop.py`, `on_session_end.py`; `vaultmind/ingest/` (incremental
  transcript reader, per-session cursor, `QueueItem` producer → Redis Stream `vaultmind:turns`,
  `SessionState.md` writer incl. `compact_boundary` + `SessionEnd` detection + the Codex
  idle-timeout heuristic); the hook config templates (`.claude/settings.json`,
  `.codex/hooks.json` — SPEC.md AC-6).
- **Build in isolation:** replay `fixtures/transcript.jsonl` → emit `QueueItem`s into local
  Redis; assert shape + `SessionState.md` rows. Needs only Redis. **No other stream required.**
- **Depends on (in):** foundation (`QueueItem` shape, SessionState format, watcher skeleton,
  Redis). **Produces (out):** `QueueItem` → P2; `SessionState.md` → P4.
- **Goes live:** P2's watcher consumes P1's first real `QueueItem` at the **hour-8 pace check**.
- **Order:** ① hook configs + `on_stop` reading the fixture → print a `QueueItem`; ② Redis
  producer + cursor; ③ `on_session_end` → SessionState; ④ `compact_boundary` detection;
  ⑤ Codex null-`transcript_path` + idle-timeout heuristic (per AC-6 asymmetry).

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity; stay-in-lane (owns only
`vaultmind/hooks/` and `vaultmind/ingest/`).

---

## Devin Session P2 — Extraction & writing

- **Owns:** `vaultmind/scribe/` (Anthropic → `ScribeResult`, incl. turn-level `intent_shift`);
  `vaultmind/notecreator/` (write node, stamp `created`/`intent_ref`/`status`, **write-time
  `scanForSecrets`**, → `NodeWritten`; `IntentLog.md` append — `ai-detected` path); node-schema
  read/write helpers.
- **Build in isolation:** hand-written `fixtures/queue_item.json` + `fixtures/scribe_result.json`
  → assert node files parse against AC-1 and `NodeWritten` matches. Only the live Scribe needs
  `ANTHROPIC_API_KEY`; everything else offline.
- **Depends on (in):** foundation (node schema, contracts, `scanForSecrets`, watcher skeleton);
  `QueueItem` from P1 (mock until hr 8). **Produces (out):** `NodeWritten` → P3's Connector; node
  files + `IntentLog.md` → P4.
- **Goes live:** consumes P1's real `QueueItem`s ~hr 8; hands `NodeWritten` to P3 ~hr 10.
- **Order:** ① node writer against the `scribe_result` fixture; ② Scribe extraction against the
  `queue_item` fixture; ③ `IntentLog` append (`ai-detected`) via the atomic-rename + lock;
  ④ wire write-time `scanForSecrets`; ⑤ plug Scribe + Note Creator into the watcher skeleton.

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity; stay-in-lane (owns only
`vaultmind/scribe/` and `vaultmind/notecreator/`).

---

## Devin Session P3 — Linking & control plane / Fetch.AI

**Heaviest, highest-stakes stream — owns the most-judged deliverable (the ASI:One demo).**
Task order is deliberate: the judged uAgent + intents come first; vector depth is the release
valve if time runs short; the Agentverse publish is late but **mandatory** and never cut.

- **Owns:** `vaultmind/connector/` (`NodeWritten` → `related` → publish `node-changed`/`linked`
  → `LinkResult`; orphan reconciliation); `vaultmind/orchestrator/` (uAgent: Agentverse
  registration, Chat Protocol, the 3 ASI:One intents, `TurnProgress` consumer + in-flight
  timeout, point-of-record); `vaultmind/handoff/` (handoff trigger + **handoff-time
  `scanForSecrets`** + entry-point assembly: `VaultIndex` pointer + current intent);
  `vaultmind/memory/` (Redis vector index + query interface).
- **Build in isolation:** Connector against `fixtures/vault/` (heuristic linking first, vector
  later); intents against `fixtures/vault/`; mock `TurnProgress`; uAgent runs locally (uagents
  bureau) before any Agentverse publish.
- **Depends on (in):** foundation (contracts, node + file schemas, fixture vault); `NodeWritten`
  from P2 (mock until hr 10). **The Connector→vector dependency on P3's own index is
  non-blocking** (heuristic fallback). **Produces (out):** `LinkResult` + events → P4; ASI:One →
  judges.
- **Goes live:** consumes P2's real `NodeWritten` ~hr 10.
- **Order:** ① uAgent skeleton + Chat Protocol echo (local); ② **the 3 ASI:One intents against
  the fixture vault — the judged core, front-loaded** (SPEC AC-8); ③ Connector heuristic linking
  + event publish + reconciliation; ④ `TurnProgress` consumer + in-flight timeout (AC-4);
  ⑤ handoff trigger + handoff scan + entry-point assembly; ⑥ (**human carve-out**) Agentverse
  registration + ASI:One shared chat + demo video — Devin wires the uAgent code; humans handle
  account registration, the shared-chat session, and recording; ⑦ Redis vector search
  (**release valve** — cut depth if behind; heuristic linking already ships).

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity; stay-in-lane (owns only
`vaultmind/connector/`, `vaultmind/orchestrator/`, `vaultmind/handoff/`, `vaultmind/memory/`).
**Human carve-outs (never hand to Devin):** Agentverse registration, ASI:One shared-chat URL,
demo video — these require account credentials and an interactive session.

---

## Human Session P4 — Web app (no Devin)

**Least blocked, longest runway** — build against the fixture vault + mock events from hour 0.
**No Devin session for this stream.** UI/UX is a judged general-prize category (Best UI/UX)
that benefits from direct human taste and iteration.

- **Owns:** `webapp/` — Next.js full-stack: graph viz (`react-force-graph`); the **five display
  states** (git status + `flags` + live scan at gates, SPEC AC-7); staging/confirm editing →
  disk; **Auto/Review modes** + pending batch + checkpoints (consume SessionState session-end /
  web-open / explicit); handoff **confirm-or-replace** prompt + "Update intent" button (→
  `IntentLog`, manual path); SSE subscriber to `vaultmind:events`; merge-conflict side-by-side
  UI. Keeps `webapp/types.ts` in sync with `vaultmind/contracts.py`.
- **Build in isolation:** `fixtures/vault/` + mock pub/sub events from hour 0.
- **Depends on (in):** foundation (node schema, the four file formats, `NodeChangedEvent` enum);
  live events/disk from the pipeline ~hr 10–12. Shares the `IntentLog` append contract with P2.
- **Order:** ① render the fixture vault graph; ② five-state indicators (git status + flags);
  ③ SSE from mock events → live append; ④ staging/confirm editing → disk (atomic write);
  ⑤ Auto/Review modes + pending batch + checkpoints; ⑥ handoff confirm-or-replace + Update intent
  button; ⑦ merge-conflict UI (polish).

---

## Blocking timeline — checkpoints, NOT deadlines

These hours are **pace anchors to verify against, not commitments.** The failure mode isn't
being an hour late — it's not noticing you're behind until hour 14. So hour 8 is a *scheduled
beat*, not a number nobody looks at.

- **Hr 0–~3:** foundation Devin session runs Buckets 2–4 (hard-stop per bucket, human review at
  each boundary), then wires Bucket 5; team witnesses Bucket 5 live fire and triggers P1–P3
  sessions. P4 human session can begin building against fixtures from Bucket 2 onward.
- **Hr ~8 — PACE CHECK (everyone present).** Each session (a) demos its stream against fixtures
  AND (b) does its first *live* handshake with its neighbor: P1's producer → P2's watcher
  consumes one real `QueueItem`; P4 subscribes to one real `node-changed` event. Also check ACU
  burn across P1–P3 — surface any slip here.
- **Hr ~10 — integration.** P2→P3 `NodeWritten` live; P3 publishes real `LinkResult`/events; P4
  renders real pipeline output.
- **Hr 10–16 — full end-to-end** on a real Claude Code session; git-status indicators update;
  SessionState compaction/session-end flags appear.
- **Hr 16–20 — demo-path hardening.** The proposal's happy path, updated for Auto/Review modes:
  start session → node appears live → second node + link → (mode-appropriate) handoff → secret
  block beat → receiving agent reads the vault. Also drive it through the ASI:One conversation
  (Intent A → B-blocked → fix → B-ready → C).
- **Hr 20–24 — polish / sponsor deliverables.** Agentverse publish + ASI:One shared chat URL +
  Agentverse profile URL + dedicated demo video (P3 code done by Devin; registration + recording
  are **human-owned, mandatory**); Arize dashboards; vector
  depth (release valve); merge-conflict polish; pitch deck. Out-of-scope items (Devin,
  dynamic VaultIndex) only if everything else is done.

---

## Cross-cutting (everyone, not a fifth stream)

- **Arize** — wire LLM observability across your own failure points as you build: P1 (hook/queue
  errors), P2 (extraction/write), P3 (connector/uAgent/handoff), P4 (server routes). Dashboards
  are hr 20–24.
- **`scanForSecrets` is never skipped** — write-time before any disk write (P2), commit-time
  (pre-commit hook), handoff-time before exposing the vault (P3, and the web app via subprocess).
  One Python implementation; never add a second (SPEC AC-5).
- **Content invariant** — the Connector edits **only** frontmatter `related`, never the body
  (enforce in P3; add a test asserting the body is byte-identical before/after linking).
- **Concurrent-write test (build-time requirement).** `IntentLog.md` has two writers (P2's
  `ai-detected`, P4's manual/handoff) and `SessionState.md` is watcher-written + P4-read. **P2
  and P4 must jointly satisfy a test:** two simultaneous appends to `IntentLog.md` do not
  clobber — the write-temp-then-atomic-rename + `.lock` sentinel holds, and exactly one entry
  ends marked `— Current`. This is the one mechanism spanning a Devin stream (P2) and the human
  stream (P4); no stream is "done" until this test passes.
