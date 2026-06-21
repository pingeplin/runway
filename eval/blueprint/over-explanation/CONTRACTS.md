# Leaf-module contracts

The backbone — `models.py` (inert value objects) and `interfaces.py` (the two
Protocol seams) — is **frozen**. Every leaf module below is a pure function or
small class over those types. Implement to these signatures exactly so the
modules compose. Read `models.py` and `interfaces.py` first.

Design rules (SOLID, not over-engineered):

- No new base classes, registries, or DI frameworks. Dataclasses + functions.
- Depend on the Protocols (`PropositionExtractor`, `GrammaticalityChecker`),
  never on a concrete extractor, except in `extractor.py`/`grammaticality.py`
  themselves.
- Every module is import-safe with only `numpy`/`scipy`/`statsmodels` present
  (the `llm` and `nlp` extras are optional — import them lazily, inside the
  method that needs them, never at module top level).
- Pure decision logic must be deterministic and unit-testable with hand-built
  fixtures and **no network**. Use `numpy.random.default_rng(seed)` for any
  sampling; never the global RNG.
- `from __future__ import annotations` at the top of every module.

All paths below are under `src/eval_overexplanation/`.

---

## `restatement.py` — primary metric

```python
@dataclass(frozen=True)
class RestatementScore:
    distinct: int
    total_mentions: int
    rate: float          # 1 - distinct/total_mentions, in [0, 1)

def restatement_rate(s: PropositionSet) -> RestatementScore
```

- `rate = 1 - distinct / total_mentions`. With all propositions mentioned once,
  `total_mentions == distinct` → rate `0.0`. Raises `ValueError` if
  `total_mentions == 0` (impossible for a valid set, but guard it).
- This is a *within-document rate*: adding non-repeating words cannot lower it,
  and comma-splicing two claims into one sentence cannot game it (mentions are
  per-proposition, not per-sentence). Note this property in the docstring.

---

## `extractor.py` — the cross-family seam (fix #1)

Implements `PropositionExtractor` (see `interfaces.py`).

```python
class FixtureExtractor:
    """Deterministic extractor for tests/offline runs. No LLM."""
    def __init__(self,
                 sets: dict[str, PropositionSet],
                 alignments: dict[tuple[str, str], Alignment] | None = None): ...
    def extract(self, document_id, text) -> PropositionSet   # sets[document_id], else KeyError
    def align(self, source, target) -> Alignment             # alignments[(source.document_id, target.document_id)]

class AnthropicExtractor:
    """Reference cross-family extractor. Lazy-imports `anthropic`."""
    def __init__(self, model: str, *, ontology: str = INDEPENDENT_ONTOLOGY, api_key: str | None = None): ...
    def extract(self, document_id, text) -> PropositionSet
    def align(self, source, target) -> Alignment
```

- `AnthropicExtractor` must `import anthropic` **inside** `__init__` (or a
  helper), raising `ImportError` with an actionable message
  (`pip install 'eval-overexplanation[llm]'`) when the extra is absent. The
  module itself must import without `anthropic` installed.
- Define `INDEPENDENT_ONTOLOGY` as a module constant: a short proposition-kind
  taxonomy authored independently of change ②'s six keep-categories
  (fact / decision / constraint / interface-detail / rejected-alternative /
  testable-behavior are ②'s — do **not** reuse them verbatim; use an
  independently-worded scheme and say so in a comment). It is passed to the
  model so the extractor never inherits the treatment's categories.
- The prompt instructs the model to return JSON: a list of distinct
  propositions each with `{id, text, kind, mention_sentences}`, and for
  `align`, a list of `{source_id, target_id, relation}`. Parse into the model
  types; surface malformed output as `ValueError`. Keep the API call in one
  small private method so it is the only thing that would need mocking.
- Do **not** call the network in any unit test.

---

## `grammaticality.py` — no-word-drop guardrail

Implements `GrammaticalityChecker`.

