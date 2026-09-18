# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Token counts (input, cache write, cache read, output) come from the same `usage` payload in each source. Arms with no stream file are reported as unmeasured, never as $0 or 0 tokens.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| B | 5/5 | $24.70 | $4.94 | 1 | $24.70 |

## Per-arm tokens

| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |
|---|---|---|---|---|---|---|---|
| B | 1,000 | 959,537 | 78,713,946 | 511,481 | 80,185,964 | 16,037,193 | 80,185,964 |

## Host-side stages

| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |
|---|---|---|---|---|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $56.91 | $11.38 | 286 | 323,377 | 17,923,317 | 132,524 | 18,379,504 |
| 06 verdicts (Arm C input) | 0 | $0.00 | — | 0 | 0 | 0 | 0 | 0 |
| 14 briefs (Arm A_plan input) | 0 | $0.00 | — | 0 | 0 | 0 | 0 | 0 |

**Panel total (measured): $81.61**
