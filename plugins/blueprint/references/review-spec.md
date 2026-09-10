# Spec Review Methodology

Review a technical spec for structural completeness, testability, and clarity. Apply these phases in order.

## Phase 1 — Structural Completeness

Check the spec against the standard template sections (Context, Motivation, Proposed Solution, Interface Contract, Acceptance Scenarios, For the Implementing Agent, Definition of Done, Alternatives Considered, Trade-offs and Limitations, Open Questions). Report a table of present/missing sections with assessment notes. If the spec uses a non-standard structure, adapt — focus on content presence, not heading names.

Because the spec is the **executable contract handed to a coding agent**, treat these three as load-bearing, not optional polish:

- **Interface Contract** — the API/error/breaking-change surface the agent must honor (inherited from the design doc when one exists).
- **For the Implementing Agent** — the explicit build instruction ("make every scenario pass with tests that would fail if the behavior were wrong") plus the test-quality principles.
- **Definition of Done** — the `/verify` pass criteria restated as a checklist. Flag its absence as a critical gap: without it, there's nothing for the referee to check the result against.

## Phase 2 — Testability Analysis

The highest-value phase. For each requirement or behavior in the spec, evaluate whether it can be tested using Beck's behavioral testing principles.

**For each requirement, ask:**

1. **Is it behavioral?** Does it describe WHAT the system does (observable output/state change), or HOW it works (implementation detail)?
   - Good: "Returns a 404 when the resource doesn't exist"
   - Bad: "Uses a HashMap for O(1) lookup" (implementation detail, not testable behavior)

2. **Is it specific enough to write a test?** Can you derive a Given/When/Then scenario from it?
   - Good: "Expired coupons are rejected with a validation error"
   - Bad: "Handles errors gracefully" (too vague — which errors? what's graceful?)

3. **Is it structure-insensitive?** Can you verify it without knowing the internal architecture?
   - Good: "Search returns results ranked by relevance"
   - Bad: "The cache is invalidated when data changes" (requires knowing cache exists)

**Output a testability scorecard:**

```
#### Fully Testable Requirements
- [Requirement]: can be verified via [approach]

#### Needs Clarification (vague or ambiguous)
- [Requirement]: unclear because [reason]. Suggest: [specific question]

#### Implementation-Coupled (rewrite needed)
- [Requirement]: describes HOW not WHAT. Suggest rewriting as: [behavioral version]

#### Untestable (missing interface)
- [Requirement]: cannot be verified without accessing internals. Consider: [interface suggestion]
```

## Phase 3 — Acceptance Scenario Audit

If the spec includes Acceptance Scenarios, audit them:

1. **Coverage check** — Map each behavior from Proposed Solution to at least one scenario. Flag behaviors without scenarios.
2. **Scenario quality** — Each scenario should follow Given/When/Then and describe observable behavior. Flag scenarios that assert implementation details (method calls, internal state, call order).
3. **Missing edge cases** — Check for common gaps:
   - Empty/null/missing inputs
   - Boundary values (0, 1, max)
   - Concurrent operations
   - Permission/authorization boundaries
   - Timeout and failure modes
   - Unicode / special characters (where applicable)
4. **Redundant scenarios** — Flag scenarios that test the same behavior with trivially different inputs.

If no Acceptance Scenarios section exists, flag this as a critical gap.

**Scope completeness — read the touched files (always, whether or not a scenarios section exists).** For every file the spec touches, open it. Anything referenced-but-undefined, stubbed, or missing that the feature's code path or its tests would reach is goal-related scope the spec does not cover: report it as an `uncovered` finding with `Fix: add as prerequisite or scenario, marked [INFERRED]`. The fix is never `mark out of scope`. A spec that fences such an item off ("do not restore", "leave as-is", "out of scope for this work") has a `contradiction` finding with `Fix: remove the fence and cover it` — see the scope rule in `references/loop.md`.

## Phase 4 — Ambiguity and Contradiction Detection

Scan for:

- **Ambiguous language** — "should", "might", "ideally", "as appropriate", "etc." — these create undefined behavior that leads to undertested code. Resolve by committing to inclusion whenever the goal, the code path, and the existing tests determine the behavior (an `uncovered` finding); route to the human only when resolving it means choosing among behaviors the goal leaves open (a `behavior-change` finding).
- **Out-of-scope entries that are not declined decisions** — an "Out of Scope" / "not in scope" / "do not restore" entry is valid only when it records a `behavior-change` decision a human declined; any other such entry is a `contradiction` finding (`Fix: remove the fence and cover it`).
- **Contradictions** — Two sections that imply different behavior for the same scenario
- **Implicit requirements** — Behaviors implied by the design but never stated (e.g., creation described but duplicate creation unaddressed)
- **Missing error handling** — Happy path described but failure modes absent

## Phase 5 — Coherence

Read the spec as a document, not a checklist. This is where contradictions and muddled wording hide:

1. **One term per concept.** The same agent, artifact, or state is called one thing throughout. Flag any pair of names used for one concept (e.g. "referee" and "verifier").
2. **Scenario IDs match the Definition of Done.** Every scenario ID the Definition of Done cites exists, and every scenario is reachable from the Definition of Done.
3. **Section order serves a first-time reader.** Contract before scenarios, scenarios before done-criteria; nothing is used before it is introduced.
4. **One claim per sentence.** Flag sentences that bundle two behaviors or hedge one behind another.
5. **No section restates another.** Flag paragraphs that repeat an earlier section in different words instead of adding to it.

## Phase 6 — Spec Summary

Output: overall testability (High/Medium/Low), critical issues blocking downstream work, improvement suggestions, and a **Ready for handoff** verdict (Yes/No with conditions) — i.e., is this a self-contained, referee-able contract a coding agent could build against and `/verify` could check?
