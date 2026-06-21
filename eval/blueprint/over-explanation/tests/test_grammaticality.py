from __future__ import annotations

import pytest

from eval_overexplanation.grammaticality import (
    DefaultGrammaticalityChecker,
    SpacyGrammaticalityChecker,
    split_sentences,
)
from eval_overexplanation.models import GrammaticalityReport

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

# Ordinary full grammatical sentences — every one MUST pass (ok=True).
FULL_SENTENCES = (
    "The function returns a list of active users.",
    "If an error occurs, the client retries the request.",
    "The cache entry expires after five minutes.",
    "We raise an exception when the input is malformed.",
    "The service stores each session in a Redis instance.",
    "This module imports anthropic lazily inside the method that needs it.",
    "Each brief is frozen before any treatment arm runs.",
    "The evaluator must not silently drop a load-bearing constraint.",
)

# A3b-style telegraphic decoys — every one MUST be flagged (ok=False). These are
# the dangerous word-drop failure mode the guardrail exists to catch.
TELEGRAPHIC_DECOYS = (
    "Returns list.",
    "If error, retry.",
    "Cache: 5 min TTL.",
    "raise error on bad input.",
    "Validates input.",
    "On failure, retry.",
    "Store in cache.",
    "Reads file, returns string.",
    "No determiner phrase here today",  # missing terminal punctuation too
    "Fetches user from cache.",
)


# --------------------------------------------------------------------------- #
# split_sentences
# --------------------------------------------------------------------------- #


def test_split_on_terminal_punctuation():
    text = "First sentence. Second one! Third?"
    assert split_sentences(text) == (
        "First sentence.",
        "Second one!",
        "Third?",
    )


def test_split_on_newlines_and_strips_whitespace():
    text = "Line one.\n\nLine two.\n  Line three.  "
    assert split_sentences(text) == ("Line one.", "Line two.", "Line three.")


def test_split_empty_text_is_empty_tuple():
    assert split_sentences("") == ()
    assert split_sentences("   \n  \n ") == ()


# --------------------------------------------------------------------------- #
# DefaultGrammaticalityChecker — the core contract
# --------------------------------------------------------------------------- #


def test_full_sentences_all_pass():
    report = DefaultGrammaticalityChecker().check(FULL_SENTENCES)
    assert isinstance(report, GrammaticalityReport)
    failed = [(v.text, v.reason) for v in report.verdicts if not v.ok]
    assert failed == [], f"full sentences were wrongly flagged: {failed}"
    assert report.ok is True
    assert report.fragments == ()


def test_telegraphic_decoys_all_flagged():
    report = DefaultGrammaticalityChecker().check(TELEGRAPHIC_DECOYS)
    passed = [v.text for v in report.verdicts if v.ok]
    assert passed == [], f"telegraphic decoys slipped through (word-drop FN): {passed}"
    assert report.ok is False
    assert len(report.fragments) == len(TELEGRAPHIC_DECOYS)


def test_every_flagged_sentence_has_a_reason():
    report = DefaultGrammaticalityChecker().check(TELEGRAPHIC_DECOYS)
    for v in report.fragments:
        assert v.reason, f"fragment {v.text!r} has no human-readable reason"


def test_verdict_indices_match_input_order():
    sentences = FULL_SENTENCES[:2] + TELEGRAPHIC_DECOYS[:2]
    report = DefaultGrammaticalityChecker().check(sentences)
    assert tuple(v.index for v in report.verdicts) == (0, 1, 2, 3)
    assert tuple(v.text for v in report.verdicts) == sentences


def test_empty_input_is_vacuously_ok():
    report = DefaultGrammaticalityChecker().check(())
    assert report.verdicts == ()
    assert report.ok is True


# --- heuristic-specific boundary cases ------------------------------------- #


def test_dropped_determiner_bigram_flags():
    # H2: verb/prep + bare count noun with no determiner.
    report = DefaultGrammaticalityChecker().check(("Returns list.",))
    v = report.verdicts[0]
    assert v.ok is False
    assert "determiner" in v.reason.lower() or "noun" in v.reason.lower()


def test_determiner_present_does_not_trip_dropped_determiner_rule():
    # Same nouns but with articles -> must pass.
    report = DefaultGrammaticalityChecker().check(
        ("The function returns a list.", "We raise an error in the cache.")
    )
    assert report.ok is True, [v.reason for v in report.fragments]


def test_no_verb_fragment_flags():
    report = DefaultGrammaticalityChecker().check(("Cache: 5 min TTL.",))
    v = report.verdicts[0]
    assert v.ok is False
    assert "verb" in v.reason.lower()


def test_lowercase_start_flags():
    report = DefaultGrammaticalityChecker().check(("raise error on bad input.",))
    assert report.verdicts[0].ok is False


def test_missing_terminal_punctuation_flags():
    report = DefaultGrammaticalityChecker().check(
        ("The function returns a list of users",)
    )
    v = report.verdicts[0]
    assert v.ok is False
    assert "punctuation" in v.reason.lower()


def test_list_marker_is_stripped_before_judging():
    # A grammatical full sentence behind a bullet marker must still pass.
    report = DefaultGrammaticalityChecker().check(
        ("- The service stores each session in a database.",)
    )
    assert report.ok is True, report.fragments
    # But a telegraphic bullet item must still fail.
    report2 = DefaultGrammaticalityChecker().check(("1. Returns list.",))
    assert report2.verdicts[0].ok is False


def test_satisfies_protocol():
    from eval_overexplanation.interfaces import GrammaticalityChecker

    assert isinstance(DefaultGrammaticalityChecker(), GrammaticalityChecker)


# --------------------------------------------------------------------------- #
# SpacyGrammaticalityChecker — import-safety without the [nlp] extra
# --------------------------------------------------------------------------- #


def test_spacy_checker_constructs_without_extra():
    # Constructing must not require spacy (lazy import inside check/_load).
    checker = SpacyGrammaticalityChecker()
    assert checker is not None


def test_spacy_checker_raises_clear_error_without_model():
    pytest.importorskip  # keep import available; not strictly needed
    checker = SpacyGrammaticalityChecker(model="en_core_web_sm")
    try:
        import spacy  # noqa: F401

        has_spacy = True
    except ImportError:
        has_spacy = False

    if not has_spacy:
        with pytest.raises(ImportError) as exc:
            checker.check(("Hello world.",))
        assert "nlp" in str(exc.value).lower()
    else:
        # spaCy present but model likely absent in CI -> ImportError w/ download hint.
        try:
            report = checker.check(("The function returns a list.",))
        except ImportError as exc:
            assert "spacy download" in str(exc.value).lower() or "nlp" in str(
                exc.value
            ).lower()
        else:
            assert report.ok in (True, False)
