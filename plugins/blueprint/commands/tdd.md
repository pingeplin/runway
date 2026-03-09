---
name: tdd
description: Show the TDD workflow steps for building features with the blueprint plugin.
---

Read `../references/tdd-workflow.md` and present its contents to the user in a clear, actionable format.

After presenting the workflow, ask the user which step they'd like to start with. If they name a step that maps to a skill, invoke that skill for them.

Step-to-skill mapping:
- Step 1 → /design-doc
- Step 2 → /design-doc-reviewer
- Step 3 → /test-generator (auto-chains /test-orderer)
- Step 5 → /implementation-plan
- Step 7 → /post-verification
- Step 8 → /refactor
- Step 9 → /git-commit-message (for committing the result)

Note: /test-orderer can still be invoked standalone to re-order tests independently.

Include the scaling guidance from the workflow doc so the user can calibrate the workflow to their task size.