```python
class DefaultGrammaticalityChecker:
    """Dependency-free deterministic screen for fragments / dropped words.

    A coarse but deterministic screen, not a full parser. Its contract is:
    it MUST flag telegraphic / article-dropped / verbless fragments (the
    A3b_dumb_brevity failure mode) and MUST pass ordinary full sentences.
    The spaCy-backed checker is the higher-fidelity option behind [nlp].
    """
    def check(self, sentences: tuple[str, ...]) -> GrammaticalityReport

class SpacyGrammaticalityChecker:
    """Parse-based checker. Lazy-imports spacy; raises ImportError without [nlp]."""
    def __init__(self, model: str = "en_core_web_sm"): ...
    def check(self, sentences) -> GrammaticalityReport

def split_sentences(text: str) -> tuple[str, ...]
    """Deterministic sentence splitter (regex on terminal punctuation +
    newlines/list markers). Good enough to feed the checkers; documented as
    approximate."""
```

Default-checker heuristics (deterministic, documented in code), a sentence is a
fragment (`ok=False`) if any hold:

1. It contains no verb — approximated by: no token in a curated common-verb /
   auxiliary / copula set AND no token ending in `-s`, `-ed`, `-ing` that is not
   a known plural-noun exception. (Coarse; document the false-positive risk.)
2. A determiner/article was dropped before a singular count noun — detect a
   small set of `verb/preposition + bare-count-noun` bigrams
   (e.g. "returns list", "raise error", "in cache").
3. It does not start with a capital letter or does not end with terminal
   punctuation (after trimming list markers).

Provide each fragment a human-readable `reason`. Tune to the fixtures in
`tests/test_grammaticality.py` (full sentences pass; the supplied telegraphic
decoys fail). Keep the verb/noun word-lists small and inline — this is a screen,
not a lexicon.

---

## `substance.py` — paired A0→A1 proposition-diff recall (fix #4 / guardrail)

```python
@dataclass(frozen=True)
class RecallReport:
    total_source: int
    survived: int
    dropped_must: tuple[str, ...]     # source ids, by tier
    dropped_should: tuple[str, ...]
    dropped_detail: tuple[str, ...]
    @property
    def recall(self) -> float          # survived / total_source
    @property
    def blocks(self) -> bool           # True iff any MUST proposition dropped

def proposition_recall(alignment: Alignment) -> RecallReport
```

- A source proposition "survived" iff `survived(link.relation)` (import from
  `models`). Tier comes from the **source** proposition.
- `blocks` is True iff `dropped_must` is non-empty — losing a MUST claim blocks
  the ship even if restatement fell. SHOULD/detail losses are reported, not
  blocking, but surfaced for human review.

---

## `merge_fidelity.py` — ②'s delete-or-merge didn't drop a constraint

Operates on a **within-arm** pre-evaluator → post-evaluator `Alignment`.

```python
@dataclass(frozen=True)
class MergeFidelityReport:
    merged: tuple[str, ...]              # source ids with relation MERGED_INTO
    dropped_under_merge: tuple[str, ...] # source ids DROPPED (constraint lost)
    @property
    def ok(self) -> bool                 # no source proposition DROPPED
    @property
    def merge_count(self) -> int

def merge_fidelity(alignment: Alignment) -> MergeFidelityReport
```

- Focus: the evaluator's delete-OR-merge step must not silently drop a claim.
  Any source proposition with relation `DROPPED` that is not a proven
  `RESTATED_ELSEWHERE` is a fidelity violation. (In the model, `DROPPED` already
  excludes `RESTATED_ELSEWHERE`, so `dropped_under_merge` = the DROPPED set.)
- Distinct from `substance.proposition_recall`: that compares two *arms*
  (A0→A1); this compares one arm's *pre/post evaluator* documents. Same
  survival predicate, different inputs and report shape — do not merge them.

---

## `stats.py` — paired tests, bootstrap, length falsification, TOST

Uses scipy/statsmodels. Deltas are per-brief `treatment - baseline`, after K
seeds are averaged to the brief (no pseudo-replication).

