from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_overexplanation.manifest import (
    DecisionThresholds,
    PreRegistration,
    dump_manifest,
    load_manifest,
)
from eval_overexplanation.models import Arm, Brief, Regime

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "preregistration"
    / "manifest.example.json"
)


def _minimal_reg(
    *,
    seeds: tuple[int, ...] = (1, 2),
    families: tuple[str, ...] = ("anthropic-claude", "openai-gpt"),
    arms: tuple[Arm, ...] | None = None,
) -> PreRegistration:
    if arms is None:
        arms = (
            Arm(id="A0", label="baseline", plugin_ref="ref0"),
            Arm(id="A1", label="treatment", plugin_ref="ref1"),
        )
    return PreRegistration(
        version="test",
        arms=arms,
        briefs=(
            Brief(id="b01", title="One", regime=Regime.NEUTRAL, buildable=True),
            Brief(
                id="b02",
                title="Two",
                regime=Regime.LARGE_REALISTIC,
                buildable=False,
            ),
        ),
        seeds=seeds,
        extractor_families=families,
        thresholds=DecisionThresholds(),
    )


# --------------------------------------------------------------------------- #
# Round-trip
# --------------------------------------------------------------------------- #


def test_round_trip_is_stable(tmp_path: Path) -> None:
    reg = _minimal_reg()
    text = dump_manifest(reg)
    path = tmp_path / "m.json"
    path.write_text(text, encoding="utf-8")

    loaded = load_manifest(path)
    assert loaded == reg
    # dump -> load -> dump is byte-stable
    assert dump_manifest(loaded) == text


def test_dump_is_canonical_sorted_keys() -> None:
    text = dump_manifest(_minimal_reg())
    parsed_keys = list(json.loads(text).keys())
    assert parsed_keys == sorted(parsed_keys)


# --------------------------------------------------------------------------- #
# content_hash stability + sensitivity
# --------------------------------------------------------------------------- #


def test_content_hash_is_stable_across_equal_regs() -> None:
    assert _minimal_reg().content_hash() == _minimal_reg().content_hash()


def test_content_hash_changes_when_seed_changes() -> None:
    a = _minimal_reg(seeds=(1, 2))
    b = _minimal_reg(seeds=(1, 3))
    assert a.content_hash() != b.content_hash()


def test_content_hash_changes_when_family_changes() -> None:
    a = _minimal_reg(families=("anthropic-claude", "openai-gpt"))
    b = _minimal_reg(families=("anthropic-claude", "google-gemini"))
    assert a.content_hash() != b.content_hash()


def test_content_hash_changes_when_threshold_changes() -> None:
    base = _minimal_reg()
    tweaked = PreRegistration(
        version=base.version,
        arms=base.arms,
        briefs=base.briefs,
        seeds=base.seeds,
        extractor_families=base.extractor_families,
        thresholds=DecisionThresholds(min_power=0.9),
    )
    assert base.content_hash() != tweaked.content_hash()


def test_content_hash_is_sha256_hex() -> None:
    h = _minimal_reg().content_hash()
    assert len(h) == 64
    int(h, 16)  # valid hex


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #


def test_validate_clean_on_well_formed_reg() -> None:
    assert _minimal_reg().validate() == ()


def test_validate_flags_missing_seeds() -> None:
    problems = _minimal_reg(seeds=()).validate()
    assert any("seed" in p for p in problems)


def test_validate_flags_missing_a0() -> None:
    arms = (Arm(id="A1", label="t", plugin_ref="r"),)
    problems = _minimal_reg(arms=arms).validate()
    assert any("A0" in p for p in problems)


def test_validate_flags_missing_a1() -> None:
    arms = (Arm(id="A0", label="b", plugin_ref="r"),)
    problems = _minimal_reg(arms=arms).validate()
    assert any("A1" in p for p in problems)


def test_validate_warns_on_single_extractor_family() -> None:
    problems = _minimal_reg(families=("anthropic-claude",)).validate()
    assert any("two extractor families" in p for p in problems)


