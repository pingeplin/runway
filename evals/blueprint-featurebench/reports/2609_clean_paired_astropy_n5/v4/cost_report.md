# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Token counts (input, cache write, cache read, output) come from the same `usage` payload in each source. Arms with no stream file are reported as unmeasured, never as $0 or 0 tokens.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| B | 5/5 | $19.20 | $3.84 | 1 | $19.20 |

## Per-arm tokens

| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |
|---|---|---|---|---|---|---|---|
| B | 994 | 725,714 | 69,956,423 | 230,635 | 70,913,766 | 14,182,753 | 70,913,766 |

## Host-side stages

| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |
|---|---|---|---|---|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $79.39 | $15.88 | 270 | 346,331 | 6,916,122 | 89,421 | 7,352,144 |
| 06 verdicts (Arm C input) | 0 | $0.00 | — | 0 | 0 | 0 | 0 | 0 |

**Panel total (measured): $98.59**
