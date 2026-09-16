---
max_turns: 4
runs: 3
timeout_seconds: 240
tags: [triggering, routing]
allowed_tools: [Read, Glob, Grep, Skill]
---

We need to decide how our services talk to each other. Right now everything
is synchronous HTTP and the coupling is hurting us, but moving to an event
bus means we take on ordering and replay problems we don't have today. The
team is split and nobody has written the argument down.

Help me work out which way we should go and make the case for it.
