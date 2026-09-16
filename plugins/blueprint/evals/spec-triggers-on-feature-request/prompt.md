---
max_turns: 4
runs: 3
timeout_seconds: 240
tags: [triggering]
allowed_tools: [Read, Glob, Grep, Skill]
---

We've already agreed we're adding rate limiting to the public API — token
bucket, per API key, 100 requests a minute, 429 with a `Retry-After` header
when a caller goes over. The approach isn't in question, I just need the
behaviour written down properly before I hand it to someone to build.

Can you get that written up?