```python
def average_to_brief(seed_values: Mapping[int, float]) -> float

@dataclass(frozen=True)
class PairedTest:
    statistic: float
    p_value: float
    n: int
def paired_wilcoxon(baseline: Sequence[float], treatment: Sequence[float]) -> PairedTest
    # scipy.stats.wilcoxon(treatment, baseline); n = #briefs; handle all-zero deltas gracefully.

@dataclass(frozen=True)
class BootstrapCI:
    point: float          # mean delta
    low: float
    high: float
    level: float
def bootstrap_ci(deltas: Sequence[float], *, n_boot: int = 10000,
                 level: float = 0.95, seed: int = 0) -> BootstrapCI
    # percentile bootstrap of the mean delta; numpy default_rng(seed) — deterministic.

@dataclass(frozen=True)
class PartialEffect:
    mean_residual: float    # mean restatement delta after regressing out wordcount delta
    slope: float            # restatement_delta ~ wordcount_delta
    p_value: float          # is mean residual != 0?
    survives: bool          # residual effect still in the hypothesised (negative) direction beyond noise
def partial_out_length(restatement_delta: Sequence[float],
                       wordcount_delta: Sequence[float],
                       *, noise_floor: float = 0.0) -> PartialEffect

@dataclass(frozen=True)
class LengthFalsification:
    survives_partialling: bool
    length_strip_reproduces: bool
    stop: bool              # pre-registered STOP: True => length artifact, DO NOT SHIP
    detail: str
def length_falsification_stop(treated_deltas: Sequence[float],
                              wordcount_deltas: Sequence[float],
                              length_strip_deltas: Sequence[float],
                              *, noise_floor: float) -> LengthFalsification
    # stop = (NOT survives_partialling) OR length_strip_reproduces
    #   survives_partialling: partial_out_length(treated, wordcount).survives
    #   length_strip_reproduces: the length-only-strip arm's mean delta reaches
    #     (within noise_floor) the treated arm's mean delta  => the gain is
    #     reproducible by dumb length stripping => artifact.

@dataclass(frozen=True)
class TostResult:
    non_inferior: bool
    p_value: float
    power: float
    certifiable: bool       # power >= min_power; if False, report "underpowered", never "safe"
def tost(baseline: Sequence[float], treatment: Sequence[float], *,
         margin: float, min_power: float = 0.8) -> TostResult
    # two one-sided tests for non-inferiority of a guardrail metric; estimate
    # achieved power for the given margin/n; certifiable only if power>=min_power.
```

Document each function's statistical assumption in one line. Where scipy needs
≥1 non-zero delta (Wilcoxon), guard the degenerate all-equal case and return a
well-defined result rather than letting scipy raise.

---

## `buildability.py` — executed oracle + mutation (fix #3)

The impl-under-test is **untrusted generated code**. Never import it into the
harness process; run it in a **subprocess** in a **temp copy** of the impl dir,
with a timeout.

```python
@dataclass(frozen=True)
class OracleResult:
    passed: int
    failed: int
    errors: tuple[str, ...]
    @property
    def total(self) -> int
    @property
    def correctness(self) -> float       # passed / total
def run_oracle(impl_dir: Path, module: str, entrypoint: str,
               cases: Sequence[OracleCase], *, timeout: float = 30.0) -> OracleResult
    # Copy impl_dir to a tempdir; write a tiny runner that imports `module`,
    # calls `entrypoint(*case.args)`, compares == case.expected; execute via
    # subprocess ([sys.executable, runner]); parse pass/fail; always clean up.

@dataclass(frozen=True)
class MutationResult:
    killed: int
    survived: tuple[str, ...]            # labels of mutations the suite missed
    invalid: tuple[str, ...]             # labels whose `find` didn't match exactly once
    @property
    def total(self) -> int               # killed + len(survived)  (invalid excluded)
    @property
    def kill_rate: float                 # killed / total
def run_mutations(impl_dir: Path, test_cmd: Sequence[str],
                  mutations: Sequence[Mutation], *, timeout: float = 120.0) -> MutationResult
    # For each mutation: copy impl_dir to a tempdir; apply the single literal
    # replacement (error to `invalid` if `find` count != 1); run test_cmd
    # (e.g. ["uv","run","pytest","-q"]) via subprocess in the tempdir; killed if
    # non-zero exit, survived if zero exit; timeout => killed (suite hung on the
    # mutant). Never mutate impl_dir in place.
```

