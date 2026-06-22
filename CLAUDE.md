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

## Merge page (frontend ↔ backend)
- `webapp/src/lib/conflicts.ts` — server-only: reads `vault/nodes/*.md`, parses git conflict markers into `Segment[]`, delegates secret scan to `python3 -m vaultmind.secrets` (one implementation per SPEC). Env var `REPO_ROOT` overrides the default `process.cwd()/..` path.
- `webapp/src/app/api/conflicts/route.ts` — GET: list all conflicted nodes (summaries)
- `webapp/src/app/api/conflicts/[id]/route.ts` — GET: full segment data for one node
- `webapp/src/app/api/conflicts/[id]/resolve/route.ts` — POST `{ resolutions: Record<hunkIndex, 'ours'|'theirs'|'both'|{custom:string}> }` → scans merged content for secrets via temp file, writes resolved node to disk. Returns `{ ok, secretBlocked?, scanSnippet? }`. `Resolution` type (exported from `conflicts.ts`) now includes `{ custom: string }` for user/AI-authored "write your own" text; `resolveNode` splits custom text on newlines.
- `webapp/src/app/api/conflicts/[id]/recommend/route.ts` — POST → loads the node's hunks and calls the Anthropic Messages REST API directly (no SDK dep; model `claude-sonnet-4-6`, `ANTHROPIC_API_KEY` — same key as the Scribe) to recommend `ours|theirs|both|custom` per hunk with a one-line rationale (+ `suggestedText` for custom). Returns `{ recommendations: [{ index, choice, rationale, suggestedText? }] }`. Returns 503 with a clear message when `ANTHROPIC_API_KEY` is unset; the UI surfaces it as a toast. **Requires `ANTHROPIC_API_KEY` in the webapp env (e.g. `webapp/.env.local`) for the AI panel to work.**
- `webapp/src/app/merge/page.tsx` — client component: GitHub-dark conflict resolution UI matching VaultMind Merge design. Fetches conflicts list + per-node detail, renders diff editor with accept/reject per hunk, progress bar, scan-blocked panel, toast notifications, dark/light theme toggle. Now also: **"Write your own"** per-hunk custom-text editor (textarea, seed-from-both helper), and a real **VaultMind AI** right-rail panel ("Get AI recommendation") that posts to `/recommend`, shows per-hunk "AI suggests …" banners with one-click apply, and "Apply all AI suggestions".
- `vault/nodes/2026-06-21-1530-7c2f9a14-demo-auth-conflict.md` — seed demo node with two real `<<<<<<<`/`=======`/`>>>>>>>` conflict hunks (auth strategy), so the Merge page has something to render. Safe to delete once real conflicts exist.
- `webapp/src/app/globals.css` — added VaultMind CSS variables (dark/light via `data-vmtheme`) + `vm-fade`/`vm-toast` keyframes.
- `webapp/src/app/layout.tsx` — added JetBrains Mono font, updated metadata.

## Last Updated
2026-06-22 — README rewritten (branch `docs/readme-rewrite`, PR #7) to reflect the actual app
rather than SPEC.md: added objective/problem/solution framing, accurate tech-stack table
(Pydantic v2, Anthropic claude-sonnet-4-6, Redis Stack, RedisVL + all-MiniLM-L6-v2, Arize/OTel,
Next.js 15/React 19, Fetch.AI uAgents, Flask bridge), and a per-module/per-route inventory now
including the Setup/Graph/Intent pages, AgentChat + useAgent + webapp/agent_bridge.py, the
memory/ (vector) and handoff/ modules, /api/nodes, and the deployable vault-mind-orchestrate/
Agentverse agent. Expanded setup into a full end-to-end guide (Redis Stack Docker-or-local,
run-by-hand, optional Orchestrator agent + ASI:One publishing). Includes an honest "pipeline
status" note that watcher.py ships wired to stub scribe/notecreator/connector seams while the
real agents are implemented + tested. README-only change.

2026-06-22 — Merge page upgraded: (1) per-hunk "Write your own" custom-text resolution
(new `{custom:string}` variant on `Resolution` in conflicts.ts + resolve route validation);
(2) real per-hunk AI recommendations via new `/api/conflicts/[id]/recommend` route calling the
Anthropic Messages REST API (claude-sonnet-4-6, `ANTHROPIC_API_KEY`) — inline "AI suggests"
banners + apply-all; (3) seed demo conflict node so the page renders. Verified: tsc clean, no new
lint errors, /api/conflicts + detail + custom resolve confirmed via running dev server. AI panel
needs `ANTHROPIC_API_KEY` in the webapp env to function (graceful 503 + toast otherwise).

2026-06-20 — Merge page implemented: conflict resolution UI (VaultMind Merge design) wired to real backend. API routes: GET /api/conflicts, GET /api/conflicts/[id], POST /api/conflicts/[id]/resolve. Server-side git conflict parser + secret scanner in webapp/src/lib/conflicts.ts. TypeScript compiles clean.

2026-06-20 — Execution-model pivot (DEVIN-PIVOT-SPEC.md): updated SPEC.md, WORKSTREAMS.md, and
CLAUDE.md to reflect Devin Cloud as the executor for foundation Buckets 2–4 and streams P1–P3;
added Execution Model section to SPEC.md (roles, ACU allocation, bucket-approval protocol,
Bucket-5 trigger gate, AC-1…AC-8 unchanged note); hardened WORKSTREAMS.md stream briefs with
per-bucket AC, ACU soft-caps, failure modes, and cross-executor B↔D concurrent-write note;
updated CLAUDE.md to serve as dual brief (human + Devin) with full execution-model rules.
