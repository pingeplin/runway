# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Token counts (input, cache write, cache read, output) come from the same `usage` payload in each source. Arms with no stream file are reported as unmeasured, never as $0 or 0 tokens.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| A | 5/5 | $26.42 | $5.28 | 0 | — |
| B | 5/5 | $29.68 | $5.94 | 3 | $9.89 |
| C | 5/5 | $21.69 | $4.34 | 3 | $7.23 |
| C0 | 5/5 | $30.52 | $6.10 | 3 | $10.17 |

## Per-arm tokens

| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |
|---|---|---|---|---|---|---|---|
| A | 918 | 707,101 | 57,974,214 | 318,824 | 59,001,057 | 11,800,211 | — |
| B | 1,120 | 717,232 | 73,962,709 | 212,250 | 74,893,311 | 14,978,662 | 24,964,437 |
| C | 772 | 736,777 | 49,194,914 | 167,014 | 50,099,477 | 10,019,895 | 16,699,826 |
| C0 | 1,074 | 728,862 | 76,500,465 | 212,737 | 77,443,138 | 15,488,628 | 25,814,379 |

## Host-side stages

| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |
|---|---|---|---|---|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $11.48 | $2.30 | 213 | 363,837 | 8,186,755 | 80,651 | 8,631,456 |
| 06 verdicts (Arm C input) | 5 | $9.17 | $1.83 | 348 | 439,567 | 15,628,076 | 120,689 | 16,188,680 |

## Arm A vs Arm B, all-in

- Arm A (inference only): **$26.42**, **59,001,057 tokens**
- Arm B (inference + spec stage): **$41.16** = $29.68 infer + $11.48 spec, **83,524,767 tokens** = 74,893,311 infer + 8,631,456 spec
- Spec overhead: **$14.74** (+56%)
- Token overhead: **24,523,710** (+42%)
- Extra tasks resolved by B: **3** → **$4.91** per extra resolve
- Tokens per extra resolve: **8,174,570**

**Panel total (measured): $128.96**
