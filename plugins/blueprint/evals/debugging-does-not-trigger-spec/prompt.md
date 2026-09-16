---
max_turns: 4
runs: 3
timeout_seconds: 240
tags: [triggering, negative]
allowed_tools: [Read, Glob, Grep, Skill]
---

Our checkout endpoint intermittently double-charges. It only shows up under
load, and only when the payment provider's webhook lands before our own
transaction commits. I think it's a race between the webhook handler and the
order-finalisation path, but I haven't pinned it down.

Where would you start looking?
