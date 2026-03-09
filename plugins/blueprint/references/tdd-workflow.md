# TDD Workflow Guide

The canonical blueprint workflow for building a feature with TDD. Each step is an independent skill — use as many or as few as the task warrants.

```
/design-doc → /design-doc-reviewer → /test-generator (auto-chains /test-orderer) → human review → /implementation-plan → implement → CI → /post-verification → /refactor → CI → human review
```

## Step-by-step

| Step | Skill | Who | What happens |
|------|-------|-----|--------------|
| 1 | `/design-doc` | AI + Human | Generate a design doc with acceptance scenarios |
| 2 | `/design-doc-reviewer` | AI | Review for testability, ambiguity, coverage gaps |
| 3 | `/test-generator` → `/test-orderer` | AI | Generate skipped test cases, then auto-order for TDD implementation |
| 4 | Human review | Human | Review generated tests and ordering; adjust sequence, cut scope if needed |
| 5 | `/implementation-plan` | AI | Generate a task checklist from design doc + tests |
| 6 | Implement | AI | Red-Green loop: unskip tests one phase at a time |
| 7 | `/post-verification` | AI | Cross-check implementation against design doc and plan |
| 8 | `/refactor` | AI + Human | Human gives direction, AI refactors with tests as safety net |
| 9 | Design scan | Human | Quick structural review of the result |

> **Note:** `/test-orderer` can still be invoked standalone (e.g., to re-order after adding tests manually).

## Human decision points

The human's role is thinking clearly and quality gates:

1. **Requirements** — Articulate acceptance scenarios before the AI writes anything
2. **Design approval** — Compare the generated doc against your own thinking
3. **Test ordering** — Control the rhythm of implementation, cut scope if needed
4. **Verification review** — Review the post-verification report, decide whether to address gaps or defer
5. **Refactoring direction** — Tell the AI what structural improvements to make
6. **Design scan** — Verify the final structure makes sense

## Scaling to task size

- **Small bug fix:** Skip steps 1-2. Write tests (step 3), implement, maybe refactor.
- **Single feature:** Full workflow. Steps 1-2 can be lightweight (~200 words).
- **Large feature:** Break into sub-features and run the workflow multiple times.
- **Refactoring only:** Jump to step 8 directly (verify tests exist and pass first).
