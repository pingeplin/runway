"""Tests for the corpus loaders.

Exercise the loaders against the shipped ``corpus/example-brief`` worked example
and against hand-built fixtures under ``tmp_path``: a brief round-trips into a
:class:`Brief`, the gold set parses into a :class:`PropositionSet`, the oracle
cases parse into :class:`OracleCase` tuples, an unknown regime raises, a missing
``cases.json`` yields ``()`` while a malformed one raises, and ``load_corpus``
discovers the example brief. No network, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_overexplanation.corpus import (
    load_brief,
    load_corpus,
    load_gold,
    load_oracle_cases,
)
from eval_overexplanation.models import (
    Brief,
    OracleCase,
    PropositionSet,
    Regime,
    Tier,
)

# The shipped worked example lives two levels up from tests/ under corpus/.
EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "corpus" / "example-brief"


# --------------------------------------------------------------------------- #
# The shipped worked example must load exactly.
# --------------------------------------------------------------------------- #


def test_example_brief_loads() -> None:
    brief = load_brief(EXAMPLE_DIR)
    assert isinstance(brief, Brief)
    assert brief.id == "example-brief"
    assert brief.title == "Running total"
    assert brief.regime is Regime.NEUTRAL
    assert brief.buildable is True
    # brief.md body flows into .text.
    assert "running_total" in brief.text
    assert brief.text.strip() != ""


def test_example_gold_parses_into_proposition_set() -> None:
    gold = load_gold(EXAMPLE_DIR)
    assert isinstance(gold, PropositionSet)
    assert gold.document_id == "example-brief-gold"
    assert gold.distinct == 5
    by_id = gold.by_id()
    # tiers survive the round-trip.
    assert by_id["p1"].tier is Tier.MUST
    assert by_id["p5"].tier is Tier.DETAIL
    # the MUST tier holds exactly the two required claims.
    assert {p.id for p in gold.tier(Tier.MUST)} == {"p1", "p2"}
    # multi-mention proposition keeps both sentence indices.
    assert by_id["p1"].mention_sentences == (0, 4)


def test_example_cases_parse_into_oracle_case_tuples() -> None:
    cases = load_oracle_cases(EXAMPLE_DIR)
    assert isinstance(cases, tuple)
    assert all(isinstance(c, OracleCase) for c in cases)
    assert len(cases) == 5
    simple = next(c for c in cases if c.label == "simple")
    # args is the splat-able argument tuple: one list argument.
    assert simple.args == ([1, 2, 3],)
    assert simple.expected == [1, 3, 6]
    empty = next(c for c in cases if c.label == "empty")
    assert empty.args == ([],)
    assert empty.expected == []


def test_load_corpus_discovers_the_example() -> None:
    root = EXAMPLE_DIR.parent
    briefs = load_corpus(root)
    ids = {b.id for b in briefs}
    assert "example-brief" in ids
    example = next(b for b in briefs if b.id == "example-brief")
    assert example.regime is Regime.NEUTRAL


# --------------------------------------------------------------------------- #
# Hand-built fixtures under tmp_path.
# --------------------------------------------------------------------------- #


def _write(brief_dir: Path, name: str, obj: object) -> None:
    brief_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        (brief_dir / name).write_text(obj, encoding="utf-8")
    else:
        (brief_dir / name).write_text(json.dumps(obj), encoding="utf-8")


def _valid_brief(brief_dir: Path, *, regime: str = "neutral",
                 buildable: bool = False) -> None:
    _write(brief_dir, "brief.json", {
        "id": brief_dir.name,
        "title": "T",
        "regime": regime,
        "buildable": buildable,
    })
    _write(brief_dir, "brief.md", "# body\nSome text.")
    _write(brief_dir, "gold_propositions.json", {
        "document_id": f"{brief_dir.name}-gold",
        "propositions": [
            {"id": "g1", "text": "claim", "kind": "k", "tier": "must",
             "mention_sentences": [0]},
        ],
    })


def test_unknown_regime_raises(tmp_path: Path) -> None:
    d = tmp_path / "b"
    _valid_brief(d, regime="impossible")
    with pytest.raises(ValueError, match="unknown regime"):
        load_brief(d)


def test_gold_default_tier_is_should(tmp_path: Path) -> None:
    d = tmp_path / "b"
    d.mkdir()
    _write(d, "gold_propositions.json", {
        "document_id": "g",
        "propositions": [
            {"id": "g1", "text": "c", "kind": "k", "mention_sentences": [0]},
        ],
    })
    gold = load_gold(d)
    assert gold.by_id()["g1"].tier is Tier.SHOULD


def test_gold_zero_mentions_rejected_by_model(tmp_path: Path) -> None:
    d = tmp_path / "b"
    d.mkdir()
    _write(d, "gold_propositions.json", {
        "document_id": "g",
        "propositions": [
            {"id": "g1", "text": "c", "kind": "k", "mention_sentences": []},
        ],
    })
    with pytest.raises(ValueError):
        load_gold(d)


def test_missing_cases_yields_empty_tuple(tmp_path: Path) -> None:
    d = tmp_path / "b"
    _valid_brief(d, buildable=False)
    assert load_oracle_cases(d) == ()


def test_malformed_cases_json_raises(tmp_path: Path) -> None:
    d = tmp_path / "b"
    _valid_brief(d, buildable=True)
    # syntactically broken JSON.
    (d / "cases.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON"):
        load_oracle_cases(d)


def test_cases_wrong_shape_raises(tmp_path: Path) -> None:
    d = tmp_path / "b"
    _valid_brief(d, buildable=True)
    # well-formed JSON, wrong shape (missing 'cases').
    _write(d, "cases.json", {"oops": []})
    with pytest.raises(ValueError, match="'cases' must be a list"):
        load_oracle_cases(d)


def test_case_missing_key_raises(tmp_path: Path) -> None:
    d = tmp_path / "b"
    _valid_brief(d, buildable=True)
    _write(d, "cases.json", {"cases": [{"label": "x", "args": [1]}]})
    with pytest.raises(ValueError, match="missing required key 'expected'"):
        load_oracle_cases(d)


def test_load_corpus_skips_dirs_without_brief_json(tmp_path: Path) -> None:
    _valid_brief(tmp_path / "good")
    (tmp_path / "scaffold").mkdir()
    (tmp_path / "scaffold" / "notes.md").write_text("hi", encoding="utf-8")
    # a stray file at root level must not break iteration.
    (tmp_path / "README.md").write_text("root", encoding="utf-8")
    briefs = load_corpus(tmp_path)
    assert {b.id for b in briefs} == {"good"}


def test_load_corpus_sorted_by_id(tmp_path: Path) -> None:
    _valid_brief(tmp_path / "zeta")
    _valid_brief(tmp_path / "alpha")
    briefs = load_corpus(tmp_path)
    assert [b.id for b in briefs] == ["alpha", "zeta"]


def test_missing_required_brief_key_raises(tmp_path: Path) -> None:
    d = tmp_path / "b"
    d.mkdir()
    _write(d, "brief.json", {"id": "b", "title": "T", "regime": "neutral"})
    with pytest.raises(ValueError, match="missing required key 'buildable'"):
        load_brief(d)


def test_brief_without_md_yields_empty_text(tmp_path: Path) -> None:
    d = tmp_path / "b"
    d.mkdir()
    _write(d, "brief.json", {
        "id": "b", "title": "T", "regime": "large_realistic", "buildable": False,
    })
    brief = load_brief(d)
    assert brief.text == ""
    assert brief.regime is Regime.LARGE_REALISTIC
