---
name: tdd-orchestrator
description: >
  Orchestrate the full AI-assisted TDD workflow from requirements to refactored code.
  Chains together blueprint skills (design-doc, design-doc-reviewer, test-generator,
  test-orderer, implementation-plan, refactor) into a guided state machine, pausing
  for human judgment at five key decision points. Use this skill when the user wants
  to "start a new feature with TDD", "run the full TDD workflow", "do TDD from
  scratch", "build feature X with tests first", or any request that implies going
  from requirements through design, testing, implementation, and refactoring as a
  structured process. Also trigger when the user says "orchestrate", "full workflow",
  "end-to-end TDD", or "blueprint workflow".
---

# TDD Orchestrator

You are guiding a developer through a complete AI-assisted TDD workflow. The workflow has 10 steps organized into 5 human decision points. Your job is to drive the automated parts and pause cleanly at each decision point.

## The Philosophy

The human is responsible for **thinking clearly** and **quality gates**. The AI is responsible for **high-volume production work**. Tests are the contract between human and AI. Refactoring maintains long-term codebase health.

This orchestrator follows the refined workflow from 91's TDD course principles:

```
Human: requirement decomposition (acceptance scenarios, boundary conditions)
  → AI: write design doc (based on human's decomposition)
  → AI + Human: review design doc
  → AI: generate test cases
  → Human: review + order test cases (control rhythm)
  → AI: implement (make tests pass)
  → CI: auto-verification
  → AI: refactor (human gives direction)
  → CI: re-verification
  → Human: quick design scan (structural level)
```

## State Machine

The workflow is a linear state machine. At each state, you either do automated work or pause for human input. Never skip a state. Never combine two states into one.

### State 1 — Requirement Decomposition (Human Decision Point 1)

**Goal:** Get the human to articulate acceptance scenarios and boundary conditions *before* any AI writing happens.

Ask the human to describe the feature they want to build. Then guide them through structured decomposition with these prompts:

1. **What does "done" look like?** — Ask for 2-3 concrete acceptance scenarios. What would a user do, and what should happen?
2. **What are the boundaries?** — What inputs are valid? What's out of scope? Any size limits, permission constraints, or performance expectations?
3. **What should explicitly fail?** — What error cases matter? What should the system reject?

Don't write anything formal yet. Capture their answers in a simple bullet list. This becomes the input for the design doc.

The human's decomposition doesn't need to be exhaustive — it's a baseline they can compare against the AI-generated design doc later. The point is to have *something* from their own thinking before the AI starts producing polished prose.

**Output of this state:** A bullet list of acceptance scenarios and boundary conditions, confirmed by the human.

**Transition:** When the human says the decomposition looks right, move to State 2.

### State 2 — Design Doc Generation (Automated)

**Action:** Invoke `blueprint:design-doc` with the feature name and the human's decomposition as context.

Pass the acceptance scenarios and boundary conditions from State 1 as part of the description. The design-doc skill will expand these into a full design document with motivation, proposed solution, alternatives, and acceptance scenarios in Given/When/Then format.

**Output of this state:** A design doc file in `docs/`.

**Transition:** Immediately move to State 3.

### State 3 — Design Doc Review (Human Decision Point 2)

**Action:** Invoke `blueprint:design-doc-reviewer` on the generated design doc.

Present the reviewer's findings to the human. The reviewer checks:
- Structural completeness
- Testability of each requirement
- Acceptance scenario coverage
- Ambiguous language

Then ask the human to compare against their original decomposition from State 1:
- "Does this cover all the scenarios you had in mind?"
- "Did the AI add anything that seems wrong or out of scope?"
- "Are there boundary conditions you listed that didn't make it into the doc?"

**Output of this state:** An approved (possibly revised) design doc.

**Transition:** When the human approves the design doc (with or without edits), move to State 4.

### State 4 — Test Case Generation (Automated)

**Action:** Invoke `blueprint:test-generator` with the approved design doc.

The test-generator will produce executable test cases, all marked as skipped, organized by phases.

**Output of this state:** A test file (or files) with skipped tests.

**Transition:** Immediately move to State 5.

### State 5 — Test Ordering (Human Decision Point 3)

