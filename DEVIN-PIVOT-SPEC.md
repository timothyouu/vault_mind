# Spec: VaultMind Execution-Layer Pivot (Devin)

> Revision spec. Aligns `SPEC.md`, `WORKSTREAMS.md`, and `CLAUDE.md` with the proposal's one
> architecture pivot since they were written: **Devin is no longer an in-product feature — it is
> the execution layer for the build itself.** This is the contract for *that revision only*. It does
> not re-argue the product and reopens **no** byte-level contract. Sources: the current proposal PDF,
> sections "How the Build Actually Runs: Devin as the Execution Layer" and the Cognition (Devin)
> sponsor-track entry.

---

## Roles at a glance (read this first — it's the whole pivot)

| Who | Surface | Does what | Draws Devin ACUs? |
|---|---|---|---|
| **Devin** (3 parallel Cloud sessions) | Devin Cloud | **Executes** — writes the code for streams **P1, P2, P3**, one bucket at a time, unattended between boundaries, subagents allowed *within* a bucket | **Yes** (the ~266 pool) |
| **Humans** (the team) | Devin Review + Claude Code | **Review** every Devin bucket via Devin Review (approve + merge before the next bucket starts); **build the foundation** (Claude Code session); **build P4** (Claude Code session); own the **carve-outs** (Agentverse, ASI:One URL, demo video, the witnessed Bucket-5 gate, integration) | No |

**"Devin Review" is the interface a *human* reviews through — it is not Devin reviewing itself.**
Devin is the executor; the human is the reviewer.

---

## Goal

Today `SPEC.md` and `WORKSTREAMS.md` assume a human types every bucket of every stream — "four
owners, each in their own Claude Code session," buckets reviewed by the person who wrote them. The
proposal changed that: **streams P1–P3 are now executed by three parallel, unattended Devin Cloud
sessions; only P4 stays human-driven.**

After this revision, the three build docs describe *that* world and only that world:

- **P1, P2, P3** are written by Devin, **hard-stop per bucket** — a session does exactly one bucket
  (it may parallelize with subagents *inside* the bucket), then halts until a human approves +
  merges via Devin Review before the next bucket begins.
- **P4** is built by a human in Claude Code, with **no Devin session**, deliberately — UI/UX is a
  judged general-prize category (Best UI/UX) that benefits from direct human taste and iteration.
- The **foundation** (existing Buckets 1–5) is built in a **human Claude Code session** — agent-
  drafted from the already-frozen SPEC and human-reviewed (Buckets 2–4), with Bucket 5 an inherently
  human-run, witnessed live fire. The foundation draws **zero Devin ACUs**, and its Bucket-5 gate is
  what **triggers** the P1–P3 Devin sessions.
- The work is governed by a **fixed ~266-ACU credit pool** ($600) shared across **P1–P3 only**.

The byte-level contracts that made the seams parallel-safe for four humans are **unchanged** — and
are now the precondition that makes unattended cloud execution safe (an ambiguous spec is fine when a
human can ask a clarifying question mid-build; it is a real risk when cloud agents run unattended
against a shared repo). The pivot changes *who executes and how work is reviewed*, never *what gets
built*.

## User

- **The P1 / P2 / P3 stream owners** — now decide how much of their stream to delegate to a Devin
  session vs. run directly (the discretion lever, e.g. to conserve ACUs or when hand-doing a bucket
  is safer), and **review + approve + merge** their stream's output via Devin Review at every bucket
  boundary.
- **The P4 owner** — builds the web app directly in a local / human-supervised Claude Code session.
- **Whoever performs Devin Review** and owns the human carve-outs (Agentverse registration + Agent
  Profile URL, the ASI:One shared-chat URL, the demo video) and the witnessed Bucket-5 gate.

## Acceptance Criteria

**AC-1 — Per-stream change ledger.** `SPEC.md` and `WORKSTREAMS.md` each state explicitly, per
stream, what changed vs. stayed the same:
- **P1/P2/P3:** executor → Devin Cloud session; brief hardened for unattended execution; carve-outs
  noted; **stream code unchanged in scope** (same deliverables, new executor).
- **P4:** executor **unchanged** (human Claude Code, no Devin); framing/labels updated; integration
  notes added.
- **Foundation (Buckets 1–5):** executor defined as **human Claude Code session** (agent-drafted +
  human-reviewed for 2–4; human-run for 5); not Devin.

