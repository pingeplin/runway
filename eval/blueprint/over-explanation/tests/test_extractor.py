"""Tests for the extractor leaf.

Covers ``FixtureExtractor`` fully (extract + align, including the documented
``KeyError`` paths) and asserts ``AnthropicExtractor`` fails with a clear,
actionable ``ImportError`` when the ``llm`` extra is absent. The parse helpers
are exercised without any network by calling them on hand-built JSON. NEVER call
the network here.
"""

from __future__ import annotations

import builtins
import importlib.util

import pytest

from eval_overexplanation import extractor as extractor_mod
from eval_overexplanation.extractor import (
    INDEPENDENT_ONTOLOGY,
    AnthropicExtractor,
    FixtureExtractor,
    OpenAIExtractor,
    _anthropic_request,
    _BaseLLMExtractor,
    _openai_request,
)
from eval_overexplanation.models import (
    Alignment,
    Proposition,
    PropositionLink,
    PropositionSet,
    Relation,
    Tier,
)

# --------------------------------------------------------------------------- #
# Hand-built fixtures (no network, no LLM)
# --------------------------------------------------------------------------- #


def _source_set() -> PropositionSet:
    return PropositionSet(
        document_id="A0",
        propositions=(
            Proposition("s1", "cache must be flushed", "directive", Tier.MUST, (0,)),
            Proposition("s2", "returns a list of ids", "specification", Tier.SHOULD, (1, 2)),
        ),
    )


def _target_set() -> PropositionSet:
    return PropositionSet(
        document_id="A1",
        propositions=(
            Proposition("t1", "flush the cache", "directive", Tier.MUST, (0,)),
        ),
    )


def _alignment() -> Alignment:
    src, tgt = _source_set(), _target_set()
    return Alignment(
        source=src,
        target=tgt,
        links=(
            PropositionLink("s1", "t1", Relation.PRESERVED),
            PropositionLink("s2", None, Relation.DROPPED),
        ),
    )


# --------------------------------------------------------------------------- #
# Independent ontology
# --------------------------------------------------------------------------- #

# Change ②'s six keep-categories — the extractor MUST NOT reuse these verbatim.
_CHANGE2_KEEP_CATEGORIES = frozenset(
    {
        "fact",
        "decision",
        "constraint",
        "interface-detail",
        "rejected-alternative",
        "testable-behavior",
    }
)


def test_independent_ontology_does_not_reuse_change2_categories():
    assert frozenset(INDEPENDENT_ONTOLOGY).isdisjoint(_CHANGE2_KEEP_CATEGORIES)
    assert len(INDEPENDENT_ONTOLOGY) >= 1


# --------------------------------------------------------------------------- #
# FixtureExtractor
# --------------------------------------------------------------------------- #


def test_fixture_extract_returns_canned_set():
    src = _source_set()
    ext = FixtureExtractor(sets={"A0": src})
    out = ext.extract("A0", "the document text is ignored")
    assert out is src
    assert out.distinct == 2
    assert out.total_mentions == 3


def test_fixture_extract_ignores_text_for_determinism():
    src = _source_set()
    ext = FixtureExtractor(sets={"A0": src})
    assert ext.extract("A0", "one text") is ext.extract("A0", "another text")


def test_fixture_extract_unknown_id_raises_keyerror():
    ext = FixtureExtractor(sets={"A0": _source_set()})
    with pytest.raises(KeyError):
        ext.extract("nope", "text")


def test_fixture_align_returns_canned_alignment():
    src, tgt = _source_set(), _target_set()
    align = _alignment()
    ext = FixtureExtractor(sets={}, alignments={("A0", "A1"): align})
    out = ext.align(src, tgt)
    assert out is align
    assert out.links_for(Relation.DROPPED)[0].source_id == "s2"


def test_fixture_align_unknown_pair_raises_keyerror():
    ext = FixtureExtractor(sets={}, alignments={})
    with pytest.raises(KeyError):
        ext.align(_source_set(), _target_set())


def test_fixture_align_defaults_to_empty_when_omitted():
    ext = FixtureExtractor(sets={"A0": _source_set()})
    with pytest.raises(KeyError):
        ext.align(_source_set(), _target_set())


def test_fixture_extractor_satisfies_protocol():
    from eval_overexplanation.interfaces import PropositionExtractor

    ext = FixtureExtractor(sets={"A0": _source_set()})
    assert isinstance(ext, PropositionExtractor)


# --------------------------------------------------------------------------- #
# AnthropicExtractor: import-safety and the missing-extra ImportError
# --------------------------------------------------------------------------- #

_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None


def test_module_imports_without_anthropic():
    # The module is already imported at top of file; reaching here proves the
    # module-level import does not require the optional extra.
    assert extractor_mod is not None


def test_anthropic_extractor_without_extra_raises_clear_importerror(monkeypatch):
    """With `anthropic` unavailable, construction must raise a clear ImportError.

    We simulate the extra being absent by making `import anthropic` fail,
    regardless of whether it happens to be installed in the test env. No network.
    """
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "anthropic" or name.startswith("anthropic."):
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    with pytest.raises(ImportError) as excinfo:
        AnthropicExtractor("claude-3-5-haiku-latest")
    msg = str(excinfo.value)
    assert "eval-overexplanation[llm]" in msg


