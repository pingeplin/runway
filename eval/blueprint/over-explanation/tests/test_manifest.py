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
    assert reg.version == "milestone-1"
    assert len(reg.briefs) == 9
    assert reg.seeds == (1, 2)
    assert len(reg.extractor_families) == 2
    arm_ids = {a.id for a in reg.arms}
    assert {"A0", "A1", "A3_fair", "A2_placebo"} == arm_ids
    # every brief carries a frozen regime
    assert all(isinstance(b.regime, Regime) for b in reg.briefs)


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