**AC-2 — "Bucket approval" is defined for a Devin executor.** The docs define it as **hard-stop per
bucket**: a Devin session completes exactly one bucket (subagents permitted *within* the bucket),
posts its diff, and **does not begin the next bucket until a human approves and merges via Devin
Review.** The definition includes:
- **Halt-on-ambiguity** — if a bucket is underspecified, or a frozen contract appears to need
  changing, the session stops and surfaces the question; it never guesses or invents an interface.
- **Stay-in-lane** — a session touches only its own stream's owned files; it never edits frozen
  contracts (`contracts.py` / `types.ts`) or another stream's files.

**AC-3 — Concrete ACU allocation** against the confirmed **$600 / ~266-ACU** pool ($2.25/ACU,
~15 min active compute/ACU), **across P1–P3 only:**

| Stream | Share | ACUs | Soft-cap alert |
|---|---|---|---|
| P3 — Linking + Orchestrator (heaviest, most-judged) | 40% | 106 | ~85 |
| P2 — Extraction & writing | 22% | 58 | ~46 |
| P1 — Ingestion (front-loaded, stable) | 18% | 48 | ~38 |
| Shared reserve (tail / re-runs / integration) | 20% | 54 | human-approved draw only |
| **P4 — Web app** | — | **0** | n/a (human) |

Governance: a soft cap = the stream's allocation; at ~80% the human reviewer is alerted (burn-
monitoring); continuing past it requires **human approval to draw from the reserve** (so no stream
silently starves another); a session that would exceed even the reserve is **paused at its next
Devin Review boundary**, where the owner may finish that bucket **by hand** to conserve ACUs. The
foundation and P4 consume **no** ACUs (Claude Code sessions). The binding risk is the *tail* — a
runaway/looping session or repeated re-runs, amplified by in-bucket subagents burning concurrently —
not the average; the caps target the tail.

**AC-4 — P4 is entirely human-driven, no Devin session.** Asserted in all three docs: no Devin Cloud
session is created for graph visualization, the five display states, staging/confirm editing, the
Auto/Review-mode UI, or the handoff prompts. This is **deliberate** (Best UI/UX general-prize
category), not a budget-driven cut.

**AC-5 — Updated `CLAUDE.md` that holds for both readers.** Its standing rules read correctly **both**
for a human opening a Claude Code session **and** for a Devin session consuming it as a brief — plus
new execution-model rules: hard-stop per bucket; stay-in-lane; halt-on-ambiguity; **never hand a
Devin session an account/publish credential** (Agentverse, etc.); ACU-awareness. It stays short and
points to `SPEC.md` / `WORKSTREAMS.md` (no duplicated content).

**AC-6 — No byte-level contract is touched.** The revision changes **none** of `SPEC.md` AC-1…AC-8
(node schema, vault layout + file formats, the six message contracts, failure visibility,
`scanForSecrets`, hook configs, display states, ASI:One intents) or the Stack non-negotiables. A
reviewer can diff those sections and confirm they are byte-unchanged. The revision states *why* they
are untouched: they are the precondition that makes unattended Devin execution safe.

**AC-7 — Foundation executor + the trigger gate are explicit.** The docs state: the foundation is a
**human Claude Code session**; Buckets 2–4 are agent-drafted + human-reviewed, each gated on a diff-
review against the relevant AC **plus two deterministic checks** — **`contracts.py`↔`types.ts` field
parity** and **every fixture node parsing against AC-1**; and **Bucket 5 (the witnessed live fire) is
the single gate that triggers all three P1–P3 Devin sessions** (sessions are triggered by this gate,
not by a clock hour). Bucket 5's DoD additionally verifies that Devin-built components conform to the
frozen contracts.

## Out of Scope

- **Any change to `SPEC.md` AC-1…AC-8 or the Stack & Constraints non-negotiables** (Redis, Fetch.AI
  uAgents/Agentverse/ASI:One, Arize, Claude Code + Codex hooks). Not reopened.
- **A Devin session for P4.** Explicitly excluded.
- **Devin as an in-product handoff target** (the old Devin REST-API third handoff target alongside
  Gemini / a fresh Claude Code session) — already dropped; stays out (it was a stretch/out-of-scope
  item).