def test_validate_warning_is_not_an_exception() -> None:
    # A single-family reg still validates structurally; the family shortfall is
    # returned as a problem string, never raised.
    reg = _minimal_reg(families=("only-one",))
    result = reg.validate()
    assert isinstance(result, tuple)


# --------------------------------------------------------------------------- #
# The shipped example file
# --------------------------------------------------------------------------- #


def test_example_file_loads_and_validates_clean() -> None:
    reg = load_manifest(EXAMPLE_PATH)
    assert reg.validate() == ()


def test_example_file_round_trips() -> None:
    reg = load_manifest(EXAMPLE_PATH)
    reloaded = load_manifest(EXAMPLE_PATH)
    assert dump_manifest(reg) == dump_manifest(reloaded)
    assert reg.content_hash() == reloaded.content_hash()


def test_example_file_has_expected_shape() -> None:
    reg = load_manifest(EXAMPLE_PATH)
    # bench-registered manifests carry the audit-trail version prefix (§4).
    assert reg.version == "bench-1-milestone-1"
    assert len(reg.briefs) == 9
    assert reg.seeds == (1, 2)
    assert len(reg.extractor_families) == 2
    arm_ids = {a.id for a in reg.arms}
    assert {"A0", "A1", "A3_fair", "A2_placebo", "A3b_dumb"} == arm_ids
    # every brief carries a frozen regime
    assert all(isinstance(b.regime, Regime) for b in reg.briefs)
    assert reg.bench is not None
    assert set(reg.bench.u_arms) <= arm_ids


