# Design-doc rubric (defined 2026-09-12, not yet measured)

Six binary items, taken from `plugins/blueprint/references/review-design.md`
§ "Ready for /spec". Score = items satisfied / 6. Each item is a listing or
quote task for a report-only judge, never a fix.

| # | Item | Judge must quote |
|---|---|---|
| D1 | The decision is stated in the first paragraph ("we propose to X"), not "this doc explores…" | the sentence |
| D2 | At least one alternative is presented with a load-bearing rejection reason (a number, a measured constraint, a named failure), not a hand-wave | the alternative and its reason |
| D3 | At least one downside of the chosen approach is named explicitly | the sentence |
| D4 | The load-bearing assumption is named and the doc says what happens if it breaks | both sentences |
| D5 | Every success criterion has a baseline and a target, or is marked TBD with a measurement plan | each criterion |
| D6 | No open question would, if answered the wrong way, invalidate the design | the open-questions list, with a verdict per question |

## Why it is not measured yet

The FeatureBench harness runs `/spec` only; no design docs exist in it, and
FeatureBench tasks ("restore the stripped feature") rarely contain a real
decision among alternatives for a design doc to argue. Adding a `/design`
pre-stage would be a new treatment arm, not a measurement. Options recorded
in the doc-quality decision (2026-09-12): (a) add the pre-stage as a paired
arm later; (b) score the repo's own `docs/designs/` as a corpus; (c) define
now, measure later — chosen.

## Validation rule when it is measured

Same as the spec metrics: score a corpus whose downstream outcome is already
known, report Spearman ρ against that outcome, and treat any item that
anti-correlates as diagnostic only.
