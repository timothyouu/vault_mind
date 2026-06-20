# VaultMind

Persistent, structured project memory in Obsidian-compatible Markdown, transferable between LLM
tools (Claude Code, Codex, Gemini) without late-stage summarization. A multi-agent pipeline
writes a git-native vault as you work; a trust UI lets you review and hand off.

## Read these first (don't re-derive them)
- **`SPEC.md`** — the technical contract: node schema, the six agent message contracts, the four
  file formats, `scanForSecrets`, hook configs, the session-end resolution, and the buckets.
- **`WORKSTREAMS.md`** — who runs what session, what's mockable in isolation, when each seam goes
  live (checkpoints, not deadlines), and per-session task order. Find your stream here.

## Standing rules (everyone, always)
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

## Stack
Python pipeline + hooks + Orchestrator (a published Fetch.AI uAgent); TypeScript / Next.js
full-stack web app. Redis = queue (Streams) + event bus (pub/sub) + vector memory. Arize across
all agents. The only cross-language seams are `vault/*.md` on disk and Redis.

## Devin execution rules (foundation Buckets 2–4, and streams P1, P2, P3)
- **Hard-stop per bucket.** Complete exactly one bucket, post the diff, and halt until a human
  approves and merges via Devin Review. Do not begin the next bucket without that approval.
- **Halt-on-ambiguity.** If a bucket is underspecified or a frozen contract appears to need
  changing, stop and surface the question. Never guess or invent an interface.
- **Stay-in-lane.** Touch only your session's owned files. Never edit `contracts.py` /
  `types.ts` or another session's files.
- **No account or publish credentials.** Agentverse registration, the ASI:One shared-chat URL,
  and the demo video are human-owned tasks. Never request or use account credentials.
- **ACU-awareness.** Each session has a soft-cap budget. If you approach it, surface the alert
  and await human approval before drawing from the shared reserve.
