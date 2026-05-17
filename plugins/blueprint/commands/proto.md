---
name: proto
description: Rapid prototyping orchestrator for quick spikes and experiments. ALWAYS use this when the user wants to prototype, spike, experiment, explore, or try something out quickly. Trigger on "try X real quick", "spike — does X work?", "let's experiment with X", "explore whether X is feasible", "prototype X", "quick proof of concept", "does this even work?", "just want to see if X works", or any request to quickly test an idea or approach before committing to a full implementation.
---

If invoked **without arguments**, display this and ask what the user wants to explore:

```
Blueprint Prototype Mode

/proto ──→ discover ──→ test ──→ implement ──→ promote or discard
              │           │          │
              read code   2-4 tests  one batched pass
              no spec     happy path no commit, no refactor
```

If invoked **with a description** (e.g., `/proto "try WebSocket instead of polling"`), begin immediately.

## How proto differs from /tdd

| | /tdd | /proto |
|---|---|---|
| Spec | Required (with self-review) | Skipped |
| Plan file | Slice-based execution graph | None — tests are generated inline |
| Scope | All scenarios, edge cases, errors | Happy path only: 2-4 tests |
| Test-batch evaluator | Yes, per slice | Skipped |
| Failing-test commit | Yes, per slice | Skipped |
| REFACTOR | Standalone /refactor at the end | Skipped |
| Human gates | After spec, after plan | Before implementation only |
| Verification | run-evaluator at the end | None (there is no spec) |
| Goal | Build it right | Find out if it works |

`/proto` is structurally one slice with all the safety nets stripped — no spec, no plan, no evaluators, no commits. If the spike works and you want to keep it, promote it to `/tdd`.

## Workflow

### Step 1: Discover

Read the codebase to understand:

- Existing test framework and conventions (naming, directory, imports)
- Modules and files relevant to the user's description
- Data models, APIs, or interfaces the prototype will touch

This is quick reconnaissance, not deep analysis. Spend minimal time here.

### Step 2: Generate happy-path tests

Write 2-4 active tests directly to a test file. No plan file, no graph, no streams, no skip markers.

**Rules:**
- **Happy path only** — test the core "does it work?" behavior. No edge cases, no error handling, no boundary conditions.
- **Follow project conventions** — match the existing test framework, naming, and directory structure.
- **Tests are active, not skipped** — write the tests as you would for any real run; they will fail collectively in Step 3 because the implementation doesn't exist yet. (This aligns `/proto` with `/run`'s slice loop; v3.4 dropped the skip-marker convention.)
- **AAA structure** — Arrange/Act/Assert, inline setup, no shared fixtures.
- **Behavioral** — test observable output, not internals.

Example output:

```python
# tests/test_websocket_updates.py

def test_client_receives_live_update():
    ws = WebSocketClient("ws://localhost/updates")
    ws.connect()
    trigger_update(item_id=1, status="shipped")
    message = ws.receive(timeout=2)
    assert message["item_id"] == 1
    assert message["status"] == "shipped"

def test_multiple_clients_receive_broadcast():
    ws1 = WebSocketClient("ws://localhost/updates")
    ws2 = WebSocketClient("ws://localhost/updates")
    ws1.connect()
    ws2.connect()
    trigger_update(item_id=1, status="shipped")
    assert ws1.receive(timeout=2)["item_id"] == 1
    assert ws2.receive(timeout=2)["item_id"] == 1
```

**Present the tests to the user. Ask: "Run this spike, or adjust?"**

### Step 3: Verify-and-implement

1. **Run the suite via `Bash`.** Expected: every new test fails / errors-as-not-implemented. Pre-existing tests remain green.
   - If a new test passes unexpectedly: flag it ("already implemented or trivially true").
   - If a pre-existing test breaks: stop and report — the spike introduced an unrelated issue.

2. **Write the minimal implementation** to make all spike tests pass. One pass — don't dribble tests in.

3. **Run the suite again.** All spike tests should pass.

4. **Bounded fix loop** if some still fail: up to 3 attempts of production-code edits. Do NOT edit the tests. If still failing after 3 attempts, stop and report — the spike may not be feasible as conceived.

No REFACTOR step. Structure doesn't matter in a prototype.

Show progress:
```
[batch] 3 tests written — running suite
[batch] 3/3 failing as expected — implementing
[batch] Implementation written — running suite
[batch] 3/3 passing — spike complete
```

### Step 4: Decide

After all tests pass, present the outcome:

```
Spike complete. All tests passing.

Files created/modified:
  - {list of files}
Tests:
  - {list of test names}

What next?
  (a) Promote → run /spec to formalize, then /tdd for the full workflow
  (b) Iterate → adjust and run /proto again
  (c) Discard → revert changes
```

**If (a) Promote:**
- Suggest `/spec "{feature name}"` — the prototype code and passing tests give concrete context for writing a proper spec
- The existing tests can inform `/plan`'s behavioral analysis
- The prototype code stays until `/run` replaces it with a fully tested implementation

**If (b) Iterate:**
- Ask what to change, then repeat from Step 2 with adjusted tests

**If (c) Discard:**
- Confirm: "This will undo all changes from this spike. Proceed?"
- Run `git checkout -- {files}` to revert, or `git stash` to save for later
