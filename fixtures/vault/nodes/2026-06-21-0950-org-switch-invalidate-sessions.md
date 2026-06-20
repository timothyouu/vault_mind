---
id: 2026-06-21-0950-org-switch-invalidate-sessions
type: question
title: Should org-switch invalidate sessions?
created: 2026-06-21T09:50:00-07:00
source_tool: claude-code
source_session: 00893aaf-19fa-41d2-8238
intent_ref: 2026-06-21 10:15
status: pending
related:
  - "[[2026-06-21-1432-supabase-rls-policies]]"
flags: []
---
Should switching the active org invalidate a user's active sessions?

Options: (a) invalidate on org-switch — safer, prevents stale org-context bugs, more disruptive UX;
(b) don't invalidate — seamless UX, but risks stale data until JWT expiry.

Not yet decided; needs an explicit call before implementing session management.

> "Should switching orgs invalidate a user's active sessions? I'm not sure what the right call is here."
