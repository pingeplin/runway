"""Tests for the instrument-trust gate (atomization / manipulation invariance).

Offline only: a hand-built ``FixtureExtractor`` maps each ``document_id`` to a
controlled ``PropositionSet`` so we can drive the distinct-count and
restatement-rate exactly. No network, no real LLM.
"""

from __future__ import annotations

import pytest

from eval_overexplanation.extractor import FixtureExtractor
from eval_overexplanation.instrument import (
    Decoy,
    InstrumentReport,
    instrument_trust_gate,
)
from eval_overexplanation.models import Proposition, PropositionSet


def _prop(pid: str, mentions: tuple[int, ...]) -> Proposition:
    return Proposition(id=pid, text=pid, kind="assertion", mention_sentences=mentions)


def _set(doc_id: str, *props: Proposition) -> PropositionSet:
    return PropositionSet(document_id=doc_id, propositions=props)


# Texts are irrelevant to FixtureExtractor (it keys off document_id), but the
# gate still passes them through, so supply placeholders.
def _docs(*ids: str) -> dict[str, str]:
    return {i: f"text for {i}" for i in ids}


# --------------------------------------------------------------------------- #
# atomization: |distinct(variant) - distinct(base)| <= tolerance
# --------------------------------------------------------------------------- #


def test_atomization_passes_when_distinct_count_unchanged() -> None:
    # Base packs two claims in one sentence; variant splits into two sentences.
    # Same TWO distinct propositions -> distinct delta 0.
    base = _set("base", _prop("a", (0,)), _prop("b", (0,)))
    variant = _set("var", _prop("a", (0,)), _prop("b", (1,)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("split", "base", "var", "atomization", tolerance=0.0)

    report = instrument_trust_gate(ext, _docs("base", "var"), [decoy])

    assert isinstance(report, InstrumentReport)
    (check,) = report.checks
    assert check.observed_delta == 0.0
    assert check.passed
    assert report.trusted


def test_atomization_fails_when_split_invents_a_proposition() -> None:
    # Splitting spuriously yields a THIRD distinct proposition -> delta 1 > tol.
    base = _set("base", _prop("a", (0,)), _prop("b", (0,)))
    variant = _set("var", _prop("a", (0,)), _prop("b", (1,)), _prop("c", (2,)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("split", "base", "var", "atomization", tolerance=0.0)

    report = instrument_trust_gate(ext, _docs("base", "var"), [decoy])

    (check,) = report.checks
    assert check.observed_delta == 1.0
    assert not check.passed
    assert not report.trusted


def test_atomization_is_symmetric_a_merge_drop_also_fails() -> None:
    # A merge that LOSES a distinct proposition is just as bad as a split that
    # invents one; the |.| makes the check symmetric.
    base = _set("base", _prop("a", (0,)), _prop("b", (1,)), _prop("c", (2,)))
    variant = _set("var", _prop("a", (0,)), _prop("b", (1,)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("merge", "base", "var", "atomization", tolerance=0.0)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == 1.0
    assert not check.passed


# --------------------------------------------------------------------------- #
# length_confound: max(0, rate_base - rate_variant) <= tolerance
# (only a rate DROP is penalised)
# --------------------------------------------------------------------------- #


def test_length_confound_passes_when_rate_holds_or_rises() -> None:
    # Base rate = 1 - 2/3. Variant pads with a novel single-mention prop but the
    # restatement is preserved so the rate does not DROP (it rises slightly is
    # fine too; here we keep it equal-or-higher). A RISE is harmless -> max(0,.).
    base = _set("base", _prop("a", (0,)), _prop("b", (1, 2)))  # rate 1/3
    # Variant keeps the same repeat structure -> identical rate -> delta 0.
    variant = _set("var", _prop("a", (0,)), _prop("b", (1, 2)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("pad", "base", "var", "length_confound", tolerance=0.0)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == 0.0
    assert check.passed


def test_length_confound_rise_in_rate_is_not_penalised() -> None:
    # Variant rate HIGHER than base: max(0, base - variant) == 0 -> passes even
    # at zero tolerance. Only a drop is a failure.
    base = _set("base", _prop("a", (0,)), _prop("b", (1, 2)))  # rate 1/3
    variant = _set("var", _prop("a", (0,)), _prop("b", (1, 2, 3)))  # rate 1/2
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("pad", "base", "var", "length_confound", tolerance=0.0)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == 0.0
    assert check.passed


def test_length_confound_fails_when_padding_lowers_the_rate() -> None:
    # Padding with novel single-mention propositions DILUTES the rate: base 1/3
    # drops toward 0. That drop exceeds tolerance -> fail.
    base = _set("base", _prop("a", (0,)), _prop("b", (1, 2)))  # rate 1/3
    variant = _set(
        "var",
        _prop("a", (0,)),
        _prop("b", (1, 2)),
        _prop("pad1", (3,)),
        _prop("pad2", (4,)),
    )  # rate = 1 - 4/5 = 1/5
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("pad", "base", "var", "length_confound", tolerance=0.05)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == pytest.approx(1 / 3 - 1 / 5)
    assert not check.passed


# --------------------------------------------------------------------------- #
# defensive_filler: max(0, distinct(variant) - distinct(base)) <= tolerance
# (only a distinct RISE is penalised)
# --------------------------------------------------------------------------- #


def test_defensive_filler_passes_when_distinct_count_holds() -> None:
    base = _set("base", _prop("a", (0,)), _prop("b", (1,)))
    variant = _set("var", _prop("a", (0,)), _prop("b", (1,)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("hedge", "base", "var", "defensive_filler", tolerance=0.0)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == 0.0
    assert check.passed


def test_defensive_filler_drop_in_distinct_is_not_penalised() -> None:
    # A DROP in distinct count is harmless for this kind: max(0, var - base)==0.
    base = _set("base", _prop("a", (0,)), _prop("b", (1,)), _prop("c", (2,)))
    variant = _set("var", _prop("a", (0,)), _prop("b", (1,)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("hedge", "base", "var", "defensive_filler", tolerance=0.0)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == 0.0
    assert check.passed


def test_defensive_filler_fails_when_filler_inflates_distinct() -> None:
    # Hedging prose is mistaken for two new claims -> distinct rises by 2 > tol.
    base = _set("base", _prop("a", (0,)), _prop("b", (1,)))
    variant = _set(
        "var",
        _prop("a", (0,)),
        _prop("b", (1,)),
        _prop("hedge1", (2,)),
        _prop("hedge2", (3,)),
    )
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("hedge", "base", "var", "defensive_filler", tolerance=1.0)

    (check,) = instrument_trust_gate(ext, _docs("base", "var"), [decoy]).checks
    assert check.observed_delta == 2.0
    assert not check.passed


# --------------------------------------------------------------------------- #
# Report-level property: trusted iff EVERY check passed.
# --------------------------------------------------------------------------- #


def test_trusted_is_true_iff_all_checks_pass() -> None:
    base = _set("base", _prop("a", (0,)), _prop("b", (1, 2)))
    pass_var = _set("ok", _prop("a", (0,)), _prop("b", (1, 2)))
    fail_var = _set(
        "bad",
        _prop("a", (0,)),
        _prop("b", (1, 2)),
        _prop("c", (3,)),  # invents a claim -> atomization delta 1
    )
    ext = FixtureExtractor(
        sets={"base": base, "ok": pass_var, "bad": fail_var}
    )
    docs = _docs("base", "ok", "bad")

    good = Decoy("g", "base", "ok", "atomization", tolerance=0.0)
    bad = Decoy("b", "base", "bad", "atomization", tolerance=0.0)

    # All good -> trusted.
    rep_ok = instrument_trust_gate(ext, docs, [good])
    assert all(c.passed for c in rep_ok.checks)
    assert rep_ok.trusted is True

    # One failing check among passing ones -> NOT trusted.
    rep_mixed = instrument_trust_gate(ext, docs, [good, bad])
    assert [c.passed for c in rep_mixed.checks] == [True, False]
    assert rep_mixed.trusted is False


def test_unknown_kind_raises_valueerror() -> None:
    base = _set("base", _prop("a", (0,)))
    variant = _set("var", _prop("a", (0,)))
    ext = FixtureExtractor(sets={"base": base, "var": variant})
    decoy = Decoy("weird", "base", "var", "not_a_kind", tolerance=0.0)
    with pytest.raises(ValueError):
        instrument_trust_gate(ext, _docs("base", "var"), [decoy])


def test_empty_decoys_yield_trusted_report() -> None:
    ext = FixtureExtractor(sets={})
    report = instrument_trust_gate(ext, {}, [])
    assert report.checks == ()
    assert report.trusted  # vacuously trusted; all() over empty is True
