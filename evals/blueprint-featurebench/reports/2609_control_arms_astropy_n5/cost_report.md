# Cost ledger

In-container inference cost is read from each task's Claude Code stream-json (`total_cost_usd` on the terminal `result` event); host stages from their `.meta.json` sidecars. Token counts (input, cache write, cache read, output) come from the same `usage` payload in each source. Arms with no stream file are reported as unmeasured, never as $0 or 0 tokens.

## Per-arm inference

| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |
|---|---|---|---|---|---|
| A | 5/5 | $12.74 | $2.55 | 2 | $6.37 |
| A_hint | 5/5 | $25.37 | $5.07 | 1 | $25.37 |
| A_plan | 5/5 | $10.63 | $2.13 | 0 | — |
| B | 5/5 | $25.52 | $5.10 | 0 | — |

## Per-arm tokens

| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |
|---|---|---|---|---|---|---|---|
| A | 722 | 587,329 | 40,439,557 | 230,348 | 41,257,956 | 8,251,591 | 20,628,978 |
| A_hint | 1,150 | 872,174 | 86,875,816 | 450,177 | 88,199,317 | 17,639,863 | 88,199,317 |
| A_plan | 496 | 521,257 | 31,105,594 | 232,785 | 31,860,132 | 6,372,026 | — |
| B | 1,156 | 902,536 | 89,517,717 | 400,487 | 90,821,896 | 18,164,379 | — |

## Host-side stages

| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |
|---|---|---|---|---|---|---|---|---|
| 01 specs (Arm B/C input) | 5 | $79.39 | $15.88 | 270 | 346,331 | 6,916,122 | 89,421 | 7,352,144 |
| 06 verdicts (Arm C input) | 0 | $0.00 | — | 0 | 0 | 0 | 0 | 0 |
| 14 briefs (Arm A_plan input) | 5 | $8.48 | $1.70 | 641 | 471,116 | 15,870,466 | 165,654 | 16,507,877 |

## Arm A vs Arm B, all-in

- Arm A (inference only): **$12.74**, **41,257,956 tokens**
- Arm B (inference + spec stage): **$104.91** = $25.52 infer + $79.39 spec, **98,174,040 tokens** = 90,821,896 infer + 7,352,144 spec
- Spec overhead: **$92.17** (+723%)
- Token overhead: **56,916,084** (+138%)
- Extra tasks resolved by B: **-2** — cost per extra resolve is undefined; the spec arm's return at this N is in test quality (see the mutation report), not in resolved count.

## All-in per arm (control panel)

| arm | tasks | infer | host stage | all-in | all-in/task | resolved |
|---|---|---|---|---|---|---|
| A | 5 | $12.74 | $0.00 | $12.74 | $2.55 | 2 |
| A_hint | 5 | $25.37 | $0.00 | $25.37 | $5.07 | 1 |
| A_plan | 5 | $10.63 | $8.48 | $19.12 | $3.82 | 0 |
| B | 5 | $25.52 | $79.39 | $104.91 | $20.98 | 0 |

**Panel total (measured): $162.14**
