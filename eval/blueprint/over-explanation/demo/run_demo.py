"""End-to-end demo of the over-explanation harness on the NON-BLIND demo corpus.

This drives the *real* analysis pipeline — restatement scoring, the substance /
merge-fidelity / grammaticality guardrails, executed buildability, the full
statistics layer (paired Wilcoxon, bootstrap, noise floor, length-falsification
STOP, Holm, leave-one-out), the instrument-trust gate, and the SHIP/KILL
decision rule — over synthetic per-arm artifacts derived from the demo corpus.

It exists to prove every mechanism *composes* and produces a coherent verdict.
It proves nothing about the real treatment: the corpus is Claude-authored and
same-family (see corpus/demo/PROVENANCE.md). Arm *artifacts* here are synthesised
with deliberately controlled restatement so the pipeline has a known-shape signal
to chew on — they are not real generator output.

Run:  uv run python demo/run_demo.py [--break substance|length|grammaticality|instrument]

``--break X`` flips exactly one upstream input so you can watch the corresponding
gate change the verdict. With no break the synthetic signal yields SHIP_TREATMENT.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval_overexplanation.buildability import run_oracle
from eval_overexplanation.corpus import load_corpus, load_gold, load_oracle_cases
from eval_overexplanation.decision import ArmComparison, DecisionInputs, decide
from eval_overexplanation.extractor import FixtureExtractor
from eval_overexplanation.grammaticality import DefaultGrammaticalityChecker
from eval_overexplanation.instrument import Decoy, instrument_trust_gate
from eval_overexplanation.merge_fidelity import merge_fidelity
from eval_overexplanation.models import (
    Alignment,
    Proposition,
    PropositionLink,
    PropositionSet,
    Relation,
    Tier,
)
from eval_overexplanation.restatement import restatement_rate
from eval_overexplanation.stats import (
    bootstrap_ci,
    estimate_noise_floor,
    holm_correction,
    leave_one_brief_out,
    length_falsification_stop,
    paired_wilcoxon,
    tost,
)
from eval_overexplanation.substance import proposition_recall

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEMO_CORPUS = ROOT / "corpus" / "demo"


# --------------------------------------------------------------------------- #
# Synthetic per-arm artifacts derived from a brief's gold set
# --------------------------------------------------------------------------- #


def _arm_set(gold: PropositionSet, doc_id: str, mentions: int) -> PropositionSet:
    """Re-emit the gold propositions with ``mentions`` mentions each.

    Restatement rate of the result is ``1 - 1/mentions`` (every proposition
    mentioned the same number of times), so a higher ``mentions`` is a more
    over-explaining document. ids are preserved so arm sets align 1:1.
    """
    props = tuple(
        Proposition(
            id=p.id,
            text=p.text,
            kind=p.kind,
            tier=p.tier,
            mention_sentences=tuple(range(mentions)),
        )
        for p in gold.propositions
    )
    return PropositionSet(document_id=doc_id, propositions=props)


def _mentions_for(arm: str, i: int) -> int:
    """Per-arm mention profile (varies a little by brief index for non-zero variance)."""
    if arm == "A0":
        return 2 + (i % 2)            # rate 0.50 or 0.667 — the over-explaining baseline
    if arm == "A2_placebo":
        return 2 + (i % 2)            # same as A0 — the extra pass removes no restatement
    if arm == "A1":
        return 1                      # rate 0.0 — the treatment win
    if arm == "A3_fair":
        return 2 if i % 3 == 0 else 1  # mostly tight; A1 still beats it slightly
    if arm == "length_strip":
        return 2 + (i % 2)            # length cut but restatement UNCHANGED (the falsifier)
    raise ValueError(arm)


def _wordcount(arm: str, i: int) -> float:
    base = {"A0": 300, "A2_placebo": 300, "A1": 180, "A3_fair": 190, "length_strip": 150}[arm]
    return float(base + 7 * i)


# --------------------------------------------------------------------------- #
# Guardrail / instrument synthetic inputs
# --------------------------------------------------------------------------- #


def _substance_alignment(a0: PropositionSet, a1: PropositionSet, drop_must: bool) -> Alignment:
    """A0->A1 alignment: all preserved, unless ``drop_must`` drops one MUST claim."""
    links = []
    dropped = False
    for p in a0.propositions:
        if drop_must and not dropped and p.tier is Tier.MUST:
            links.append(PropositionLink(p.id, None, Relation.DROPPED))
            dropped = True
        else:
            links.append(PropositionLink(p.id, p.id, Relation.PRESERVED))
    # If the gold set had no MUST proposition, force the first link to DROPPED so
    # the break is always demonstrable.
    if drop_must and not dropped:
        links[0] = PropositionLink(a0.propositions[0].id, None, Relation.DROPPED)
    return Alignment(source=a0, target=a1, links=tuple(links))


def _merge_alignment(pre: PropositionSet, post: PropositionSet) -> Alignment:
    """pre(evaluator-in)->post(evaluator-out): every claim merged_into/preserved, intact."""
    links = tuple(
        PropositionLink(p.id, p.id, Relation.MERGED_INTO) for p in pre.propositions
    )
    return Alignment(source=pre, target=post, links=links)


def _instrument_decoys(broken: bool):
    """Three invariance decoys + a FixtureExtractor returning controlled sets.

    atomization: splitting sentences must not change the distinct count.
    length_confound: padding must not lower the rate.
    defensive_filler: filler must not raise the distinct count.
    ``broken`` makes the atomization variant invent two extra propositions.
    """

    def pset(doc_id: str, distinct: int, mentions: int) -> PropositionSet:
        return PropositionSet(
            document_id=doc_id,
            propositions=tuple(
                Proposition(f"{doc_id}-p{k}", f"claim {k}", "assertion", Tier.SHOULD,
                            tuple(range(mentions)))
                for k in range(distinct)
            ),
        )

    sets = {
        "atom-base": pset("atom-base", 5, 2),
        "atom-var": pset("atom-var", 7 if broken else 5, 2),    # split shouldn't add claims
        "len-base": pset("len-base", 5, 2),
        "len-var": pset("len-var", 5, 2),                        # padding: rate unchanged
        "fill-base": pset("fill-base", 5, 2),
        "fill-var": pset("fill-var", 5, 2),                      # filler: distinct unchanged
    }
    docs = {k: f"text for {k}" for k in sets}
    decoys = [
        Decoy("atomization-invariance", "atom-base", "atom-var", "atomization", 0.0),
        Decoy("length-confound", "len-base", "len-var", "length_confound", 0.01),
        Decoy("defensive-filler", "fill-base", "fill-var", "defensive_filler", 0.0),
    ]
    return FixtureExtractor(sets), docs, decoys


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


def run(break_mode: str | None) -> int:
    briefs = load_corpus(DEMO_CORPUS)
    print(f"loaded {len(briefs)} demo briefs from {DEMO_CORPUS.relative_to(ROOT)}\n")

    # Per-brief restatement rates per arm, computed by the real scorer.
    rates: dict[str, list[float]] = {a: [] for a in
                                     ("A0", "A1", "A2_placebo", "A3_fair", "length_strip")}
    wc: dict[str, list[float]] = {a: [] for a in rates}
    a0_sets: list[PropositionSet] = []
    a1_sets: list[PropositionSet] = []

    for i, b in enumerate(briefs):
        gold = load_gold(DEMO_CORPUS / b.id)
        for arm in rates:
            s = _arm_set(gold, f"{b.id}:{arm}", _mentions_for(arm, i))
            rates[arm].append(restatement_rate(s).rate)
            wc[arm].append(_wordcount(arm, i))
        a0_sets.append(_arm_set(gold, f"{b.id}:A0", _mentions_for("A0", i)))
        a1_sets.append(_arm_set(gold, f"{b.id}:A1", _mentions_for("A1", i)))

    n = len(briefs)
    treated = [rates["A1"][i] - rates["A0"][i] for i in range(n)]
    placebo = [rates["A2_placebo"][i] - rates["A0"][i] for i in range(n)]
    strip = [rates["length_strip"][i] - rates["A0"][i] for i in range(n)]
    if break_mode == "length":
        strip = list(treated)  # dumb stripping reproduces the gain -> length artifact
    wc_treated = [wc["A1"][i] - wc["A0"][i] for i in range(n)]

    print("== restatement (primary metric) ==")
    print(f"  mean A0 rate     {sum(rates['A0'])/n:.3f}")
    print(f"  mean A1 rate     {sum(rates['A1'])/n:.3f}")
    print(f"  mean delta A1-A0 {sum(treated)/n:+.3f}  (negative = less restatement = a win)")

    wil = paired_wilcoxon(rates["A0"], rates["A1"])
    ci = bootstrap_ci(treated, seed=0)
    noise = estimate_noise_floor(same_arm_seed_spread=[0.0] * n, placebo_deltas=placebo)
    lf = length_falsification_stop(treated, wc_treated, strip, noise_floor=noise)
    loo = leave_one_brief_out(treated)
    print(f"  paired Wilcoxon  stat={wil.statistic:.4g} p={wil.p_value:.4g} n={wil.n}")
    print(f"  bootstrap 95% CI [{ci.low:+.3f}, {ci.high:+.3f}]  mean {ci.point:+.3f}")
    print(f"  noise floor      {noise:.4f}")
    print(f"  length-falsify   {lf.detail}")
    print(f"  leave-one-out    sign_stable={loo.sign_stable} range=[{loo.min_mean:+.3f},{loo.max_mean:+.3f}]")

    restatement_real = (sum(treated) / n < 0) and (not lf.stop)

    # -- guardrails --
    drop_must = break_mode == "substance"
    substance_blocks = any(
        proposition_recall(_substance_alignment(a0_sets[i], a1_sets[i], drop_must)).blocks
        for i in range(n)
    )
    merge_ok = all(merge_fidelity(_merge_alignment(a0_sets[i], a1_sets[i])).ok for i in range(n))

    checker = DefaultGrammaticalityChecker()
    a1_doc = ("The limiter rejects requests beyond the cap.",
              "Each tenant has an isolated bucket.")
    a3b_doc = ("rejects requests beyond cap.", "tenant isolated bucket.")  # telegraphic
    a1_gram_ok = checker.check(a1_doc).ok
    a3b_fails = not checker.check(a3b_doc).ok
    if break_mode == "grammaticality":
        a3b_fails = False  # the positive control no longer fails -> detector unproven

    print("\n== guardrails ==")
    print(f"  substance recall  blocks={substance_blocks} (MUST claim lost)" )
    print(f"  merge fidelity    ok={merge_ok}")
    print(f"  grammaticality    A1_ok={a1_gram_ok}  A3b_fails_detector={a3b_fails}")

    # -- buildability (executed oracle on the real demo oracles) --
    build_a0: list[float] = []
    build_a1: list[float] = []
    for b in briefs:
        if not b.buildable:
            continue
        d = DEMO_CORPUS / b.id
        import json
        entry = json.loads((d / "brief.json").read_text())["entrypoint"]
        cases = load_oracle_cases(d)
        corr = run_oracle(d, module="oracle", entrypoint=entry, cases=cases).correctness
        build_a0.append(corr)   # both arms run the same reference oracle in the demo
        build_a1.append(corr)
    build_tost = tost(build_a0, build_a1, margin=0.05)
    gram_tost = tost([0.0] * len(build_a0), [0.0] * len(build_a0), margin=0.5)
    print("\n== buildability (executed oracle) ==")
    print(f"  buildable briefs {len(build_a0)}  mean correctness {sum(build_a1)/len(build_a1):.3f}")
    print(f"  non-inferiority TOST  non_inferior={build_tost.non_inferior} "
          f"power={build_tost.power:.2f} certifiable={build_tost.certifiable}")

    # -- instrument-trust gate --
    extractor, docs, decoys = _instrument_decoys(broken=(break_mode == "instrument"))
    report = instrument_trust_gate(extractor, docs, decoys)
    print("\n== instrument-trust gate ==")
    for c in report.checks:
        print(f"  {c.name:24} kind={c.kind:16} delta={c.observed_delta:.3f} tol={c.tolerance:.3f} {'PASS' if c.passed else 'FAIL'}")
    print(f"  trusted={report.trusted}")

    # -- multiplicity across the guardrail family (Holm) --
    fam_p = holm_correction([wil.p_value, build_tost.p_value, gram_tost.p_value])
    print(f"\n== Holm-adjusted guardrail-family p-values ==\n  {[round(p,4) for p in fam_p]}")

    # -- decision --
    beats_a3 = (sum(rates["A1"]) / n) < (sum(rates["A3_fair"]) / n) - 1e-9
    beats_a2 = (sum(rates["A1"]) / n) < (sum(rates["A2_placebo"]) / n) - 1e-9
    inputs = DecisionInputs(
        restatement_real=restatement_real,
        substance_ok=not substance_blocks,
        buildability=build_tost,
        grammaticality=gram_tost,
        a3b_fails_grammaticality=a3b_fails,
        instrument_trusted=report.trusted,
        beats_a3_fair=ArmComparison(beats_a3, "A1 mean rate < A3_fair mean rate"),
        beats_a2_placebo=ArmComparison(beats_a2, "A1 mean rate < A2_placebo mean rate"),
        a4_captures_effect=False,
    )
    result = decide(inputs)

    print("\n" + "=" * 70)
    print(f"VERDICT: {result.verdict.value.upper()}")
    for r in result.reasons:
        print(f"  - {r}")
    print("=" * 70)
    print("\nNON-BLIND DEMO DATA — pipeline shakeout only, never a ship decision.")
    print("See corpus/demo/PROVENANCE.md. A real verdict needs the blind corpus")
    print("and the OpenAI (non-Anthropic) extractor actually running.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Over-explanation harness end-to-end demo.")
    parser.add_argument(
        "--break", dest="break_mode", default=None,
        choices=["substance", "length", "grammaticality", "instrument"],
        help="flip one upstream input to watch the matching gate change the verdict",
    )
    args = parser.parse_args(argv)
    return run(args.break_mode)


if __name__ == "__main__":
    raise SystemExit(main())