@pytest.mark.skipif(not _HAS_ANTHROPIC, reason="anthropic extra not installed")
def test_anthropic_extractor_default_ontology_is_independent():
    # Constructing with the extra present must not touch the network (the client
    # is created lazily-connectionless; no request is issued in __init__).
    ext = AnthropicExtractor("claude-3-5-haiku-latest", api_key="sk-test-not-real")
    assert ext.ontology is INDEPENDENT_ONTOLOGY


# --------------------------------------------------------------------------- #
# AnthropicExtractor parsing (pure, no network — drive the parse helpers
# directly via a bare instance so we never construct the client or call out).
# --------------------------------------------------------------------------- #


def _bare_anthropic() -> AnthropicExtractor:
    """An AnthropicExtractor whose __init__ is bypassed (no anthropic, no net)."""
    return AnthropicExtractor.__new__(AnthropicExtractor)


def test_parse_propositions_valid_json():
    ext = _bare_anthropic()
    raw = (
        '{"propositions": [{"id": "p1", "text": "x must hold", '
        '"kind": "directive", "tier": "must", "mention_sentences": [0, 3]}]}'
    )
    out = ext._parse_propositions("D1", raw)
    assert out.document_id == "D1"
    assert out.propositions[0].id == "p1"
    assert out.propositions[0].tier is Tier.MUST
    assert out.propositions[0].mention_sentences == (0, 3)


def test_parse_propositions_defaults_tier_to_should():
    ext = _bare_anthropic()
    raw = (
        '{"propositions": [{"id": "p1", "text": "t", "kind": "assertion", '
        '"mention_sentences": [1]}]}'
    )
    out = ext._parse_propositions("D1", raw)
    assert out.propositions[0].tier is Tier.SHOULD


def test_parse_propositions_non_json_raises_valueerror():
    ext = _bare_anthropic()
    with pytest.raises(ValueError):
        ext._parse_propositions("D1", "not json at all {")


def test_parse_propositions_missing_key_raises_valueerror():
    ext = _bare_anthropic()
    with pytest.raises(ValueError):
        ext._parse_propositions("D1", '{"items": []}')


def test_parse_propositions_malformed_entry_raises_valueerror():
    ext = _bare_anthropic()
    # missing mention_sentences -> Proposition would reject; surfaced as ValueError
    raw = '{"propositions": [{"id": "p1", "text": "t", "kind": "assertion"}]}'
    with pytest.raises(ValueError):
        ext._parse_propositions("D1", raw)


def test_parse_propositions_unknown_tier_raises_valueerror():
    ext = _bare_anthropic()
    raw = (
        '{"propositions": [{"id": "p1", "text": "t", "kind": "assertion", '
        '"tier": "critical", "mention_sentences": [0]}]}'
    )
    with pytest.raises(ValueError):
        ext._parse_propositions("D1", raw)


def test_parse_alignment_valid_json():
    ext = _bare_anthropic()
    src, tgt = _source_set(), _target_set()
    raw = (
        '{"links": ['
        '{"source_id": "s1", "target_id": "t1", "relation": "preserved"}, '
        '{"source_id": "s2", "target_id": null, "relation": "dropped"}]}'
    )
    out = ext._parse_alignment(src, tgt, raw)
    assert isinstance(out, Alignment)
    assert {l.source_id for l in out.links} == {"s1", "s2"}
    assert out.links_for(Relation.DROPPED)[0].source_id == "s2"


def test_parse_alignment_missing_key_raises_valueerror():
    ext = _bare_anthropic()
    with pytest.raises(ValueError):
        ext._parse_alignment(_source_set(), _target_set(), '{"rows": []}')


def test_parse_alignment_unknown_relation_raises_valueerror():
    ext = _bare_anthropic()
    raw = '{"links": [{"source_id": "s1", "target_id": "t1", "relation": "warped"}]}'
    with pytest.raises(ValueError):
        ext._parse_alignment(_source_set(), _target_set(), raw)


# --------------------------------------------------------------------------- #
# OpenAIExtractor: import-safety and the missing-extra ImportError
# --------------------------------------------------------------------------- #

_HAS_OPENAI = importlib.util.find_spec("openai") is not None


def test_openai_extractor_without_extra_raises_clear_importerror(monkeypatch):
    """With `openai` unavailable, construction must raise a clear ImportError.

    We simulate the extra being absent by making `import openai` fail, regardless
    of whether it happens to be installed in the test env. No network.
    """
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise ImportError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    with pytest.raises(ImportError) as excinfo:
        OpenAIExtractor("gpt-4o-mini")
    msg = str(excinfo.value)
    assert "eval-overexplanation[llm]" in msg


