# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Arms with no stream file are reported as unmeasured, never as $0.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| A | 5/5 | $26.42 | $5.28 | 0 | — |
| B | 5/5 | $29.68 | $5.94 | 3 | $9.89 |
| C | 5/5 | $21.69 | $4.34 | 3 | $7.23 |
| C0 | 5/5 | $30.52 | $6.10 | 3 | $10.17 |

## Host-side stages

| stage | tasks | cost | mean/task |
|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $11.48 | $2.30 |
| 06 verdicts (Arm C input) | 5 | $9.17 | $1.83 |

## Arm A vs Arm B, all-in

- Arm A (inference only): **$26.42**
- Arm B (inference + spec stage): **$41.16** = $29.68 infer + $11.48 spec
- Spec overhead: **$14.74** (+56%)
- Extra tasks resolved by B: **3** → **$4.91** per extra resolve

**Panel total (measured): $128.96**
