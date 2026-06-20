# Vault Index — {{project}}
Read order for a receiving agent:
1. ProjectGoal.md, Constraints.md, TechStack.md — standing project frame
2. Current entry in IntentLog.md (top, marked "Current") — what to do next
3. SessionState.md — context-degradation flags; check before trusting recent nodes
4. nodes/ — atomic decisions/constraints/goals/questions, linked via `related`

Conventions: links live in each node's `related:` frontmatter as `[[basename]]`;
`intent_ref` = the IntentLog entry key current when the node was written.