def test_unknown_regime_raises(tmp_path: Path) -> None:
    bad = {
        "version": "x",
        "arms": [
            {"id": "A0", "label": "b", "plugin_ref": "r", "evaluator": {}, "description": ""},
            {"id": "A1", "label": "t", "plugin_ref": "r", "evaluator": {}, "description": ""},
        ],
        "briefs": [
            {"id": "b1", "title": "t", "regime": "not_a_regime", "buildable": True, "text": ""}
        ],
        "seeds": [1],
        "extractor_families": ["a", "b"],
        "thresholds": {"noise_floor_multiple": 2.0, "tost_margin": 0.0, "min_power": 0.8},
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


# --------------------------------------------------------------------------- #
# BenchThresholds (BLUEPRINT-BENCH §4)
# --------------------------------------------------------------------------- #


def _bench_reg(**bench_over) -> PreRegistration:
    from eval_overexplanation.manifest import BenchThresholds
    from eval_overexplanation.models import Arm

    base = _minimal_reg()
    arms = base.arms + (
        Arm(id="A2_placebo", label="p", plugin_ref="r"),
        Arm(id="A3_fair", label="f", plugin_ref="r"),
        Arm(id="A3b_dumb", label="d", plugin_ref="r"),
    )
    bench_kwargs: dict = {
        "implementer_ref": "pinned-model-x",
        "preamble_template": "Implement {module}.{entrypoint} now.",
    }
    bench_kwargs.update(bench_over)
    bench = BenchThresholds(**bench_kwargs)
    return PreRegistration(
        version="bench-1-test",
        arms=arms,
        briefs=base.briefs,
        seeds=base.seeds,
        extractor_families=base.extractor_families,
        thresholds=base.thresholds,
        bench=bench,
    )


def test_bench_round_trips_and_hashes_stably(tmp_path: Path) -> None:
    reg = _bench_reg()
    text = dump_manifest(reg)
    path = tmp_path / "m.json"
    path.write_text(text, encoding="utf-8")
    loaded = load_manifest(path)
    assert loaded == reg
    assert dump_manifest(loaded) == text
    assert loaded.content_hash() == reg.content_hash()


def test_bench_absence_keeps_prebench_hash_shape() -> None:
    # Pre-bench registrations must keep their historical hashes: no "bench"
    # key is serialized when the block is absent.
    reg = _minimal_reg()
    assert "bench" not in json.loads(dump_manifest(reg))


def test_bench_changes_the_hash_by_design() -> None:
    import dataclasses

    with_bench = _bench_reg()
    without = dataclasses.replace(with_bench, bench=None)
    assert with_bench.content_hash() != without.content_hash()


def test_bench_threshold_edit_changes_the_hash() -> None:
    import dataclasses

    a = _bench_reg()
    b = dataclasses.replace(a, bench=dataclasses.replace(a.bench,
                                                         dead_end_cap=7))
    assert a.content_hash() != b.content_hash()


def test_bench_validate_clean_on_well_formed() -> None:
    assert _bench_reg().validate() == ()


def test_bench_validate_requires_version_prefix() -> None:
    import dataclasses

    reg = dataclasses.replace(_bench_reg(), version="milestone-1")
    assert any("bench-1-" in p for p in reg.validate())


def test_bench_validate_u_arms_subset_of_arms() -> None:
    problems = _bench_reg(
        u_arms=("A0", "A1", "A2_placebo", "A3_fair", "A3b_dumb", "A9"),
    ).validate()
    assert any("u_arms" in p and "A9" in p for p in problems)


def test_bench_validate_requires_a3b_dumb_in_u_arms() -> None:
    problems = _bench_reg(u_arms=("A0", "A1")).validate()
    assert any("A3b_dumb" in p for p in problems)


def test_bench_validate_weights_must_sum_to_one() -> None:
    problems = _bench_reg(
        weights={"C": 0.5, "U": 0.3, "O": 0.3}).validate()
    assert any("sum to 1.0" in p for p in problems)


def test_bench_validate_requires_both_placeholders() -> None:
    problems = _bench_reg(
        preamble_template="Implement {module} now.").validate()
    assert any("{entrypoint}" in p for p in problems)


def test_bench_validate_requires_nonempty_implementer_ref() -> None:
    problems = _bench_reg(implementer_ref="").validate()
    assert any("implementer_ref" in p for p in problems)


def test_bench_validate_mutations_per_brief_is_eight() -> None:
    problems = _bench_reg(mutations_per_brief=6).validate()
    assert any("mutations_per_brief" in p for p in problems)


@pytest.mark.parametrize("field, value", [
    ("win_alpha", 0.01),
    ("c_min_den", 0.03),
    ("u_min_den", 0.06),
    ("u_noise_multiple", 3.0),
    ("o_weight_correctness", 0.6),
    ("o_weight_kill", 0.25),
    ("o_weight_bloat", 0.15),
    ("max_o_term_skipped_fraction", 0.2),
])
def test_bench_operative_field_edit_changes_the_hash(field, value) -> None:
    # Regression (round-3 MAJOR): every operative scoring number must live
    # under content_hash — an edit that leaves the hash unmoved would dodge
    # the audit trail.
    import dataclasses

    a = _bench_reg()
    b = dataclasses.replace(
        a, bench=dataclasses.replace(a.bench, **{field: value}))
    assert a.content_hash() != b.content_hash(), field


def test_bench_validate_o_weights_must_sum_to_one() -> None:
    problems = _bench_reg(o_weight_correctness=0.7).validate()
    assert any("o_weight" in p and "sum to 1.0" in p for p in problems)


def _asset_corpus(tmp_path: Path, *, holdout: bool = True,
                  mutations: int | None = 8) -> Path:
    corpus = tmp_path / "corpus"
    d = corpus / "b01"   # _bench_reg's only buildable brief
    d.mkdir(parents=True)
    (d / "brief.json").write_text(json.dumps(
        {"id": "b01", "module": "m", "entrypoint": "e"}))
    (d / "cases.json").write_text(json.dumps({"cases": []}))
    if holdout:
        (d / "cases_holdout.json").write_text(json.dumps({"cases": []}))
    if mutations is not None:
        (d / "mutations.json").write_text(json.dumps({"mutations": [
            {"label": f"m{i}", "filename": "m.py", "find": "a",
             "replace": "b"} for i in range(mutations)]}))
    return corpus


def test_validate_corpus_root_clean_when_assets_present(
        tmp_path: Path) -> None:
    corpus = _asset_corpus(tmp_path)
    assert _bench_reg().validate(corpus_root=corpus) == ()


def test_validate_corpus_root_flags_missing_holdout(tmp_path: Path) -> None:
    # §4 asset rule: a buildable brief without its blind holdout is a
    # manifest problem (=> scorable:false), never a quiet per-cell skip.
    corpus = _asset_corpus(tmp_path, holdout=False)
    problems = _bench_reg().validate(corpus_root=corpus)
    assert any("b01" in p and "cases_holdout.json" in p for p in problems)


def test_validate_corpus_root_flags_missing_mutations(tmp_path: Path) -> None:
    corpus = _asset_corpus(tmp_path, mutations=None)
    problems = _bench_reg().validate(corpus_root=corpus)
    assert any("b01" in p and "mutations.json" in p for p in problems)


def test_validate_corpus_root_flags_wrong_mutation_count(
        tmp_path: Path) -> None:
    corpus = _asset_corpus(tmp_path, mutations=5)
    problems = _bench_reg().validate(corpus_root=corpus)
    assert any("b01" in p and "5 mutations" in p for p in problems)


def test_validate_corpus_root_flags_missing_interface_pin(
        tmp_path: Path) -> None:
    corpus = _asset_corpus(tmp_path)
    (corpus / "b01" / "brief.json").write_text(json.dumps({"id": "b01"}))
    problems = _bench_reg().validate(corpus_root=corpus)
    assert any("b01" in p and "module/entrypoint" in p for p in problems)


def test_validate_corpus_root_ignores_non_buildable_briefs(
        tmp_path: Path) -> None:
    # b02 is buildable:false — no corpus dir needed for it.
    corpus = _asset_corpus(tmp_path)
    problems = _bench_reg().validate(corpus_root=corpus)
    assert not any("b02" in p for p in problems)


def test_validate_without_corpus_root_skips_asset_rules() -> None:
    assert _bench_reg().validate() == ()


def test_bench_keeps_two_distinct_noise_multiples() -> None:
    # The §4 trap the score fixer closed: gate (2.0) and scale (4.0) are two
    # separate frozen fields, and the shipped demo manifest carries both.
    demo = load_manifest(
        EXAMPLE_PATH.parent / "manifest.demo.json")
    assert demo.bench is not None
    assert demo.bench.c1_gate_noise_multiple == 2.0
    assert demo.bench.c_scale_noise_multiple == 4.0
    assert demo.validate() == ()


def test_demo_manifest_preamble_matches_run_implementer_template() -> None:
    # The manifest's frozen preamble must be the byte-identical template
    # run-implementer.sh embeds (preamble_template_sha is a U0 gate input).
    import re

    demo = load_manifest(EXAMPLE_PATH.parent / "manifest.demo.json")
    script = (EXAMPLE_PATH.parents[1] / "scripts" /
              "run-implementer.sh").read_text(encoding="utf-8")
    match = re.search(r"PREAMBLE_TEMPLATE='([^']*)'", script)
    assert match is not None
    assert demo.bench is not None
    assert demo.bench.preamble_template == match.group(1)


def test_demo_manifest_max_retries_matches_run_implementer_default() -> None:
    # bench.max_retries is consumed as run-implementer.sh's MAX_RETRIES
    # default; a drift between the frozen manifest and the script would make
    # the recorded retry budget a fiction.
    import re

    demo = load_manifest(EXAMPLE_PATH.parent / "manifest.demo.json")
    script = (EXAMPLE_PATH.parents[1] / "scripts" /
              "run-implementer.sh").read_text(encoding="utf-8")
    match = re.search(r'MAX_RETRIES="\$\{MAX_RETRIES:-(\d+)\}"', script)
    assert match is not None
    assert demo.bench is not None
    assert demo.bench.max_retries == int(match.group(1))
