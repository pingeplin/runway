# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Token counts (input, cache write, cache read, output) come from the same `usage` payload in each source. Arms with no stream file are reported as unmeasured, never as $0 or 0 tokens.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| B | 5/5 | $14.79 | $2.96 | 1 | $14.79 |
| C | 5/5 | $23.74 | $4.75 | 0 | — |
| C0 | 5/5 | $16.16 | $3.23 | 0 | — |

## Per-arm tokens

| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |
|---|---|---|---|---|---|---|---|
| B | 738 | 738,914 | 47,666,192 | 230,253 | 48,636,097 | 9,727,219 | 48,636,097 |
| C | 1,038 | 914,951 | 82,826,378 | 351,280 | 84,093,647 | 16,818,729 | — |
| C0 | 878 | 686,689 | 55,652,830 | 227,807 | 56,568,204 | 11,313,641 | — |

## Host-side stages

| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |
|---|---|---|---|---|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $79.39 | $15.88 | 270 | 346,331 | 6,916,122 | 89,421 | 7,352,144 |
| 06 verdicts (Arm C input) | 5 | $9.26 | $1.85 | 368 | 579,478 | 18,701,809 | 173,674 | 19,455,329 |
| 14 briefs (Arm A_plan input) | 0 | $0.00 | — | 0 | 0 | 0 | 0 | 0 |

**Panel total (measured): $143.34**
