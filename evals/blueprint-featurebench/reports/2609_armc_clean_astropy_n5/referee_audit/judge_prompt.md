You are auditing a code referee. A referee read an implementation patch against its spec and wrote a verdict. You will score the verdict against ground truth. You have no tools; everything you need is below. Be literal and conservative: only mark something TRUE, YES or CAUGHT when the evidence below shows it.

## Inputs

- **VERDICT** — the referee's report on the BASE patch.
- **BASE PATCH** — the implementation the referee judged.
- **BASE FAILURES** — hidden acceptance tests the BASE patch fails, clustered by the exception that failed them. The referee never saw these.
- **REFERENCED TEST SOURCES** — source of tests the verdict names, where they could be located.
- **PATCH X** and **PATCH Y** — two later, independent re-implementations of the same task. Their order is random. Do not guess how they were produced.

## Task A — the referee's claims

Enumerate the verdict's distinct, actionable criticisms from its headline, anti-vacuity, implementation-quality and punch-list sections. Merge duplicates. Do not list positive assessments ("reads as correct") and do not list individual coverage-matrix rows — a punch-list item that groups scenarios is one claim. At most 15 claims.

For each claim:
- `kind`: `impl_defect` (the base code is wrong or missing something), `vacuous_test` (a named test cannot fail or asserts nothing meaningful), `missing_tests` (behaviour has no test), or `other`.
- `accuracy_on_base`: `TRUE` if the BASE PATCH or the REFERENCED TEST SOURCES confirm it; `FALSE_POSITIVE` if they contradict it; `UNVERIFIABLE` if the inputs cannot settle it.
- `addressed_in_X` / `addressed_in_Y`: `YES`, `PARTIAL`, `NO`, or `N_A` (claim was not TRUE). Judge from the patch content only.

## Task B — what actually broke

For each BASE FAILURES cluster, decide whether the verdict identified its cause:
- `YES` — names the missing or broken symbol/behaviour that the exception points to.
- `PARTIAL` — points at the right file or area but not the defect.
- `NO` — not mentioned, or the verdict calls that area correct.

## Output

Return ONLY one JSON object, no prose, no code fence:

{"claims":[{"id":"K1","kind":"impl_defect","claim":"<=25 words","accuracy_on_base":"TRUE","accuracy_evidence":"<=40 words citing file/function/test","addressed_in_X":"YES","addressed_in_Y":"NO","addressed_evidence":"<=40 words"}],"failure_clusters":[{"cluster":"F1","caught":"NO","evidence":"<=25-word verdict quote, or 'not mentioned'"}]}
