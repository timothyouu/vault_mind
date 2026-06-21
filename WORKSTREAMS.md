# WORKSTREAMS — VaultMind

How to read this: `SPEC.md` is the contract (schemas, the six message shapes, `scanForSecrets`,
hook configs). This file is **who runs what session, what each can build in isolation, when each
seam goes live, and the order to work in.** When in doubt about a shape, `SPEC.md` wins.

Paths are relative to the tool repo root (the `vault_mind` repo; it installs into a user's
project as `.vaultmind/`). The exact tree is finalized in Bucket 2; the package is `vaultmind/`,
the web app is `webapp/`, shared fixtures live in `fixtures/`.

**Execution model.** Devin Cloud sessions execute foundation Buckets 2–4 and streams P1–P3;
one human Claude Code session executes P4 only. All Devin sessions follow **hard-stop per
bucket** (complete one bucket, post diff, halt until a human approves + merges via Devin Review,
then proceed), **halt-on-ambiguity** (stop and surface any underspecified contract — never
guess), and **stay-in-lane** (touch only your session's owned files). ACU allocation and the
bucket-approval protocol are in `SPEC.md` §Execution Model; the ACU table is repeated at the
end of this file for quick reference.

**Foundations-first gate.** No stream session starts until Buckets 2–5 land. This is the gate
that **triggers the P1–P3 Devin sessions and commits their ACU budget** — sessions are not
started before passing it, and the team witnesses the live fire together. Buckets 2–4 are
executed by a dedicated Devin session (hard-stop per bucket, human review at each boundary).
Bucket 5 is Devin-wired and human-witnessed: the team runs the live fire together; passing it
(both pre-flight deterministic checks clean + all seven live-fire steps fired) is the trigger.
The frozen contracts (`vaultmind/contracts.py` + `webapp/types.ts`), `scanForSecrets`, the
runtime skeleton, and the **fixture transcript (`fixtures/transcript.jsonl`) and fixture vault
(`fixtures/vault/`)** are what every stream session mocks against.

**Direct-execution discretion.** P1–P3 stream owners may choose to execute one or more of
their buckets directly (in a local or human-supervised Claude Code session) rather than
delegating them to a Devin session — for example, to conserve ACUs when a bucket is small or
when a human is faster. The same bucket-approval rules (hard-stop, human review, merge before
next) apply regardless of executor. A bucket completed directly does not draw from the ACU
pool.

---

## Devin Session — Foundation (Buckets 2–4)

Executes the shared foundation before any stream begins. Same hard-stop-per-bucket rules as
P1–P3: complete one bucket, post the diff, wait for human review and merge, then proceed.
**ACU soft-cap: ~15 ACUs (~19 total allocation); alert the human reviewer at ~15 ACUs.**

- **Bucket 2:** repo + `vaultmind`-package skeleton; `contracts.py` + mirrored `types.ts`; the
  four file templates; fixture transcript + fixture vault every stream mocks against.
  *Bucket-2 AC:* `contracts.py` imports cleanly (Pydantic v2); `types.ts` compiles clean
  (`tsc --noEmit`); all fixture nodes in `fixtures/vault/` parse against AC-1; the fixture
  transcript has at least the four turns specified in `SPEC.md` §Task Breakdown.
- **Bucket 3:** `scanForSecrets` Python util + `secret-patterns.json` + pre-commit hook + tests
  for all three call-site behaviors + seeded demo secret.
  *Bucket-3 AC:* `python -m pytest tests/` passes; `python -m vaultmind.secrets
  fixtures/vault/nodes/<secret-node>.md` returns non-empty JSON; pre-commit hook exits 1 on
  the seeded secret file.
- **Bucket 4:** Redis docker-compose; hook configs; watcher-loop skeleton (consumer-group + ACK
  + idempotency + `TurnProgress`, stubbed plug-in points); Arize init; `npm run vaultmind:start`.
  *Bucket-4 AC:* `npm run vaultmind:start` starts all three processes cleanly; Redis responds
  to `PING`; `python -m vaultmind.watcher` creates the consumer group and loops without error;
  `next dev` serves on port 3000.
- **Bucket 5 (wired by this session, witnessed by the team):** wire stubs end-to-end per the DoD
  in `SPEC.md`. Run the two pre-flight checks first (contract-parity + fixture-parse). The team
  runs the live fire together; passing it triggers the P1–P3 sessions.
  *Bucket-5 AC:* both pre-flight checks exit 0; all seven live-fire steps fire cleanly in one
  sitting; secondary failure-visibility check confirms `XPENDING` retention + `stuck` flag.

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity (if any contract is
underspecified or appears to need changing, stop and surface the question — never guess);
stay-in-lane (once P1–P3 begin, this session is done — do not modify stream files);
no account/publish credentials (Agentverse, ASI:One, demo video are human-owned); ACU-awareness
(alert at ~15 ACUs; await human approval before drawing from the shared reserve).

---

## Devin Session P1 — Ingestion

Gets raw turns flowing. Front-loaded; mostly stable once turns flow.
**ACU soft-cap: ~36 ACUs (~45 total allocation); alert at ~36.**

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

**Per-bucket AC (applied at Devin Review):**
- Bucket passes when: replay of `fixtures/transcript.jsonl` produces `QueueItem`s whose shape
  matches `contracts.py` exactly (the contract-parity check passes); `SessionState.md` has the
  correct rows; `XPENDING` drains after consume; tests in `tests/` pass.
- Each bucket diff is reviewed by the stream owner via Devin Review before the next begins.

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity (stop and surface any
underspecified contract — never guess); stay-in-lane (owns only `vaultmind/hooks/` and
`vaultmind/ingest/` — never edit `contracts.py`, `types.ts`, or any other stream's files);
no account/publish credentials; ACU-awareness (alert at ~36 ACUs; await human approval before
drawing from the shared reserve).

---

## Devin Session P2 — Extraction & writing

**ACU soft-cap: ~45 ACUs (~56 total allocation); alert at ~45.**
**Environment key required:** `ANTHROPIC_API_KEY` (only for the live Scribe; all other steps
are offline). Mocks-first: everything except the live Scribe runs without a key.

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

**Per-bucket AC (applied at Devin Review):**
- Bucket passes when: written nodes parse against AC-1; `NodeWritten` shape matches
  `contracts.py`; `IntentLog.md` append via atomic-rename + lock is tested in
  `tests/test_concurrent_write.py` (see Cross-cutting below); write-time `scanForSecrets`
  sets `flags:[secret-detected]` on a node with a seeded secret (does not block write);
  tests pass.
- Each bucket diff is reviewed by the stream owner via Devin Review before the next begins.

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity (stop and surface any
underspecified contract — never guess); stay-in-lane (owns only `vaultmind/scribe/` and
`vaultmind/notecreator/` — never edit `contracts.py`, `types.ts`, or any other stream's
files); ACU-awareness (alert at ~45 ACUs; await human approval before drawing from the
shared reserve).

---

## Devin Session P3 — Linking & control plane / Fetch.AI

**Heaviest, highest-stakes stream — owns the most-judged deliverable (the ASI:One demo).**
Task order is deliberate: **the judged uAgent + intents come first** (Devin can build them);
vector depth is the release valve if time runs short (cut depth, never the Agentverse publish);
the Agentverse publish is late but **mandatory** and never cut — but the publish itself is a
**human carve-out** (requires account credentials).
**ACU soft-cap: ~81 ACUs (~101 total allocation); alert at ~81.**
**Environment required:** local Redis; local uAgent bureau (before Agentverse publish). No
account credentials are ever provisioned to this session.

- **Owns:** `vaultmind/connector/` (`NodeWritten` → `related` → publish `node-changed`/`linked`
  → `LinkResult`; orphan reconciliation); `vaultmind/orchestrator/` (uAgent: Chat Protocol, the
  3 ASI:One intents, `TurnProgress` consumer + in-flight timeout, point-of-record);
  `vaultmind/handoff/` (handoff trigger + **handoff-time `scanForSecrets`** + entry-point
  assembly: `VaultIndex` pointer + current intent); `vaultmind/memory/` (Redis vector index +
  query interface).
- **Build in isolation:** Connector against `fixtures/vault/` (heuristic linking first, vector
  later); intents against `fixtures/vault/`; mock `TurnProgress`; uAgent runs locally (uagents
  bureau) before any Agentverse publish.
- **Depends on (in):** foundation (contracts, node + file schemas, fixture vault); `NodeWritten`
  from P2 (mock until hr 10). **The Connector→vector dependency on P3's own index is
  non-blocking** (heuristic fallback). **Produces (out):** `LinkResult` + events → P4; ASI:One →
  judges.
- **Goes live:** consumes P2's real `NodeWritten` ~hr 10.
- **Order (front-loaded judged core first):**
  ① uAgent skeleton + Chat Protocol echo (local bureau);
  ② **the 3 ASI:One intents against the fixture vault — the judged core** (SPEC AC-8):
     Intent A (project state), Intent B (handoff readiness, blocked + ready cases),
     Intent C (open questions);
  ③ Connector heuristic linking + event publish + orphan reconciliation;
  ④ `TurnProgress` consumer + in-flight timeout (AC-4);
  ⑤ handoff trigger + handoff scan + entry-point assembly;
  ⑥ Redis vector search (**release valve** — cut depth if behind; heuristic linking already
     ships; never skip steps ①–⑤ to get here);
  ⑦ **(human carve-out — Devin halts here):** Agentverse registration + ASI:One shared-chat
     URL + demo video — Devin wires the uAgent code; **humans handle account registration,
     the shared-chat session URL, and recording**; these are never handed to Devin.

**Per-bucket AC (applied at Devin Review):**
- Bucket passes when: the 3 ASI:One intents return correct responses against the fixture vault
  (Intent B returns blocked when the seeded secret is present); `LinkResult` shape matches
  `contracts.py`; body of written nodes is byte-identical before/after Connector linking (body
  invariant test passes); handoff scan blocks on the seeded secret; tests pass.
- Each bucket diff is reviewed by the stream owner via Devin Review before the next begins.

**Devin execution rules:** hard-stop per bucket; halt-on-ambiguity (stop and surface any
underspecified contract — never guess); stay-in-lane (owns only `vaultmind/connector/`,
`vaultmind/orchestrator/`, `vaultmind/handoff/`, `vaultmind/memory/` — never edit
`contracts.py`, `types.ts`, or any other stream's files); ACU-awareness (alert at ~81 ACUs;
await human approval before drawing from the shared reserve).
**Human carve-outs (never hand to Devin):** Agentverse registration, ASI:One shared-chat URL,
demo video — these require account credentials and an interactive session.

---

## Human Session P4 — Web app (sole human-driven stream; no Devin)

**Least blocked, longest runway** — build against the fixture vault + mock events from hour 0.
**No Devin session for this stream. This is deliberate** — UI/UX is a judged general-prize
category (Best UI/UX) that benefits from direct human taste and iteration, not a budget cut.

- **Owns:** `webapp/` — Next.js full-stack: graph viz (`react-force-graph`); the **five display
  states** (git status + `flags` + live scan at gates, SPEC AC-7); staging/confirm editing →
  disk; **Auto/Review modes** + pending batch + checkpoints (consume SessionState session-end /
  web-open / explicit); handoff **confirm-or-replace** prompt + "Update intent" button (→
  `IntentLog`, manual path); SSE subscriber to `vaultmind:events`; merge-conflict side-by-side
  UI. Keeps `webapp/types.ts` in sync with `vaultmind/contracts.py` — never edit `types.ts`
  independently; if a contract appears to need changing, surface it to the team (halt-on-ambiguity
  applies here too).
- **Build in isolation:** `fixtures/vault/` + mock pub/sub events from hour 0.
- **Depends on (in):** foundation (node schema, the four file formats, `NodeChangedEvent` enum);
  live events/disk from the pipeline ~hr 10–12. Shares the `IntentLog` append contract with P2.
- **Order:** ① render the fixture vault graph; ② five-state indicators (git status + flags);
  ③ SSE from mock events → live append; ④ staging/confirm editing → disk (atomic write);
  ⑤ Auto/Review modes + pending batch + checkpoints; ⑥ handoff confirm-or-replace + Update intent
  button; ⑦ merge-conflict UI (polish).

**Integration note — B↔D cross-executor concurrent-write test.** `IntentLog.md` has two
writers: P2's `ai-detected` path (Devin stream) and P4's manual/handoff path (human stream).
`SessionState.md` is watcher-written (Devin/P1) and P4-read. The test that covers this
cross-executor boundary **is owned by P2** (`tests/test_concurrent_write.py`): two simultaneous
appends to `IntentLog.md` must not clobber — the write-temp-then-atomic-rename + `.lock`
sentinel holds, and exactly one entry ends marked `— Current`. **P4 must not add a second
atomic-write implementation**; it imports `vaultmind.notecreator.atomic_write`. No stream is
"done" until this test passes. This test spans a Devin-built stream (P2) and the human-built
stream (P4) — the stream owner for each side must verify it passes before declaring their
stream complete.

---

## Blocking timeline — checkpoints, NOT deadlines

These hours are **pace anchors to verify against, not commitments.** The failure mode isn't
being an hour late — it's not noticing you're behind until hour 14. So hour 8 is a *scheduled
beat*, not a number nobody looks at.

- **Hr 0–~3:** foundation Devin session runs Buckets 2–4 (hard-stop per bucket, human review at
  each boundary, ACU burn checked at each boundary), then wires Bucket 5; team witnesses Bucket 5
  live fire together and confirms both pre-flight checks + all seven live-fire steps; P1–P3
  Devin sessions are triggered. P4 human session can begin building against fixtures from Bucket
  2 onward.
- **Hr ~8 — PACE CHECK (everyone present) + ACU-BURN CHECK.** Each session (a) demos its stream
  against fixtures AND (b) does its first *live* handshake with its neighbor: P1's producer →
  P2's watcher consumes one real `QueueItem`; P4 subscribes to one real `node-changed` event.
  **Also check ACU burn across P1–P3 at this beat** — surface any slip, confirm no session is
  at or above its soft-cap, and flag any session that has consumed an unexpectedly large share
  of its allocation. If a session is stuck or looping (see failure modes below), this is the
  point to intervene.
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
  are **human-owned, mandatory**); Arize dashboards; vector depth (release valve);
  merge-conflict polish; pitch deck. Out-of-scope items (dynamic VaultIndex) only if everything
  else is done.

**Failure modes (Devin-specific):**
- **Stuck / looping Devin session:** a session that keeps re-running the same bucket without
  passing its AC, or that is burning ACUs in a loop (e.g., repeatedly retrying a failing test
  without making progress), should be flagged at the next Devin Review boundary. The human
  reviewer pauses the session, diagnoses the root cause, and either unblocks the session (by
  clarifying a spec ambiguity or fixing an environment problem) or completes the remaining
  bucket by hand. Never let a looping session silently drain the shared reserve.
- **Session approaches reserve:** if a session exceeds its soft cap and is drawing from the
  shared reserve, the human reviewer must approve the draw explicitly (per the ACU governance in
  `SPEC.md` §Execution Model). If the reserve itself would be exceeded, the session is paused at
  its next Devin Review boundary and the remaining work is finished by hand.
- **Ambiguity halt:** a Devin session that surfaces a halt-on-ambiguity question is *not* a
  failure — it is working correctly. The human reviewer resolves the ambiguity (by clarifying
  the spec, not by telling Devin to guess), then resumes the session.

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
  owns the test** — it lives at `tests/test_concurrent_write.py` and asserts: two simultaneous
  appends to `IntentLog.md` do not clobber — the write-temp-then-atomic-rename + `.lock`
  sentinel holds, and exactly one entry ends marked `— Current`. P4 must not add a second
  atomic-write implementation; it imports the same utility P2 ships
  (`vaultmind.notecreator.atomic_write`). No stream is "done" until this test passes.
  **This test spans a Devin-built stream (P2) and the human-built stream (P4)** — both sides
  must verify it passes before declaring their work complete.

---

## ACU allocation — quick reference

Full governance in `SPEC.md` §Execution Model. Summary:

| Stream | Share | ACUs | Soft-cap alert | Executor |
|---|---|---|---|---|
| P3 — Linking + Orchestrator | 38% | 101 | ~81 | Devin Cloud |
| P2 — Extraction & writing | 21% | 56 | ~45 | Devin Cloud |
| P1 — Ingestion | 17% | 45 | ~36 | Devin Cloud |
| Foundation — Buckets 2–4 | 7% | ~19 | ~15 | Devin Cloud |
| Shared reserve | 17% | 45 | human-approved draw only | — |
| **P4 — Web app** | — | **0** | n/a | **Human only** |

- At ~80% of its allocation, a session surfaces a burn alert; the human reviewer approves any
  draw from the shared reserve.
- A session that would exceed even the reserve is paused at its next Devin Review boundary; the
  owner finishes by hand.
- P1–P3 stream owners may execute any bucket directly (conserving ACUs) — same bucket-approval
  rules apply regardless of executor.
