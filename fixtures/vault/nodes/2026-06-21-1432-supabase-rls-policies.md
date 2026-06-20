---
id: 2026-06-21-1432-supabase-rls-policies
type: decision
title: Use Supabase RLS for row-level auth
created: 2026-06-21T14:32:07-07:00
source_tool: claude-code
source_session: 00893aaf-19fa-41d2-8238
intent_ref: 2026-06-21 14:32
status: approved
related:
  - "[[2026-06-21-1015-db-schema-users-table]]"
  - "[[Constraints]]"
flags: []
---
Decided to enforce per-row access with Supabase Row-Level Security rather than
checking ownership in app code, so the DB is the single source of truth for authz.

> "let's just do RLS so we don't re-check ownership in every endpoint"
