# Over-explanation benchmark harness

A **standalone, on-demand** harness that measures whether a change to the
blueprint generator/evaluator skills reduces **over-explanation** (intra-document
restatement of already-stated claims) in generated design docs and specs —
*without* silently stripping load-bearing content or breaking downstream
buildability. Issue [#10](https://github.com/pingeplin/runway/issues/10).

It is **not part of any skill.** It lives under `eval/` (per-plugin eval tree),
pins two plugin commits (`A0` baseline vs `A1` treatment), runs them
side-by-side, and is invoked by hand whenever a blueprint skill is touched. A
grader bundled into the artifact it grades can't be trusted — so it isn't.

It **extends** [`../eval-methodology.md`](../eval-methodology.md): it reuses that
doc's two-`$CLAUDE_CONFIG_DIR` + git-worktree setup (§2), pre-registered panel
(§3), hidden-oracle + executed-mutation scoring (§4), and cron/`/loop`
orchestration (§5). It **adds**, specific to prose over-explanation: a
within-document restatement-rate metric, a cross-family proposition extractor,
substance/merge/grammaticality guardrails, and length-falsification controls.

## What it measures — and explicitly does not

**Primary signal = intra-document restatement rate**, not length:
`1 − (DISTINCT_PROPOSITIONS / TOTAL_PROPOSITION_MENTIONS)`. A within-document
rate, so a longer-but-non-repetitive doc scores the same as a short one, adding
non-repeating words cannot lower it, and comma-splicing two claims into one
sentence cannot game it. **Word count is never a ship target** — only a logged
covariate the effect must survive being adjusted for.

The change has two failure directions and the harness gates **both**: *no-effect*
(restatement didn't fall → don't ship as a win) and *substance-strip* (a
load-bearing claim was lost, or buildability/grammaticality regressed → block,
even if restatement fell).

## Layout

```
src/eval_overexplanation/
  models.py          frozen value objects (propositions, alignments, briefs, arms) — the contract
  interfaces.py      the only two judgement seams: PropositionExtractor, GrammaticalityChecker
  restatement.py     primary metric: 1 - distinct/total_mentions
  extractor.py       FixtureExtractor (offline/tests) + AnthropicExtractor (reference, lazy import)
  grammaticality.py  Default (dependency-free screen) + Spacy (behind [nlp]) checkers
  substance.py       paired A0->A1 proposition-diff recall guardrail (MUST-loss blocks)
  merge_fidelity.py  within-arm pre->post: ②'s delete-or-merge didn't drop a constraint
  stats.py           paired Wilcoxon, bootstrap CI, length-partialling, falsification STOP, TOST
  buildability.py    executed oracle + strategic mutation, subprocess-isolated (untrusted impls)
  manifest.py        pre-registration: validate() + content_hash() tamper-evidence
  corpus.py          load human-authored briefs / gold sets / oracle cases
  cli.py             thin wiring: restatement | guardrails | stats | buildability | manifest-hash
corpus/              the frozen task corpus (README = blind-authoring protocol; schema.md; worked example)
preregistration/     manifest.example.json — the frozen pre-registration template
scripts/             setup-worktrees.sh + run-arm.sh — the §2/§5 orchestration glue (bash)
tests/               one test file per module; runs fully offline (no network, no LLM, no spaCy model)
CONTRACTS.md         exact signatures every leaf implements to
```

Design: SOLID without ceremony. Inert dataclasses + **two** Protocols at the
non-deterministic seams; every decision rule is a pure function tested with
hand-built fixtures. The LLM (extractor) and NLP (grammaticality) are the only
things behind an interface, which is what lets the suite run offline and lets the
"≥2 model families" requirement (fix #1) be met by swapping an implementation,
not editing call sites.

## The four validity fixes (load-bearing — see issue #10)

1. **Definition-decoupled extractor** — `PropositionExtractor` uses an ontology
   authored independently of change ②'s six keep-categories, on a *different*
   model family, replicated across ≥2 (`manifest.extractor_families`; the
   harness warns at <2).
2. **Restatement RATE + length falsification** — `restatement.py` +
   `stats.length_falsification_stop` (pre-registered STOP if the effect doesn't
   survive partialling out word-count *or* a length-only strip reproduces it).
3. **Executable buildability, not `/verify`** — `buildability.py` runs a frozen
   brief-derived acceptance set + executed mutation testing. `/verify` can't
   referee this: it reads the spec's *own* scenarios (`referee.md:48`) so a
   stripped spec self-certifies, and its anti-vacuity is advisory, not executed
   (`referee.md:87-89`).
4. **Paired A0→A1 proposition-diff** — `substance.proposition_recall`: every
   unique A0 MUST-claim must survive into A1 or be a proven restatement.

## Run it

Requires [`uv`](https://docs.astral.sh/uv/). All Python goes through `uv`.

```bash
cd eval/blueprint/over-explanation
uv sync                       # core deps (numpy/scipy/statsmodels) + pytest
uv run pytest -q              # 129 passing, 1 skipped (the live-LLM test, gated on the [llm] extra)

# CLI (thin wiring; non-zero exit on any guardrail block / length-artifact STOP):
uv run overexpl manifest-hash preregistration/manifest.example.json
uv run overexpl restatement  <results-dir>     # per-(arm,brief,seed) rates
uv run overexpl guardrails   <results-dir>     # substance recall + merge fidelity + grammaticality
uv run overexpl stats        <results-dir>     # paired Wilcoxon + bootstrap + length-falsification STOP
uv run overexpl buildability <corpus> <impl-dir> --module M --entrypoint fn
```

Optional extras: `uv sync --extra llm` (live `AnthropicExtractor`),
`uv sync --extra nlp` (parse-based grammaticality).

A full A/B run (orchestration, reusing `eval-methodology.md` §2/§5):

```bash
scripts/setup-worktrees.sh <A0-commit> <A1-commit>   # tag + worktree + per-arm config dirs
scripts/run-arm.sh A0 <brief-dir> <seed>             # drive one pinned arm against one brief
```

## Status: Milestone 1

Built: the complete deterministic harness (metric, all guardrails, statistics,
buildability, manifest, corpus loader, CLI, orchestration glue) + tests, plus a
worked example brief and a pre-registration template. The mechanisms are
**already full-design-capable** — arms/briefs/seeds/extractor-families are config
(`manifest.example.json`), so scaling Milestone 1 (4 arms, K=2, 9 briefs) to
Milestone 2 (8 arms, ≥2 families, N=18) grows data, not code.

**Requires human-authored, blind, frozen inputs before a real run** (by design —
these are what make the experiment valid, and cannot be auto-generated without
defeating the blinding):

- the **9 briefs** + per-brief **gold proposition sets** + **hidden oracles**,
  authored per `corpus/README.md` (the worked `example-brief/` shows the shape);
- a concrete **second non-Anthropic extractor family** (open decision below);
- the pinned **A0/A1 commits** for `setup-worktrees.sh`.

**Known Milestone-1 limitations** (documented, not bugs):

- `overexpl stats` runs the length-falsification *partialling* half; the
  length-only-strip arm (the dumb-brevity reference) is a Milestone-2 arm, so the
  strip-reproduction check degrades to a sign test until that arm exists.
- `DefaultGrammaticalityChecker` is a deterministic *screen* (flags telegraphic /
  dropped-article / verbless fragments); the parse-based `[nlp]` checker is the
  higher-fidelity option, and a human read remains the final gate per issue #10.

**Verdict ceiling** (issue #10): a clean restatement cut with no detected
substance loss on the buildable subset is *"promising — scale to N=18 before
ship,"* never a ship. N=9/K=2 is underpowered to certify safety.

## Open decisions (carried from issue #10)

- Which **second (non-Anthropic) extractor/implementer family** to use.
- Where the **OSS large-realistic briefs** are mined from (license-clean, read-only).
- Whether to encode the run as a **`Workflow` script** vs the cron orchestration
  in `eval-methodology.md §5`.