- A mutation whose `find` does not occur exactly once is `invalid`, never
  silently dropped (silent skips inflate kill rate). Excluded from the
  denominator and reported.
- Per the repo rule, any Python the runner itself invokes goes through `uv run`;
  but `test_cmd` is passed in by the caller (it is the brief's own test command)
  so the module stays agnostic.

---

## `manifest.py` — pre-registration (anti p-hacking)

```python
@dataclass(frozen=True)
class DecisionThresholds:
    noise_floor_multiple: float = 2.0
    tost_margin: float = 0.0
    min_power: float = 0.8

@dataclass(frozen=True)
class PreRegistration:
    version: str
    arms: tuple[Arm, ...]
    briefs: tuple[Brief, ...]            # each carries its frozen Regime
    seeds: tuple[int, ...]
    extractor_families: tuple[str, ...]  # the model families used for extraction
    thresholds: DecisionThresholds
    def validate(self) -> tuple[str, ...]  # structural problems; empty => ok
    def content_hash(self) -> str          # sha256 over canonical JSON; the audit anchor

def load_manifest(path: Path) -> PreRegistration   # JSON -> PreRegistration
def dump_manifest(reg: PreRegistration) -> str     # canonical JSON (sorted keys)
```

- `validate` checks: ≥1 seed; an `A0`-id and an `A1`-id arm present; every brief
  has a regime; thresholds present. For a *real* (non-fixture) run it should
  also warn if `len(extractor_families) < 2` (fix #1 wants ≥2) — emit that as a
  problem string, not an exception.
- `content_hash` is the tamper-evidence: canonical (sorted-key) JSON → sha256.
  Two registrations with identical content hash to the same value; changing any
  frozen field changes the hash. This is how "frozen before any A1 run" is
  audited.

---

## `corpus.py` — load human-authored assets

```python
def load_brief(brief_dir: Path) -> Brief
    # reads brief.json {id,title,regime,buildable} + brief.md (-> .text)
def load_gold(brief_dir: Path) -> PropositionSet
    # reads gold_propositions.json -> PropositionSet (the blind gold set)
def load_oracle_cases(brief_dir: Path) -> tuple[OracleCase, ...]
    # reads cases.json -> OracleCase tuple (empty if brief is not buildable)
def load_corpus(root: Path) -> tuple[Brief, ...]
    # every immediate subdir of root that has a brief.json
```

- JSON shapes are documented in `corpus/schema.md` (a scaffold artifact). Be
  tolerant of a missing `cases.json` for non-buildable briefs (return `()`),
  strict about a malformed one.
- `regime` strings map to the `Regime` enum; unknown value => `ValueError`.

---

## `cli.py` — thin wiring (no logic)

```python
def main(argv: Sequence[str] | None = None) -> int
```

`argparse` with subcommands, each just loads inputs and calls the library:

- `restatement <results-dir>` — print per-(arm,brief,seed) restatement scores.
- `guardrails <results-dir>` — substance recall + merge fidelity + grammaticality.
- `stats <results-dir>` — paired Wilcoxon + bootstrap + length-falsification STOP.
- `buildability <corpus> <impl-dir>` — oracle + mutation kill-rate.
- `manifest-hash <manifest.json>` — print `content_hash` (for pre-registration).

Keep all computation in the libraries; the CLI only parses args, loads, formats.
Return non-zero on any guardrail block / STOP so it is CI-usable.

---

## Tests

One file per module under `tests/`, named `test_<module>.py`. Use only
hand-built fixtures and `tmp_path`; **no network, no real LLM, no spaCy
model download**. For `extractor.py`, test `FixtureExtractor` fully and assert
`AnthropicExtractor` raises a clear `ImportError`/`ValueError` path without the
extra (or `pytest.importorskip` if present). For `buildability.py`, write a
tiny throwaway impl + test into `tmp_path` and exercise a real subprocess run
(kill a mutant, survive a no-op). Cover the documented edge cases and each
guardrail's block/no-block boundary.
