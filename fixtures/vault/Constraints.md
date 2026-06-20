---
id: Constraints
type: scope
title: Project Constraints
created: 2026-06-20T18:00:00-07:00
source_tool: claude-code
source_session: 00893aaf-19fa-41d2-8238
intent_ref: 2026-06-20 18:00
status: approved
related: []
flags: []
---
Standing constraints that apply to all decisions in this project:

1. **RLS is the authz source of truth.** Supabase Row-Level Security enforces per-row access; app code must not re-check ownership.
2. **No PII in logs.** User emails, names, and org membership details must not appear in any log output (structured or unstructured). Log user IDs (opaque UUIDs) only.
