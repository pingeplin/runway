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
- Step 6 → implement (auto-chains /post-verification)
- Step 7 → /refactor
- Step 8 → /git-commit-message (for committing the result)

Note: /test-orderer and /post-verification can still be invoked standalone.

Include the scaling guidance from the workflow doc so the user can calibrate the workflow to their task size.
