# Doc-quality metric validation — 15 specs with known outcomes (2026-09-12)

First run of stages 12 (deterministic) and 13 (blind opus judge) over the
specs of the clean paired rerun
([`../2609_clean_paired_astropy_n5/`](../2609_clean_paired_astropy_n5/README.md)):
5 astropy tasks × 3 spec producers (blueprint 4.0, Ouroboros A, Ouroboros B),
each with a measured B pass_rate. Nothing in the plugin changed; this run
asks only **which document metrics point the same way as the outcome** before
any of them is optimised against — the check the Ouroboros line skipped
(post-mortem 2609.0003 §5).

- `doc_quality_report.md` — stage 12: oracle recall, effective recall, file
  recall, fenced∩oracle (heuristic), grounding.
- `doc_judge_report.md` — stage 13: fence listing, coherence, testability;
  2 repeats per cell, ± = judge self-disagreement. Coherence was removed from
  stage 13 after this run (decision 2026-09-13, see finding 4); the cells and
  prompt sha stay here as the record.
- `doc_judge/` — the 90 judge cells (prompt/spec sha256, cost, wall, raw JSON).
- `doc_quality.json` — stage 12 per-cell records.

## Headline

| metric | expected sign | pooled ρ (n=15) | within-task agreement | verdict |
|---|---|---|---|---|
| file recall (12) | + | 0.50 | **1.00** (5 pairs) | keep — breadth at file level |
| effective recall (12) | + | 0.50 | 0.70 (10 pairs) | keep — breadth minus fenced |
| symbol recall (12) | + | 0.50 | 0.62 (8 pairs) | keep, read with effective recall |
| hard fenced∩oracle (13, judge) | − | −0.35 | 0.64 (11 pairs) | keep — separates lombscargle v4 (2) from Ouroboros A/B (7/6) |
| fenced∩oracle (12, heuristic) | − | −0.49 | 0.78 (9 pairs) | keep as the free proxy; judge is the reference |
| contradictions (13) | − | −0.00 | 0.54 (13 pairs) | **dropped** — no relation to outcome; ±1–4 between repeats |
| terminology drift (13) | − | 0.23 | 0.45 | dropped with coherence |
| ordering defects (13) | − | 0.27 | 0.18 | dropped with coherence |
| behavioral share (13) | + | −0.04 | 0.22 | saturated (0.85–1.00 everywhere); no signal on this corpus |
| grounding precision (12) | + | −0.30 | 0.31 | diagnostic only; 0.97–1.00 everywhere |
| spec lines (12) | none | −0.05 | — | length is not quality |

Per-label means:

| | 4.0 | Ouroboros A | Ouroboros B |
|---|---|---|---|
| B pass_rate | **0.84** | 0.37 | 0.70 |
| effective recall | 0.55 | 0.49 | **0.74** |
| file recall | 0.68 | 0.62 | **0.80** |
| hard fenced∩oracle (judge, mean per spec) | 2.6 | 4.0 | 2.5 |
| contradictions (judge) | 4.2 | **2.8** | 3.0 |
| behavioral share | 0.97 | 0.98 | 0.94 |

## What this says

1. **Breadth metrics agree with the outcome; coherence does not.** Recall
   and fence overlap order labels the way pass_rate does in 62–100 % of
   within-task pairs. Contradiction count is a coin flip (0.54) and pooled
   ρ is 0.00. The Ouroboros A point estimate is lower (2.8 vs 4.2), but
   the same prompt on the same spec moves by up to 4 between repeats, so this
   corpus cannot say whether the loop changed coherence at all — only that
   coherence, however measured here, has no visible relation to whether the
   agent builds the feature. This is the post-mortem's §5 claim, now measured.
2. **The fence metric reproduces the lombscargle mechanism.** The judge lists
   2 hard-fenced oracle symbols in the 4.0 spec (0.96 pass) and 7 / 6 in the
   Ouroboros A / B specs (0.03 pass), including `str_kwargs` and
   `get_unit`/`strip_units`, which the 4.0 spec puts in scope. The stage-12
   heuristic gets 0 / 3 / 1 for the same cells after the reviewer-driven fix
   that stopped it counting "in scope, added during review" lines under a
   "Companion gaps" heading as fences.
3. **Ouroboros B has the highest recall and still loses to 4.0.** Recall is
   necessary, not sufficient: B's `test_lombscargle` recall is 0.61 vs 4.0's
   0.50, but it fences `get_err_str` and the agent stopped at 0.03. Read
   recall and fence together.
4. **Judge self-agreement is poor on coherence, so the metric was dropped.**
   Two runs of the same prompt on the same spec differ by up to 4
   contradictions (v4 `test_containers`: 5.0 ±4), the pooled ρ is 0.00, and
   coherence cells were the 10 most expensive of the 90. Fence and
   testability repeat within ±1–2 and stay. `prompts/judge_coherence.md` is
   gone; stage 13 now judges fence and testability only.
5. **Testability and grounding are saturated.** Every producer writes
   behavioral Given/When/Then at ≥0.85 and names real files at ≥0.97. On
   this corpus they cannot rank anything; they may still catch a regression.

## Caveats

- 5 tasks, one repository, one seed of the downstream pass_rate. Pooled n=15
  counts cells that share tasks; the within-task column is the honest one and
  has 5–13 pairs.
- The judge saw only the spec text (`--tools ""`, empty cwd), so it cannot
  know which fenced symbols the hidden tests reach; the ∩ oracle is computed
  host-side afterwards.
- Coherence prompt asks for two quotes per contradiction; entries with one
  quote are dropped. The remaining count is still judge opinion.
- Stage-12 fence heuristic is phrase-based and will miss new phrasings; the
  judge listing is the reference, the heuristic is the free approximation.
- Symbols are matched by bare name. `__init__` / `__call__` in a fence list
  therefore count against any masked class with that method (`test_table`,
  `test_basic_rgb` rows carry them); recall has the same blind spot. Filtering
  dunders or using the mask's hunk-header class context is a later fix.

## Cost and time

| | |
|---|---|
| judge calls kept | 90 (15 specs × 3 metrics × 2 repeats) |
| judge spend, kept cells | $149.11 |
| judge spend incl. failed/timed-out attempts | ≈$150 |
| mean wall per call | 220 s (max 893 s; coherence is the slow one) |
| stage 12 | free, ~1 min incl. re-masking 5 workspaces |

Per-cell cost ranged $0.33–4.76. The 10 most expensive cells are 8 coherence
cells (27k–47k output tokens, 115k–240k cached-prefix reads accumulated over
the call) and 2 fence cells whose cache had expired (134k / 117k cache-write
tokens, output unchanged). Coherence's own volume was the main driver; cache
expiry between passes was the secondary one. With coherence removed the
remaining cells ran $0.33–0.45 (fence) and $0.46–2.4 (testability).

A first pass lost 55 cells to `claude exited 1` in 4 s at $0 (transient CLI
failure, cause not captured — the harness now keeps the stderr tail on a
non-zero exit); they were re-judged from the cache boundary. One coherence
call hit the 900 s timeout; the default is now 1800 s.

## Design docs

Not measured. Rubric defined in [`../../DESIGN_RUBRIC.md`](../../DESIGN_RUBRIC.md);
no corpus with known outcomes exists yet.
