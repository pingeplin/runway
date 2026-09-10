# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Token counts (input, cache write, cache read, output) come from the same `usage` payload in each source. Arms with no stream file are reported as unmeasured, never as $0 or 0 tokens.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| B | 5/5 | $19.78 | $3.96 | 1 | $19.78 |

## Per-arm tokens

| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |
|---|---|---|---|---|---|---|---|
| B | 994 | 822,772 | 67,690,013 | 294,530 | 68,808,309 | 13,761,662 | 68,808,309 |

## Host-side stages

| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |
|---|---|---|---|---|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $76.82 | $15.36 | 576 | 905,993 | 43,404,779 | 427,731 | 44,739,079 |
| 06 verdicts (Arm C input) | 0 | $0.00 | — | 0 | 0 | 0 | 0 | 0 |

**Panel total (measured): $96.59**
