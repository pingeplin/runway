# Smell density — validation on the 15-spec corpus (2026-09-18)

Stage 12 gained one deterministic metric, `smell_density`. It counts
requirements smells (Femmer et al. 2017) per 100 prose words. The
smell classes are the INCOSE *Guide to Writing Requirements* v4 rules that a
word list can detect: hedges, R7 vague terms, R8 escape clauses, R9 open-ended
clauses and R26 absolutes. R16 ("not") and R24 (pronouns) are counted but left
out of the density, because detecting them needs the sentence read. The word
lists are ours, seeded from those rules.

The corpus, dataset and reports are the same as in
[`../2609_doc_quality_validation/`](../2609_doc_quality_validation/README.md):
5 astropy tasks × {4.0, Ouroboros A, Ouroboros B} specs, each joined to its B
pass_rate from [`../2609_clean_paired_astropy_n5/`](../2609_clean_paired_astropy_n5/README.md).
The run used no model and cost $0. Grounding was skipped because no pristine
testbed was passed.

```bash
R=reports/2609_clean_paired_astropy_n5
uv run python scripts/12_doc_quality.py \
  --dataset-jsonl results/_armc_clean/results/dataset_arm_b/data/fast.jsonl \
  --corpus v4=$R/v4/specs:$R/v4/report.md \
  --corpus ouroboros-a=$R/ouroboros-a/specs:$R/ouroboros-a/report.md \
  --corpus ouroboros-b=$R/ouroboros-b/specs:$R/ouroboros-b/report.md
```

## Result

| metric | expected sign | pooled ρ (n=15) | within-task agreement | verdict |
|---|---|---|---|---|
| smell density | − | −0.34 | 0.62 (13 pairs) | **diagnostic only** |

Per-label means are 4.0 0.33, Ouroboros A 0.38 and Ouroboros B 0.36 smells per
100 words, against pass rates 0.84 / 0.37 / 0.70.

On this run the recall and fence metrics reproduce the 09-12 numbers exactly
(0.50/0.62, 0.50/0.70, 0.50/1.00, −0.49/0.78). The change did not move them.

## What this says

1. **The sign is right, but the signal is too weak to use.** 8 of 13
   within-task pairs agree. At this n that is not distinguishable from a coin
   flip. The label means differ by 0.05 per 100 words.
2. **The specs are already near the floor.** There are 4–23 hits per
   2,700–5,400 prose words (0.13–0.56 per 100). LLM-written blueprint specs
   rarely use this vocabulary. That is the same saturation seen earlier in
   testability (≥0.85) and grounding (≥0.97).
3. **Most hits are not requirements smells.** [`hit_sample.md`](hit_sample.md)
   lists 20 random hits out of 212. Classified by Claude in the session that added the metric
   (not a human rating):
   - 16 are in descriptive prose: context, file notes, mutation notes ("a large
     number of code paths", "never exercised", "should break S3").
   - 4 are in requirement sentences, and all 4 are assertable as written ("must
     never raise or return …", "always maps to the *same* generated subclass").
   - None makes a requirement ambiguous. Femmer's ~0.5 precision was measured
     on requirements documents. On these specs most prose is not a
     requirement, and the word list has close to zero precision.

## Consequence

- `smell_density` stays in stage 12 as a free regression alarm and must not be
  a target.
- It matches the plugin decision in the same change: the INCOSE wording rules
  in `plugins/blueprint/references/review-spec.md` are report-only for the
  `spec-evaluator`, never autonomous fixes.
- Restricting the count to requirement-bearing text (acceptance scenarios,
  "must/shall" sentences) is the obvious next refinement. It is not done
  here: on this corpus it would leave almost nothing to count.
