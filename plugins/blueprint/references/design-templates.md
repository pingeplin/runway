# Design Doc Templates

Starting templates for the most common design-doc formats. **These are scaffolds, not goals.** Keep sections that carry argument; delete sections that don't apply. The structural spine in `/design`'s SKILL.md is what matters; these are convenient starting shapes.

If the user's organization has its own template, prefer that — local conventions win.

Every template should begin with the standard blueprint header:

```markdown
# {yymm.xxxx} {Title}

**Date:** YYYY-MM-DD · **Status:** draft · **Author:** {name}
**Doc type:** {Mini RFC | RFC | ADR | Feature Doc | SDD | PR/FAQ}
```

---

## Mini RFC (small, team-scoped change)

For changes where the decision is small enough that ~1 page is enough. Adding an index, switching a library, changing a config default.

```markdown
## Problem
[2-3 sentences: what's broken, with numbers if relevant]

## Proposed change
[The decision, in one paragraph]

## Why this and not the alternatives
[1-2 alternatives considered, why each was rejected. Keep this short but real.]

## Trade-offs accepted
[What this costs us — perf, complexity, future flexibility]

## Success criteria
[How we'll know it worked, with concrete numbers]

## Plan
[Rollout steps, including any rollback]
```

---

## RFC / Design Doc (decision-making, cross-team or high-stakes)

For changes that need approval from people outside the immediate team, or where the chosen approach has real downsides that need debate. Aim for 3-7 pages — longer than that and reviewers will skim.

```markdown
**Approvers:** [Names with explicit decision authority]
**Reviewers:** [Names — feedback welcome]

## TL;DR
[One paragraph. The decision being proposed and the load-bearing trade-off.
A reviewer should be able to stop here and know what they'd be approving.]

## Problem
[What's wrong in the world. Evidence — numbers, incident reports, user research.
Why it matters, why now.]

## Constraints
[Deadlines, existing systems, headcount, regulatory, political. The reasons
the obvious answer doesn't work.]

## Proposed approach
[High-level architecture or change. Just enough detail to evaluate the
decision — interfaces, key components, data flow. Not implementation.]

## Alternatives considered
[Real alternatives, presented with their genuine merits. For each: what it is,
what's good about it, and why it loses to the proposed approach *given the
constraints*. If you can't make an alternative sound defensible, it's a
straw man — drop it or work harder.]

## Trade-offs
[What the proposed approach costs us. State at least one downside explicitly.
"We're accepting [X] in order to gain [Y]." If you can't write this sentence,
the design isn't ready for review.]

## Key assumption
[The thing this design rests on. If this assumption is wrong, the design
needs to change. Examples: read/write ratio, traffic shape, data size,
upstream system behavior, team capacity.]

## Out of scope
[Bounded explicitly. Prevents the review from sprawling.]

## Success metrics
[Concrete, with baselines and targets. "p95 latency baseline 850ms → target <200ms"
not "improve performance".]

## Implementation plan
[Phasing if multi-stage. Dependencies on other teams. Rollout/rollback strategy
for anything risky.]

## Risks
[Things that could go wrong, with mitigations. Distinct from the "key assumption"
section: those are design-invalidating; these are operational.]

## Open questions
[Genuinely small things to resolve in review. NOT escape hatches for
unresolved design decisions.]
```

---

## Feature Doc (implementation alignment, decision mostly settled)

For features where the team has agreed roughly what to build and the doc helps everyone build the same thing. Less emphasis on alternatives; more on the user-facing contract and edge cases.

```markdown
## Summary
[What we're building, who it's for, why now]

## Success criteria
[How we'll know the feature is working — usage, business metrics, qualitative]

## User-facing behavior

### What the user does
[User flows. The happy path in plain language.]

### What the system does in response
[State changes, side effects, downstream events]

### Edge cases
[Specific cases that need explicit decisions. e.g., "what if the user is
logged out?", "what if the product is out of stock when they share?"]

## Technical design

### Data model changes
[New tables/columns, migrations]

### API changes
[Endpoint signatures, request/response shapes — the contract, not impl]

### Dependencies
[Internal services, third-party APIs, design assets, copy]

## Out of scope
[Explicitly]

## Rollout
[Feature flag? Gradual rollout? A/B test? Anything risky here?]

## Open questions
[Things needing product/design/eng decisions before build]
```

---

## SDD (System Design Document — multi-component system)

For new systems or major architectural changes. Longer than an RFC; emphasis on architecture, data flow, and operational concerns. Use when the design touches multiple services, has migration complexity, or needs to convince a broader audience.

Same structure as the RFC template above, plus these sections:

```markdown
## System architecture

### Components
[List the major components and their responsibilities. Each should be one
sentence — if you need a paragraph, break it out as a subsection.]

### Architecture diagram
[The high-level picture. ASCII art is fine; clarity matters more than tooling.]

### Data flow
[How data moves through the system. Often easier as a sequence than a diagram.]

## Detailed design

### Data models
[Schemas, key fields, relationships]

### API specifications
[Service-to-service contracts]

### Security
[Authn/authz, data classification, threat model if relevant]

## Operations

### Deployment
[Environment topology, rollout strategy]

### Observability
[Key metrics, alerts, dashboards]

### Failure modes and recovery
[What breaks, how we detect it, how we recover]

### Capacity / scaling
[Expected load, scaling levers, cost model]
```

---

## ADR (Architecture Decision Record — capturing a decision after the fact)

When the decision has been made and you want to record *why* for future readers. Should be terse — a few paragraphs — and immutable once written. New decisions get new ADRs that supersede old ones.

```markdown
## Context
[The situation that forced a decision. Constraints. Why we couldn't avoid choosing.]

## Decision
[What we decided. One sentence ideally.]

## Consequences
[What this means going forward — positive and negative. The trade-off accepted.]
```

---

## PR/FAQ (Amazon-style working backwards)

Use when the customer/user value is in doubt. The exercise of writing the press release first surfaces whether the project is worth doing.

```markdown
## Press release (written as if launched)

**Headline:** [Customer-facing announcement]

**Subheadline:** [One-line elaboration]

**Body:**
[3-4 paragraphs from the customer's perspective. What problem does it solve?
What's their experience? Quote from a hypothetical customer. Quote from the
team about why we built this.]

## FAQ

### External (customer questions)
- Q: How is this different from [existing thing]?
- Q: How much does it cost?
- Q: What's the experience on mobile?

### Internal (engineering / business)
- Q: What does this cost to build?
- Q: What are the technical risks?
- Q: How does this affect [adjacent product]?
- Q: What's the business case?
```

---

## Notes on adapting these

- **Drop sections that don't apply.** A doc with "N/A" sections is worse than one without those sections.
- **Add sections the spine demands but the template missed.** If your design's load-bearing assumption is something the template doesn't have a slot for, write it in anyway under its own heading.
- **Right-size the doc.** Two pages for a small change beats a forced 10-page template.
- **Match local convention.** If your team's existing docs look different, mimic them. Reviewers are calibrated on what they're used to.
