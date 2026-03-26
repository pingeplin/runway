# TDD Workflow Guide

The canonical blueprint workflow for building a feature with TDD. Each step is an independent skill — use as many or as few as the task warrants.

```
/spec → /plan → /run → /refactor → /commit
```

Orchestrated by `/tdd`.

## Step-by-step

| Step | Skill | Who | What happens |
|------|-------|-----|--------------|
| 1 | `/spec` | AI + Human | Generate spec with acceptance scenarios + built-in testability review |
| 2 | `/plan` | AI + Human | Generate execution graph — behavioral milestones with dependencies, streams, critical path |
| 3 | `/run` | AI | Execute the graph: read codebase, write tests, implement code per triplet. Post-run evaluation (test suite, coverage, Desiderata, /simplify) is handled by an independent evaluator hook |
| 4 | `/refactor` | AI + Human | Human gives direction, AI refactors with tests as safety net |
| 5 | `/commit` | AI | Generate commit message following Chris Beams' 7 rules |

Standalone: `/review` — can review any artifact (spec, plan, test, implementation) at any point.

## Human decision points

The human's role is thinking clearly and quality gates:

1. **Requirements** — articulate what to build (input to /spec)
2. **Spec approval** — review generated spec before /plan
3. **Plan approval** — review execution graph before /run
4. **Refactoring direction** — tell the AI what structural improvements to make
5. **Final review** — verify the result

## Scaling to task size

- **Small bug fix:** Skip /spec, go straight to /plan.
- **Single feature:** Full workflow, /spec can be lightweight.
- **Large feature:** Break into sub-features, run workflow multiple times.
- **Prototype / spike:** Use `/proto` — happy-path only, no spec, fast feedback. Promote to `/tdd` if the idea works.
- **Refactoring only:** Jump to /refactor (verify tests pass first).
