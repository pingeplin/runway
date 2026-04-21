---
name: proto
description: Rapid prototyping orchestrator for quick spikes and experiments. ALWAYS use this when the user wants to prototype, spike, experiment, explore, or try something out quickly. Trigger on "try X real quick", "spike — does X work?", "let's experiment with X", "explore whether X is feasible", "prototype X", "quick proof of concept", "does this even work?", "just want to see if X works", or any request to quickly test an idea or approach before committing to a full implementation.
---

If invoked **without arguments**, display this and ask what the user wants to explore:

```
Blueprint Prototype Mode

/proto ──→ discover ──→ test ──→ implement ──→ promote or discard
              │           │          │
              read code   2-4 tests  RED-GREEN only
              no spec     happy path no refactor
```

If invoked **with a description** (e.g., `/proto "try WebSocket instead of polling"`), begin immediately.

## How proto differs from /tdd

| | /tdd | /proto |
|---|---|---|
| Spec | Required (with self-review) | Skipped |
| Plan file | Execution graph with streams | None — tests are generated inline |
| Scope | All scenarios, edge cases, errors | Happy path only: 2-4 tests |
| REFACTOR | Included | Skipped |
| Human gates | After spec, after plan | Before implementation only |
| Verification | Auto-verify against spec | None (there is no spec) |
| Goal | Build it right | Find out if it works |

## Workflow

### Step 1: Discover

Read the codebase to understand:

- Existing test framework and conventions (naming, directory, imports)
- Modules and files relevant to the user's description
- Data models, APIs, or interfaces the prototype will touch

This is quick reconnaissance, not deep analysis. Spend minimal time here.

### Step 2: Generate happy-path tests

Write 2-4 skipped tests directly to a test file. No plan file, no graph, no streams.

**Rules:**
- **Happy path only** — test the core "does it work?" behavior. No edge cases, no error handling, no boundary conditions.
- **Follow project conventions** — match the existing test framework, naming, and directory structure.
- **All tests skipped** — use the framework's skip marker with a behavioral description.
- **AAA structure** — Arrange/Act/Assert, inline setup, no shared fixtures.
- **Behavioral** — test observable output, not internals.

Example output:

```python
# tests/test_websocket_updates.py

@pytest.mark.skip(reason="client receives live update via WebSocket")
def test_client_receives_live_update():
    ws = WebSocketClient("ws://localhost/updates")
    ws.connect()
    trigger_update(item_id=1, status="shipped")
    message = ws.receive(timeout=2)
    assert message["item_id"] == 1
    assert message["status"] == "shipped"

@pytest.mark.skip(reason="multiple clients receive the same update")
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

### Step 3: RED-GREEN loop

For each test, sequentially:

1. **RED** — Unskip the test. Run it. Expect failure.
   - If it passes unexpectedly: flag it ("already implemented or trivially true")
2. **GREEN** — Write the minimal code to make it pass. Run all tests. Expect all green.
   - If it fails after 2 attempts: stop and report the issue.

No REFACTOR step. Structure doesn't matter in a prototype.

Show progress:
```
[1/3] RED  — test_client_receives_live_update — FAILED (expected)
[1/3] GREEN — implemented WebSocketHandler — ALL PASSING
[2/3] RED  — test_multiple_clients_receive_broadcast — FAILED (expected)
[2/3] GREEN — added broadcast logic — ALL PASSING
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