@pytest.mark.skipif(not _HAS_OPENAI, reason="openai extra not installed")
def test_openai_extractor_default_ontology_is_independent():
    # Constructing with the extra present must not touch the network (the OpenAI
    # client is connectionless until a request is issued). base_url is accepted
    # so any OpenAI-compatible endpoint can be targeted.
    ext = OpenAIExtractor(
        "gpt-4o-mini", api_key="sk-test-not-real", base_url="http://localhost:8000/v1"
    )
    assert ext.ontology is INDEPENDENT_ONTOLOGY
    assert ext.model == "gpt-4o-mini"


# --------------------------------------------------------------------------- #
# _BaseLLMExtractor: shared extract/align driven through a canned _complete.
# A subclass whose _complete returns a fixed JSON string exercises the WHOLE
# shared path (prompt assembly -> parse) with no network and no SDK installed.
# --------------------------------------------------------------------------- #


class _CannedExtractor(_BaseLLMExtractor):
    """Drives the shared base with a scripted _complete. No __init__/SDK/network."""

    def __init__(self, extract_json: str, align_json: str) -> None:
        self._extract_json = extract_json
        self._align_json = align_json
        self.calls: list[tuple[str, str]] = []

    def _complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        # Route by which instruction block the base handed us.
        return self._align_json if "align" in system.lower() else self._extract_json


def test_base_complete_not_implemented_by_default():
    base = _BaseLLMExtractor()
    with pytest.raises(NotImplementedError):
        base._complete("sys", "usr")


def test_base_extract_parses_canned_completion():
    raw = (
        '{"propositions": [{"id": "p1", "text": "x must hold", '
        '"kind": "directive", "tier": "must", "mention_sentences": [0, 3]}]}'
    )
    ext = _CannedExtractor(extract_json=raw, align_json="{}")
    out = ext.extract("D1", "some document body")
    assert out.document_id == "D1"
    assert out.propositions[0].id == "p1"
    assert out.propositions[0].tier is Tier.MUST
    assert out.propositions[0].mention_sentences == (0, 3)
    # The base assembled a user message embedding the document text.
    assert "some document body" in ext.calls[0][1]


def test_base_align_parses_canned_completion():
    src, tgt = _source_set(), _target_set()
    raw = (
        '{"links": ['
        '{"source_id": "s1", "target_id": "t1", "relation": "preserved"}, '
        '{"source_id": "s2", "target_id": null, "relation": "dropped"}]}'
    )
    ext = _CannedExtractor(extract_json="{}", align_json=raw)
    out = ext.align(src, tgt)
    assert isinstance(out, Alignment)
    assert {l.source_id for l in out.links} == {"s1", "s2"}
    assert out.links_for(Relation.DROPPED)[0].source_id == "s2"
    # The base assembled a user message embedding both proposition lists.
    user_msg = ext.calls[0][1]
    assert "s1: cache must be flushed" in user_msg
    assert "t1: flush the cache" in user_msg


def test_base_extract_surfaces_malformed_completion_as_valueerror():
    ext = _CannedExtractor(extract_json="not json {", align_json="{}")
    with pytest.raises(ValueError):
        ext.extract("D1", "body")


def test_concrete_extractors_share_the_base():
    # Both LLM families inherit the shared parsing/Protocol surface.
    assert issubclass(AnthropicExtractor, _BaseLLMExtractor)
    assert issubclass(OpenAIExtractor, _BaseLLMExtractor)


# --------------------------------------------------------------------------- #
# Prompt-caching wiring (pure request builders — no network, no SDK). These
# prove the cache_control breakpoint sits on the STABLE system prefix and the
# volatile per-call text stays after it, for both families.
# --------------------------------------------------------------------------- #


def test_anthropic_request_caches_the_system_prefix():
    req = _anthropic_request("claude-sonnet-4-6", "INSTRUCTIONS", "DOCUMENT BODY")
    assert req["model"] == "claude-sonnet-4-6"
    # system is a content-block list whose single block carries an ephemeral
    # cache_control breakpoint (the stable, reusable prefix).
    assert req["system"] == [
        {"type": "text", "text": "INSTRUCTIONS", "cache_control": {"type": "ephemeral"}}
    ]


def test_anthropic_request_leaves_volatile_user_text_uncached():
    req = _anthropic_request("claude-sonnet-4-6", "INSTRUCTIONS", "DOCUMENT BODY")
    (user_msg,) = req["messages"]
    assert user_msg["role"] == "user"
    # The per-document body is a plain string AFTER the breakpoint — no
    # cache_control, since it differs on every call.
    assert user_msg["content"] == "DOCUMENT BODY"


def test_openai_request_orders_stable_prefix_first():
    req = _openai_request("gpt-5.4", "INSTRUCTIONS", "DOCUMENT BODY")
    assert req["model"] == "gpt-5.4"
    # OpenAI caches automatically (no parameter); the only requirement is that
    # the stable system message precedes the volatile user content.
    roles = [m["role"] for m in req["messages"]]
    assert roles == ["system", "user"]
    assert req["messages"][0]["content"] == "INSTRUCTIONS"
    assert req["messages"][1]["content"] == "DOCUMENT BODY"
    # JSON output is still constrained for parseable propositions.
    assert req["response_format"] == {"type": "json_object"}
