---
name: proto
description: Rapid prototyping orchestrator. Skips spec, generates a happy-path-only plan, runs it fast, then asks whether to promote to a full /tdd workflow or discard. Use for spikes, experiments, "does this even work?" explorations, or when the user says "prototype", "spike", "try", "experiment", or "explore".
---

If invoked **without arguments**, display this and ask what the user wants to explore:

```
Blueprint Prototype Mode

/proto ──→ lightweight /plan ──→ /run ──→ promote or discard
               │                   │
               no spec             no verification
               happy path only     no refactor
```

If invoked **with a description** (e.g., `/proto "try WebSocket instead of polling"`), begin immediately.

## How proto differs from /tdd

| | /tdd | /proto |
|---|---|---|
| Spec | Required (with self-review) | Skipped |
| Plan scope | Full: all scenarios, edge cases, errors | Happy path only: 1 stream, no edge cases |
| REFACTOR nodes | Included | Skipped |
| Human gates | After spec, after plan | After plan only |
| Verification | Auto-verify against spec | No verification (there is no spec) |
| Goal | Build it right | Find out if it works |

## Workflow

### Step 1: Lightweight /plan

Invoke `/plan` with these overrides:

- **No spec required** — use the user's description directly as input
- **Happy path only** — generate tests for the core behavior only. No edge cases, no error scenarios, no invariants.
- **Single stream** — keep it simple. 2-4 triplets maximum.
- **Skip REFACTOR nodes** — mark all as "(skip)". Structure doesn't matter in a prototype.
- **Skip Phase 5 self-review** — no spec to check coverage against, and completeness is not the goal.
- **Skip desiderata self-review** — speed over rigor.

The plan should be minimal — just enough to prove the concept works.

**GATE — Present the plan. Ask: "Run this spike, or adjust?"**

### Step 2: /run

Invoke `/run` with the plan. Since it's a single stream with no REFACTOR nodes, execution is always sequential and fast.

**Override for proto mode:**
- Skip auto-verification (there is no spec to verify against)
- After all GREEN nodes pass, report success directly

### Step 3: Decide

After execution completes, present the outcome and ask:

```
Spike complete. All tests passing.

Files created/modified:
  - {list of files}

What next?
  (a) Promote → run /spec to formalize, then /tdd for the full workflow
  (b) Iterate → adjust and run /proto again
  (c) Discard → revert changes
```

If the user chooses **(a) Promote**:
- Suggest `/spec "{feature name}"` — the prototype code and tests provide context for writing a proper spec
- The existing test file can serve as a starting point for `/plan`'s behavioral analysis
- The prototype code stays as-is until `/run` replaces it with properly tested implementation

If the user chooses **(c) Discard**:
- Confirm before reverting: "This will undo all changes from this spike. Proceed?"
- Run `git checkout -- {files}` to revert, or `git stash` to save for later