- **Re-deciding the Karpathy bucket method or the product architecture.**
- **Building or executing the streams themselves.** This revision edits docs only.
- **Stretch items** — dynamic `VaultIndex.md`, vector-search depth tuning — unchanged.
- **Editing the proposal PDF / Google Doc itself.** Its residual P4-in-Devin language (the stream
  table lists P4 with a "Devin session scope" column; the prose says "P2 and P4 similarly start
  immediately") contradicts the locked "P4 never Devin" decision — this is **flagged as an out-of-
  band fix for the proposal owner**, not fixed in these three files.

## Stack & Constraints

**Unchanged (not reopened):** Redis (queue Streams + event bus pub/sub + vector memory); Fetch.AI
uAgents + Agentverse + ASI:One (the Orchestrator is the published uAgent with the Chat Protocol);
Arize across the pipeline + web-app server; Claude Code + Codex `Stop`/`SessionEnd` hooks; Python
pipeline/hooks/Orchestrator + TypeScript/Next.js full-stack web app; the only cross-language seams
are `vault/*.md` on disk and Redis.

**New, locked:**
- **Devin Cloud + Devin Review = the execution/review layer for P1, P2, P3 only.** Devin executes;
  humans review via Devin Review.
- **$600 / ~266-ACU shared pool** across P1–P3 (allocation in AC-3).
- **Hard-stop per bucket**; **subagents permitted within a bucket**; **halt-on-ambiguity** +
  **stay-in-lane** (AC-2).
- **Mocks-first + minimal scoped keys** for Devin environments (P2 → `ANTHROPIC_API_KEY`; P3 → local
  Redis / local uAgent bureau); **account/publish credentials are never provisioned to Devin.**

**New, locked (exclusions):**
- **P4 is never executed by Devin** (human Claude Code session).
- **The foundation (Buckets 1–5) is never a Devin session** (human Claude Code; agent-drafted +
  human-reviewed for 2–4; Bucket 5 human-run). Zero ACUs.

## Task Breakdown

Small, independently reviewable buckets. Each **edits an existing doc in place** — not a new parallel
doc the team has to reconcile against the originals. Do not start a bucket until the previous is
approved; at each boundary, summarize what was done and wait for confirmation.

**Bucket 1 — Revise `SPEC.md` in place.**
- Add an **Execution Model** section (the contract): bucket-approval = hard-stop, subagents-within-
  a-bucket, the human/Devin boundary + carve-outs, the foundation-vs-stream executor split, and the
  "Devin Review = a human reviews Devin's output" clarification.
- Reframe **§Goal** (person-boundary → session-boundary) and **§User** (session executors: Devin for
  P1–P3, human Claude Code for P4 and for the foundation).
- Update the **§Task Breakdown** intro + **Bucket-5 Definition of Done** so that (a) Bucket 5 is the
  explicit gate that triggers the P1–P3 Devin sessions and (b) it verifies Devin-built components
  against the frozen contracts, plus record the two deterministic foundation checks.
- Add the **"AC-1…AC-8 unchanged, and why"** note.

**Bucket 2 — Revise `WORKSTREAMS.md` in place.**
- Retitle (drop "four owners" → the executor model).
- Reframe the **Foundations-first gate** in terms of *triggering Devin sessions / committing ACUs*,
  and name Bucket 5 as the trigger.
- **Harden the P1/P2/P3 briefs** (Option A): per-bucket acceptance criteria, the halt-on-ambiguity
  protocol, and the stay-in-lane constraint.
- **Re-bucket P3**: front-load the judged core (uAgent skeleton → 3 ASI:One intents on fixtures);
  carve the human deliverables (Agentverse registration + Profile URL, ASI:One shared-chat URL, demo
  video) out as **human** tasks; keep vector-search as an explicit **human-pulled** release valve.
- **Label P4** the sole human-driven stream; add integration notes, including **who owns the B↔D
  cross-executor concurrent-write test** (now spanning a Devin stream and a human stream).
- Revise the **timeline + hr-8 pace check** to human-review-of-Devin + an **ACU-burn check**; add the
  **"stuck / looping Devin session"** failure mode.
- Insert the **ACU allocation table + governance** (AC-3) and note the **direct-execution
  discretion** lever for P1–P3 owners.

**Bucket 3 — Update `CLAUDE.md`.**
- Rephrase the standing rules to hold for **both** a human at session start and a Devin session
  reading it as a brief.
- Add the **Devin execution-model rules** (hard-stop, stay-in-lane, halt-on-ambiguity, no account/
  publish credentials to Devin, ACU-awareness).
- Keep it short; keep it pointing to `SPEC.md` + `WORKSTREAMS.md`.

**Bucket 4 — Cross-document consistency pass + self-review.**
- Verify the three docs agree (no contract drift; P4-never-Devin consistent; foundation executor
  consistent; allocation numbers match across docs).
- Confirm `SPEC.md` AC-1…AC-8 and the Stack non-negotiables are byte-unchanged.
- File the **out-of-band flag** for the proposal's residual P4-in-Devin language.

---

After spec approval, we start with **Bucket 1 only**; at the end of each bucket I summarize and wait
for your confirmation before the next.
