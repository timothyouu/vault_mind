# VaultMind

Persistent, structured project memory in Obsidian-compatible Markdown, transferable between LLM
tools (Claude Code, Codex, Gemini) without late-stage summarization. A multi-agent pipeline
writes a git-native vault as you work; a trust UI lets you review and hand off.

> **This file is the brief for both human sessions (Claude Code) and Devin Cloud sessions.**
> The standing rules and execution rules below apply to all readers; the only difference is
> executor — Devin for foundation Buckets 2–4 and streams P1–P3, human for P4.

## Read these first (don't re-derive them)
- **`SPEC.md`** — the technical contract: node schema, the six agent message contracts, the four
  file formats, `scanForSecrets`, hook configs, the session-end resolution, the buckets, and the
  **Execution Model** (roles, bucket-approval protocol, ACU allocation, the Bucket-5 trigger gate,
  and the AC-1…AC-8 unchanged note).
- **`WORKSTREAMS.md`** — who runs what session, what's mockable in isolation, when each seam goes
  live (checkpoints, not deadlines), per-session task order, per-bucket acceptance criteria, ACU
  table, and failure modes. Find your stream here.

## Standing rules (everyone, always — human or Devin session)
1. **Never let a downstream LLM touch the Scribe's content.** The Note Creator wraps the Scribe's
   extraction verbatim; the Connector edits **only** frontmatter `related` — never the body. The
   body is immutable after write.
2. **Always `scanForSecrets` before it matters:** write-time (before any disk write), commit-time
   (pre-commit hook), handoff-time (before the vault is exposed). One Python implementation —
   never add a second.
3. **Disk is the source of truth.** Redis events are minimal "re-read this id" triggers, not
   payloads; the web app re-reads files + `git status` on every event.
4. **`IntentLog.md` is the developer's own words.** Only Auto Mode may write an `ai-detected`
   entry, and it must be labeled. Review Mode never writes it without confirmation.
5. **VaultMind never commits or hands off silently.** Commits are manual; a detected secret
   blocks commit *and* handoff in both Auto and Review modes.
6. **Concurrent-write safety:** appends to `IntentLog.md` / `SessionState.md` use atomic
   write-temp-rename + a `.lock` sentinel (test required — see WORKSTREAMS.md).

## Execution-model rules (Devin sessions — foundation Buckets 2–4, and streams P1, P2, P3)
These rules also apply to human sessions working on any of these streams.

- **Hard-stop per bucket.** Complete exactly one bucket, post the diff, and halt until a human
  approves and merges via **Devin Review**. Do not begin the next bucket without that approval.
  ("Devin Review" is the interface a human reviewer uses — not Devin reviewing itself.)
- **Halt-on-ambiguity.** If a bucket is underspecified or a frozen contract appears to need
  changing, stop and surface the question. Never guess or invent an interface.
- **Stay-in-lane.** Touch only your session's owned files. Never edit `contracts.py` /
  `types.ts` or another session's files. File ownership per stream is in `WORKSTREAMS.md`.
- **No account or publish credentials.** Agentverse registration, the ASI:One shared-chat URL,
  and the demo video are human-owned tasks that require account credentials. A Devin session
  must never be handed these credentials and must never attempt those tasks.
- **ACU-awareness.** Each session has a soft-cap budget (allocation table in `SPEC.md`
  §Execution Model and `WORKSTREAMS.md` §ACU allocation). At ~80% of the allocation, surface a
  burn alert and await human approval before drawing from the shared reserve. A session that
  would exceed even the shared reserve is paused at its next Devin Review boundary; the owner
  finishes by hand.
- **P4 is never executed by Devin.** The web-app stream (P4) is human-only — deliberate, not a
  budget cut. No Devin session is created for it.

## Stack
Python pipeline + hooks + Orchestrator (a published Fetch.AI uAgent); TypeScript / Next.js
full-stack web app. Redis = queue (Streams) + event bus (pub/sub) + vector memory. Arize across
all agents. The only cross-language seams are `vault/*.md` on disk and Redis.

## Webapp scaffold (Bucket 4 — walking skeleton)
- `webapp/` — Next.js 15 app (TypeScript, Tailwind, ESLint, App Router, `src/` layout)
  - `webapp/types.ts` — frozen TS contracts; **do not edit** (mirrors `vaultmind/contracts.py`)
  - `webapp/src/app/page.tsx` — VaultMind vault page; SSE client, live event list
  - `webapp/src/app/api/events/route.ts` — SSE endpoint; subscribes to `vaultmind:events` Redis pub/sub
  - `webapp/package.json` — includes `redis ^6.0.0` dependency
- `package.json` (repo root) — `vaultmind:start` script + `dev` shortcut
- `scripts/start.sh` — starts Redis (Docker), Python watcher, and Next.js dev server concurrently

## Last Updated
2026-06-20 — Bucket 4: Next.js webapp scaffold (create-next-app), SSE /api/events route,
VaultMind vault page (NodeChangedEvent live list), redis npm package, root package.json,
scripts/start.sh. TypeScript compiles clean (tsc --noEmit exit 0). webapp/types.ts preserved.

2026-06-20 — Execution-model pivot (DEVIN-PIVOT-SPEC.md): updated SPEC.md, WORKSTREAMS.md, and
CLAUDE.md to reflect Devin Cloud as the executor for foundation Buckets 2–4 and streams P1–P3;
added Execution Model section to SPEC.md (roles, ACU allocation, bucket-approval protocol,
Bucket-5 trigger gate, AC-1…AC-8 unchanged note); hardened WORKSTREAMS.md stream briefs with
per-bucket AC, ACU soft-caps, failure modes, and cross-executor B↔D concurrent-write note;
updated CLAUDE.md to serve as dual brief (human + Devin) with full execution-model rules.