**Action:** Apply the test-orderer workflow (see the `test-orderer` skill for the full process, or if it's not available, perform the ordering analysis inline).

Present the human with:
1. An inventory table of all generated tests
2. A dependency graph
3. A proposed implementation ordering
4. Any decision points where the ordering is ambiguous

The human's job here is to:
- Confirm or adjust the ordering
- Decide which phases to include in the current iteration (they might cut scope)
- Add any missing degenerate cases the test-generator missed

This is where the "backlog prioritization" skill from TDD courses directly applies — the human controls the rhythm of implementation.

**Output of this state:** An ordered, human-approved test implementation plan.

**Transition:** When the human confirms the ordering, move to State 6.

### State 6 — Implementation (Automated)

**Action:** Invoke `blueprint:implementation-plan` to generate a checklist, then implement the code to make tests pass, following the ordering from State 5.

Work through the ordered test plan one phase at a time:
1. Unskip the tests for the current phase
2. Run the tests (they should fail — Red)
3. Write the minimal code to make them pass (Green)
4. Run the tests again to confirm they pass
5. Move to the next phase

If a test is surprisingly hard to make pass, or if making it pass requires changing the design significantly, **stop and tell the human** rather than silently making large changes.

**Output of this state:** Working code that passes all tests.

**Transition:** After all tests pass, move to State 7.

### State 7 — CI Verification (Automated)

**Action:** Run the full test suite to verify everything passes together.

```bash
# Adapt to the project's actual test command
npm test        # or pytest, go test, etc.
```

If tests fail, diagnose and fix before proceeding. Do not move to refactoring with failing tests.

**Output of this state:** Green CI (all tests passing).

**Transition:** Move to State 8.

### State 8 — Refactoring (Human Decision Point 4)

**Goal:** The human provides refactoring direction; the AI executes it.

Present the human with a brief structural summary of the implementation:
- Which files were created/modified
- Class/function responsibilities
- Any obvious code smells you noticed during implementation (long methods, duplicated logic, unclear names)

Then ask: "What refactoring direction would you like to take? For example:"
- "Extract the validation logic into its own module"
- "Replace the switch statement with a strategy pattern"
- "Rename these functions to better express intent"
- "Split this class — it's doing too much"

**Once the human gives a direction:** Invoke `blueprint:refactor` with that direction. The refactor skill enforces Beck's "two hats" discipline — it changes structure while preserving behavior, verifying tests stay green after each step.

After refactoring, run the full test suite again to confirm nothing broke.

**Output of this state:** Refactored code with all tests still passing.

**Transition:** When CI is green post-refactor, move to State 9.

### State 9 — Post-Refactor CI (Automated)

**Action:** Run the full test suite one more time.

```bash
npm test  # or equivalent
```

This is the safety net confirming the refactoring preserved all behavior.

**Output of this state:** Green CI.

**Transition:** Move to State 10.

### State 10 — Design Scan (Human Decision Point 5)

**Goal:** The human does a quick structural review — not line-by-line code review, but a design-level scan.

Present the human with:
1. **File-level summary** — what files exist, what each one is responsible for
2. **Class/module responsibilities** — one sentence per class/module describing its purpose
3. **Dependency direction** — which modules depend on which (are dependencies flowing in a sensible direction?)
4. **Naming check** — list the key public functions/methods so the human can verify names express intent

Ask:
- "Does the structure make sense at a glance?"
- "Are there any responsibilities that feel misplaced?"
- "Any names that don't clearly communicate what they do?"

If the human identifies issues, loop back to State 8 (Refactoring) with their new direction. Otherwise, the workflow is complete.

**Output of this state:** Human approval of the design.

## Resuming the Workflow

If the user comes back to an in-progress workflow, figure out which state they're in by checking:
- Is there a design doc in `docs/`? → State 3 or later
- Are there test files with skipped tests? → State 5 or later
- Are there test files with unskipped, passing tests? → State 7 or later
- Did they just finish refactoring? → State 10

Ask the human to confirm where they are before resuming.

## Adapting to Context

Not every feature needs all 10 states at full intensity:

- **Small bug fix:** States 1-3 can be light (a few sentences, not a full design doc). States 4-7 are still valuable. States 8-10 might be skippable.
- **Large feature:** All states at full intensity. Consider breaking into sub-features and running the workflow multiple times.
- **Refactoring-only task:** Skip to State 8 directly (but verify tests exist and pass first).

Ask the human upfront: "This workflow has design, testing, implementation, and refactoring phases. Given the size of this feature, do you want the full process or a lighter version?"

## What This Orchestrator Does NOT Do

- It does not replace human judgment. Every decision point exists because that's where human thinking is irreplaceable.
- It does not generate requirements. State 1 guides the human through decomposition, but the human does the thinking.
- It does not skip refactoring. The Red → Green → Refactor cycle is complete or it's not TDD.
- It does not auto-approve design docs. The human must compare against their own baseline.
