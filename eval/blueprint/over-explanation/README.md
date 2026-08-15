# Over-explanation benchmark harness

A **standalone, on-demand** harness that measures whether a change to the
blueprint generator/evaluator skills reduces **over-explanation** (intra-document
restatement of already-stated claims) in generated design docs and specs —
*without* silently stripping load-bearing content or breaking downstream
buildability. Issue [#10](https://github.com/pingeplin/runway/issues/10).

It is **not part of any skill.** It lives under `eval/` (per-plugin eval tree),
pins the plugin commits for each experimental arm (`A0` baseline … up to the 8
arms of the full design), runs them side-by-side, and is invoked by hand
whenever a blueprint skill is touched. A grader bundled into the artifact it
grades can't be trusted — so it isn't.

It **extends** [`../eval-methodology.md`](../eval-methodology.md): it reuses that
doc's two-`$CLAUDE_CONFIG_DIR` + git-worktree setup (§2), pre-registered panel
(§3), hidden-oracle + executed-mutation scoring (§4), and cron/`/loop`
orchestration (§5). It **adds**, specific to prose over-explanation: a
within-document restatement-rate metric, a cross-family proposition extractor
(Anthropic + OpenAI families), substance/merge/grammaticality guardrails,
length-falsification controls, an instrument-trust gate, and the full SHIP/KILL
decision rule.

**Status: Milestone 2 + BLUEPRINT-BENCH v1 are implemented** — all 8 arms, the
second extractor family, Holm correction, leave-one-brief-out, the dedup-threshold
sweep, TOST-powered guardrails, the instrument-trust gate, the decision rule, and
the full C/U/O benchmark layer of `BENCHMARK.md` (usage/dead-end/leakage/outcome
signals, the §2 scorer with canonical `score.json`, the §4 `bench.*` manifest
thresholds, and the pinned-implementer driver). 484 tests pass offline. A labeled
**non-blind demo corpus** makes it runnable end-to-end today (`scripts/demo.sh`,
`scripts/bench-demo.sh`); a real verdict still needs the blind, human-authored
corpus assets (briefs, gold sets, oracles, `cases_holdout.json`,
`mutations.json`) — the one thing the harness cannot author for itself without
defeating its own validity.

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
  extractor.py       FixtureExtractor (offline) + AnthropicExtractor + OpenAIExtractor (≥2 families, fix #1;
                     pinned claude-sonnet-4-6 + gpt-5.4; prompt-cache the stable instruction prefix)
  grammaticality.py  Default (dependency-free screen) + Spacy (behind [nlp]) checkers
  substance.py       paired A0->A1 proposition-diff recall guardrail (MUST-loss blocks)
  merge_fidelity.py  within-arm pre->post: ②'s delete-or-merge didn't drop a constraint
  stats.py           Wilcoxon, bootstrap, length-partialling, falsification STOP, TOST,
                     Holm correction, leave-one-brief-out, dedup sweep, noise floor
  buildability.py    executed oracle + strategic mutation, subprocess-isolated (untrusted impls)
  instrument.py      instrument-trust gate (atomization / length / filler invariance) — pre-unblinding
  decision.py        the SHIP/KILL rule (ship treatment | one-liner | ② only | do-not-ship | underpowered)
  manifest.py        pre-registration: validate() + content_hash() + BenchThresholds (§4 bench.*)
  corpus.py          load human-authored briefs / gold sets / oracle + holdout cases / mutations
  usage.py           fail-closed transcript usage parse (U1/U2/U4/U6) — missing is never zero
  deadend.py         U0/U3/U5 transcript signals + O4 workaround lint + L1-L4 leakage control
  score.py           the §2 scorer: gates, subscores, precedence, canonical score.json
  cli.py             thin wiring: restatement|guardrails|stats|buildability|manifest-hash|decision|
                     instrument|sweep|usage|deadend|leakage|outcome|bench-trust|score
corpus/              the frozen task corpus (README = blind-authoring protocol; schema.md; worked example)
  demo/              labeled NON-BLIND demo corpus (9 briefs, see PROVENANCE.md) — pipeline shakeout only
preregistration/     manifest.example.json + manifest.demo.json (both carry the frozen bench.* block)
scripts/             setup-worktrees.sh, run-arm.sh, run-implementer.sh, run-experiment.sh (panel),
                     demo.sh, bench-demo.sh — §2/§5 bash glue
analysis/            assemble.py — run cells + cross-family extractor -> results.json
orchestration/       run-experiment.workflow.js — the primary (Workflow) panel driver
demo/                run_demo.py (M2 verdict demo) + run_benchmark_demo.py (bench score.json demo)
tests/               one test file per module + demo smoke tests; runs fully offline
CONTRACTS.md         exact signatures every leaf implements to (M1 + M2 + BENCHMARK sections)
BENCHMARK.md         BLUEPRINT-BENCH v1 frozen contract (§1 dimensions, §2 score.json, §3 modules, §4 manifest)
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
uv run pytest -q              # 484 passing, 2 skipped (the live-LLM tests, gated on the [llm] extra)

# End-to-end demo on the NON-BLIND demo corpus -> a real verdict (synthetic arm data):
scripts/demo.sh                       # clean run -> SHIP_TREATMENT
scripts/demo.sh --break substance     # drop a MUST claim   -> DO_NOT_SHIP
scripts/demo.sh --break length        # length artifact     -> DO_NOT_SHIP
scripts/demo.sh --break grammaticality
scripts/demo.sh --break instrument

# BLUEPRINT-BENCH offline demo -> a real canonical score.json (exit code = verdict):
scripts/bench-demo.sh                        # clean -> SHIP (exit 0), demo/out/bench/score.json
scripts/bench-demo.sh --break leakage        # UNFENCED oracle paste in the spec -> L1/L2 gate, exit 1
scripts/bench-demo.sh --break workaround     # assert True + TODO in the impl    -> O4 gate,   exit 1
scripts/bench-demo.sh --break missing-result # transcript without result event    -> U4 gate,   exit 1
scripts/bench-demo.sh --break incomplete     # unpacked crashed cells             -> not scorable, exit 4

# CLI (thin wiring; non-zero exit on any guardrail block / STOP / not-trusted):
uv run overexpl manifest-hash preregistration/manifest.demo.json
uv run overexpl restatement  <results-dir>      # per-(arm,brief,seed) rates
uv run overexpl guardrails   <results-dir>      # substance recall + merge fidelity + grammaticality
uv run overexpl stats        <results-dir>      # Wilcoxon + bootstrap + length-falsification STOP
uv run overexpl buildability <corpus> <impl-dir> --module M --entrypoint fn
uv run overexpl instrument   <docs.json> <decoys.json>   # trust gate — run BEFORE reading numbers
uv run overexpl decision     <inputs.json>      # the SHIP/KILL verdict
uv run overexpl sweep        <sweep.json>       # dedup-threshold stability

# BLUEPRINT-BENCH CLI (BENCHMARK.md §3; exit 1 = blocked, exit 4 = not scorable):
uv run overexpl usage       <transcript.jsonl> [--return-code N]     # fail-closed cell usage
uv run overexpl deadend     <transcript.jsonl> [--manifest M]        # U0/U3/U5 signals
uv run overexpl leakage     <spec.md> <brief-dir> <impl-dir>         # L1-L4 incl. executed L4
uv run overexpl outcome     <brief-dir> <impl-dir> [--manifest M]    # O1-O5; owns the O3 reference dir
uv run overexpl bench-trust <brief-dir> [--manifest M]               # G-BT reference+stub controls
uv run overexpl score       <inputs.json> --manifest M --corpus C [--out F]  # §2 precedence -> score.json
```

Optional extras: `uv sync --extra llm` (live `AnthropicExtractor` + `OpenAIExtractor`),
`uv sync --extra nlp` (parse-based grammaticality).

A full panel run (all arms × briefs × seeds). Primary path is the Workflow
script; the bash driver is the §5 fallback:

```bash
scripts/setup-worktrees.sh <A0-commit> <A1-commit> ...   # tag + worktree + per-arm config dirs
# primary: Workflow({ scriptPath: "orchestration/run-experiment.workflow.js",
#                     args: { manifest, corpus, family: "openai", model } })
# fallback (bash/cron):  MODEL is optional — defaults to the per-family pin
FAMILY=openai scripts/run-experiment.sh preregistration/manifest.demo.json corpus/demo
```

The two cross-family extractors are pinned to **Anthropic `claude-sonnet-4-6`**
and **OpenAI `gpt-5.4`** (override with `--model` / `MODEL`; `--base-url` points
the "openai" family at any OpenAI-compatible/local endpoint for a cheaper third
family). Both extractors are **prompt-cache-aware**: the stable instruction +
ontology prefix carries the cache breakpoint (Anthropic `cache_control`; OpenAI
caches automatically), with the volatile per-document text after it. Caching
activates once a prefix clears the model floor (~2048 tokens on Sonnet 4.6,
~1024 on OpenAI) — placement-correct today, cost-saving as instructions grow.

## Status: Milestone 2 + BLUEPRINT-BENCH v1 — implemented

Built and tested (484 offline tests): the metric, all guardrails, the full
statistics layer (Wilcoxon, bootstrap, length-partialling + falsification STOP,
TOST with achieved-power, Holm correction, leave-one-brief-out, dedup-threshold
sweep, noise floor), executed buildability, the instrument-trust gate, the
SHIP/KILL decision rule, the manifest, the corpus loader, both extractor families
(Anthropic + OpenAI), the CLI, the assembly bridge, and both orchestration paths
(Workflow + bash). `scripts/demo.sh` runs the whole pipeline to a verdict.

On top, the **BLUEPRINT-BENCH v1 layer** (`BENCHMARK.md`): fail-closed usage
parsing (`usage.py`), dead-end/leak/workaround signals with whole-document
leakage detection (`deadend.py`), the §2 scorer with the full precedence table
and byte-stable canonical `score.json` (`score.py`), the §4 `bench.*` manifest
block (`manifest.BenchThresholds`, hashed + validated; the manifest — not
Python defaults — feeds the scorer), holdout/mutation loaders (absent ⇒
skipped, never passed), the pinned-implementer driver
(`scripts/run-implementer.sh`, non-ok cells exit non-zero) with generate-cell
isolation to match (`run-arm.sh` refuses an inside-repo workspace), and the six
bench CLI subcommands — `overexpl score`'s packer re-derives the manifest hash
and every `CellCounts.expected` from the manifest panel so omitted crashed
cells can never read as a complete arm. `scripts/bench-demo.sh` emits a real
`score.json` offline and each `--break` mode proves its gate.

**The things not auto-generated — by design:** the **blind, human-authored
corpus assets** (briefs + gold proposition sets + hidden oracles +
`cases_holdout.json` ×6 + `mutations.json` ×6×8). The harness ships a labeled
*non-blind demo* corpus (`corpus/demo/`, Claude-authored) so the pipeline runs
end-to-end, but a real verdict requires the blind corpus per
`corpus/README.md` — authoring it with the model under test would defeat the
blinding the whole design depends on. A real run also needs the two extractor
families' API keys, the pinned per-arm plugin commits for
`setup-worktrees.sh`, the pinned implementer config (`~/.claude-implementer` +
`IMPLEMENTER_MODEL`), and the pre-treatment calibration pass that lifts the L
caps and `frag_rate_cap` off their floors (BENCHMARK.md §1).

**Documented limitations** (not bugs):

- `DefaultGrammaticalityChecker` is a deterministic *screen*; the parse-based
  `[nlp]` checker is higher-fidelity, and a human read remains the final gate.
- **Merge-fidelity** recovers the pre-evaluator document from each cell's
  `transcript.jsonl` (the generator's lone `Write` to an artifact, before the
  evaluator `Edit`s it) and emits a `merge_alignment` for `overexpl guardrails`.
  It is **fail-closed**: a cell whose artifact was written more than once, or has
  no transcript Write, is *skipped* (no signal), never passed — an uncertain
  pre/post boundary must not fabricate a "no claim dropped" result. Fully
  reliable capture across all cells ultimately wants a generator-side pre-eval
  snapshot; the ambiguous cells simply contribute no merge-fidelity signal.

**Verdict ceiling** (issue #10): at the Milestone-1 panel size (N=9/K=2) a clean
result is *"promising — scale to N=18 before ship,"* never a ship; the manifest
scales arms/briefs/seeds to the full design without code change.

## Decisions (resolved)

- **Second extractor family: OpenAI** (`OpenAIExtractor`, configurable
  `base_url` so it also targets OpenAI-compatible/local endpoints), alongside
  `AnthropicExtractor`. The two families are pinned to `claude-sonnet-4-6` and
  `gpt-5.4`, and both build their requests so the stable instruction prefix is
  prompt-cached.
- **Orchestration: both** — a runnable `Workflow` script (primary) and the
  bash/cron driver (fallback).
- **Still open:** where the OSS large-realistic briefs are mined from
  (license-clean, read-only) for the real blind corpus.
