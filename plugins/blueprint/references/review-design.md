# Design Doc Review Methodology

Review a design doc as a skeptical reviewer would — for argument strength, not section completeness. A doc with every section but no real argument fails. A doc missing sections but making a sharp case succeeds. Judge the argument first.

Apply these phases in order.

## Phase 1 — Decision Clarity

A reviewer should be able to read the first paragraph and know what's being proposed and what they'd be approving. Check:

1. **Is the decision findable in the first paragraph?** Not "this doc explores options for X" but "we propose to do X."
2. **Is it one decision, or a bundle?** Multi-decision docs are unreviewable because reviewers can't approve some parts and reject others. Flag if the doc bundles independent decisions.
3. **Is the doc type matched to the situation?** An RFC for a settled decision is theatre; an ADR for an open decision is premature. If a mismatch is obvious, flag.

**Autonomous fixes:** Hoist a buried TL;DR to the top if the content exists further down. Add a missing doc-type header.

**Flag for human:** Decision absent, or doc clearly bundling independent decisions.

## Phase 2 — Alternative Quality

This is where most docs fail. Real alternatives have plausible champions; straw men are dismissed in two lines with weak reasons. Apply this test:

> If you removed the chosen solution and asked someone to pick from the alternatives alone, would any be defensible?

If no, the alternatives are straw men.

For each alternative, check:

1. **Is it presented with its genuine merits, not just its cons?**
2. **Is the rejection reason load-bearing, or hand-wave?** "Doesn't scale" without numbers is hand-wave. "Hits ~400ms in our benchmark, target is <200ms" is load-bearing.
3. **Is the comparison made *given the constraints*?** Alternatives often look bad when stripped of context.

**Autonomous fixes:** None — you cannot strengthen an alternative without technical judgment.

**Flag for human:** Any alternative that reads as a straw man. Specifically: "Alternative N (`{name}`) is dismissed for `{reason}` — is this dismissal fair? If yes, please add the evidence behind it; if no, this alternative may be the right choice."

## Phase 3 — Trade-off Honesty

Real engineering choices have downsides. If every section says the chosen option wins, the author either hasn't thought about what they're giving up or is hiding it.

Check:

1. **Is there a one-sentence trade-off statement somewhere?** "We chose X over Y because we value [A] more than [B] given [constraint]."
2. **Is at least one downside of the chosen approach named explicitly?** Operational complexity, cost, future flexibility, latency, team learning curve — something concrete.
3. **Does the "Trade-offs" section (if present) actually take a position?** Listing trade-offs without picking sides ("we could do X or Y; both have merits") is completionism, not argument.

**Autonomous fixes:** If a downside is mentioned implicitly elsewhere (e.g., in "Risks" or "Open Questions") but not surfaced in a trade-off statement, hoist it.

**Flag for human:** No downside named anywhere. "The chosen approach reads as dominant on every axis — what are we giving up?"

## Phase 4 — Load-bearing Assumption

Every design rests on something. Read-write ratio, traffic shape, data size, upstream system behavior, team capacity, regulatory window. If the assumption is wrong, the design needs to change. If it's not stated, future readers won't know to watch for it breaking.

Check:

1. **Is at least one load-bearing assumption named explicitly?** "Key assumption: read traffic outnumbers write traffic by ~100:1."
2. **Is it justified?** Numbers, prior data, stakeholder confirmation.
3. **Does the doc say what happens if the assumption breaks?** "If write volume grows past X, we'd revisit the cache-aside choice."

**Autonomous fixes:** If a load-bearing assumption is stated implicitly (e.g., in problem-statement numbers) but never called out, add a "Key Assumption" section that names it explicitly.

**Flag for human:** No assumption findable. "I can't identify the load-bearing assumption from the draft — what would force a rewrite if it turned out to be wrong?"

## Phase 5 — Success Criteria & Specificity

A design that cannot fail cannot succeed. Six months later, no one should have to argue about whether the project worked.

Check:

1. **Does every success metric have a baseline, a target, and a measurement plan?** Not "improve performance" — "p95 latency baseline 850ms → target <200ms, measured 30 days post-launch."
2. **Are problem statements quantified?** "Search is slow" is not reviewable. "p95 800ms" is.
3. **Are adjectives doing the work numbers should?** Scan for "fast," "scalable," "reliable," "performant," "robust" used without quantification.

**Autonomous fixes:** Tighten a vague metric if a concrete baseline appears elsewhere in the doc. Replace adjective-only claims with the numeric form when the numbers are present in the doc body.

**Flag for human:** Adjective-only success criteria when no numbers are available. "Success metric '{metric}' is qualitative — what's the baseline and target?"

## Phase 6 — Ambiguity, Scope, and Completionism

A final scan for the small failure modes that compound:

1. **Hedging language.** "Should," "might," "ideally," "as appropriate," "etc." — flag instances and rewrite to commitments where the doc's other content makes the commitment unambiguous.
2. **Scope creep.** Doc starts about caching, ends up redesigning the data model. Check whether the proposed approach has expanded beyond the problem statement.
3. **Out-of-scope section.** If scope creep is detected and no "Out of Scope" section exists, add one with the specific exclusions you observed.
4. **Open questions as escape hatches.** Any open question that, if answered wrong, would invalidate the design. Those aren't open questions; they're unaddressed risks.
5. **Template completionism.** Sections filled in without committing to a position. Headings that restate themselves as the first sentence. Flag for the human to either rewrite or delete.
6. **Implementation in disguise.** Pages of class hierarchies, helper functions, or detailed sequencing that belong in code, not the doc. Flag.

**Autonomous fixes:** Tighten hedging language where the doc commits unambiguously elsewhere. Add "Out of Scope" header with observed exclusions. Tighten self-referential headings.

**Flag for human:** Open questions that look design-invalidating. Implementation-in-disguise sections (suggest moving to code review).

## Phase 7 — Summary

Output:

- **Argument strength:** High / Medium / Low
- **Critical issues blocking /spec:** numbered list, or "None"
- **Improvement suggestions:** ranked, structural first
- **Ready for /spec:** Yes / Yes, after resolving the above / No — fundamental rework needed
- **Suggested next step:** one concrete action

A doc is **Ready for /spec** when:

- The decision is findable in the first paragraph
- At least one real alternative is present with a load-bearing rejection reason
- At least one downside of the chosen approach is explicit
- The load-bearing assumption is named
- Success criteria are quantified (or marked as TBD with a planned measurement)
- No design-invalidating questions are left in "open questions"

A doc that meets these can be translated into testable acceptance scenarios by `/spec`. A doc that doesn't is not yet an argument — it's a draft of one.
