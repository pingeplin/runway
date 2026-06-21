"""Proposition extractors — the cross-family seam (issue #10, fix #1).

This module provides implementations of the ``PropositionExtractor`` Protocol
(see ``interfaces.py``):

* ``FixtureExtractor`` — deterministic, dict-backed. Returns canned proposition
  sets and alignments. Used for tests and offline runs; no LLM, no network.
* ``_BaseLLMExtractor`` — the shared JSON parsing + ``extract``/``align``
  Protocol surface for every LLM-backed extractor. Subclasses implement exactly
  one method, ``_complete(system, user) -> str`` (the single network seam), so
  that is the only thing a test would ever need to mock.
* ``AnthropicExtractor`` / ``OpenAIExtractor`` — the two cross-family extractors
  (fix #1 wants >= 2 families). Each lazy-imports its SDK inside its constructor
  so this module is import-safe even when the ``llm`` extra is absent.

The ``INDEPENDENT_ONTOLOGY`` constant below is the proposition-kind taxonomy the
LLM extractor is instructed to use. It is authored *independently* of change ②'s
six keep-categories (fact / decision / constraint / interface-detail /
rejected-alternative / testable-behavior). Reusing those verbatim would make
proposition density rise by construction and invalidate the metric. The scheme
here is worded independently — see the comment on the constant.
"""

from __future__ import annotations

import json
from typing import Any

from .models import (
    Alignment,
    Proposition,
    PropositionLink,
    PropositionSet,
    Relation,
    Tier,
)

# --------------------------------------------------------------------------- #
# Independent ontology (NOT change ②'s six keep-categories)
# --------------------------------------------------------------------------- #
#
# Change ② keeps: fact / decision / constraint / interface-detail /
# rejected-alternative / testable-behavior. We deliberately do NOT reuse those
# labels — an extractor that inherited the treatment's own categories would make
# the density metric move by construction (issue #10, fix #1). The kinds below
# are an independently-worded scheme describing *what role a claim plays in
# prose*, with no one-to-one mapping back onto the treatment's keep-list. They
# are descriptive metadata only; no decision rule keys off specific kind strings
# (see ``Proposition.kind`` in models.py).
INDEPENDENT_ONTOLOGY: tuple[str, ...] = (
    "assertion",        # a stated truth-claim about the world or the system
    "directive",        # an instruction / requirement the reader must satisfy
    "boundary",         # a limit, precondition, or scope restriction
    "specification",    # a concrete shape: signature, field, value, format
    "discarded-option",  # an approach considered and explicitly set aside
    "expected-outcome",  # an observable result used to judge correctness
)


def _tier_from(value: Any) -> Tier:
    """Coerce a JSON tier value to the ``Tier`` enum, defaulting to SHOULD."""
    if value is None:
        return Tier.SHOULD
    try:
        return Tier(str(value).lower())
    except ValueError as exc:  # unknown tier string
        raise ValueError(f"unknown proposition tier: {value!r}") from exc


def _relation_from(value: Any) -> Relation:
    """Coerce a JSON relation value to the ``Relation`` enum."""
    try:
        return Relation(str(value).lower())
    except ValueError as exc:
        raise ValueError(f"unknown alignment relation: {value!r}") from exc


# --------------------------------------------------------------------------- #
# FixtureExtractor — deterministic, no LLM
# --------------------------------------------------------------------------- #


class FixtureExtractor:
    """Deterministic extractor for tests/offline runs. No LLM, no network.

    Backed by two dicts handed in at construction:

    * ``sets`` maps ``document_id -> PropositionSet``; ``extract`` returns the
      canned set (and raises ``KeyError`` for an unknown id).
    * ``alignments`` maps ``(source_id, target_id) -> Alignment``; ``align``
      looks up the pair (and raises ``KeyError`` for an unknown pair).

    It satisfies the ``PropositionExtractor`` Protocol structurally.
    """

    def __init__(
        self,
        sets: dict[str, PropositionSet],
        alignments: dict[tuple[str, str], Alignment] | None = None,
    ) -> None:
        self._sets = dict(sets)
        self._alignments = dict(alignments) if alignments is not None else {}

    def extract(self, document_id: str, text: str) -> PropositionSet:
        """Return the canned set for ``document_id`` (``KeyError`` if absent).

        ``text`` is accepted to satisfy the Protocol but is ignored — the result
        is fixed by ``document_id`` so callers get fully deterministic output.
        """
        return self._sets[document_id]

    def align(self, source: PropositionSet, target: PropositionSet) -> Alignment:
        """Return the canned alignment for the document-id pair.

        Raises ``KeyError`` if no alignment was supplied for
        ``(source.document_id, target.document_id)``.
        """
        return self._alignments[(source.document_id, target.document_id)]


# --------------------------------------------------------------------------- #
# LLM-backed extractors — shared base + the two concrete families
# --------------------------------------------------------------------------- #


def _extract_instructions(ontology: str | tuple[str, ...]) -> str:
    """Build the extraction prompt for a given kind ontology.

    The kind list is injected from the *instance's* ontology so the
    ``ontology=`` constructor argument actually changes what the model is told
    (fix #1: the extractor must use an ontology independent of change ②'s
    keep-categories, and that choice must be honoured, not implied).
    """
    kinds = ontology if isinstance(ontology, str) else ", ".join(ontology)
    return (
        "You extract the distinct load-bearing propositions from a document. "
        "A proposition is one atomic claim. Count every place it is asserted as a "
        "mention. Return ONLY JSON: a list under key \"propositions\", each item "
        '{"id": str, "text": str, "kind": str, "tier": "must"|"should"|"detail", '
        '"mention_sentences": [int, ...]}. The "kind" MUST be one of: '
        + kinds
        + ". Use 1-based or 0-based sentence indices consistently; every "
        "proposition has at least one mention."
    )


# Default instruction string (the independent ontology), kept for reference and
# for bare instances that carry no ``ontology`` attribute.
_EXTRACT_INSTRUCTIONS = _extract_instructions(INDEPENDENT_ONTOLOGY)

_ALIGN_INSTRUCTIONS = (
    "You align each SOURCE proposition to its fate in the TARGET document. "
    "Return ONLY JSON: a list under key \"links\", each item "
    '{"source_id": str, "target_id": str|null, "relation": '
    '"preserved"|"merged_into"|"restated_elsewhere"|"dropped"}. '
    "Every source proposition appears exactly once. A surviving relation names "
    "a target_id; \"dropped\" names target_id null."
)


# --------------------------------------------------------------------------- #
# Provider request builders (pure — no network, no SDK). Separated from the
# ``_complete`` I/O seam so the prompt-caching wiring is unit-testable offline.
# --------------------------------------------------------------------------- #
#
# Prompt caching is a *prefix match*: a hit is only possible when stable content
# comes first and volatile content last. Here the ``system`` block (the extraction
# / align instructions + ontology) is identical across every document and every
# alignment, so it is the cacheable prefix; the per-call ``user`` text (the
# document body, or the SOURCE+TARGET proposition lists) is what varies and must
# come after it. Both families are wired for this; only the mechanism differs.
#
# Caveat (honest): a prefix only caches once it clears the model's minimum —
# ~2048 tokens on Sonnet 4.6, ~1024 on OpenAI. Today's instruction block is far
# shorter than that, so on the current per-document call shape caching is a
# placement-correct no-op (no error, no extra cost); the win materialises if the
# instructions grow (few-shot examples, a longer rubric) or the shared prefix
# otherwise gets large. The design is cache-ready, not cache-dependent.

_CACHE_CONTROL = {"type": "ephemeral"}


def _anthropic_request(model: str, system: str, user: str) -> dict:
    """Build ``messages.create`` kwargs with a cache_control breakpoint.

    The ``system`` instructions are the stable prefix and carry the breakpoint;
    the volatile ``user`` content follows, uncached, so each document/alignment
    reuses the cached instruction prefix instead of re-billing it.
    """
    return {
        "model": model,
        "max_tokens": 4096,
        "system": [
            {"type": "text", "text": system, "cache_control": dict(_CACHE_CONTROL)},
        ],
        "messages": [{"role": "user", "content": user}],
    }


def _openai_request(model: str, system: str, user: str) -> dict:
    """Build ``chat.completions.create`` kwargs.

    OpenAI prompt caching is automatic — there is no parameter to set; the cache
    keys off the stable prefix on its own. The only design requirement is
    ordering, so the stable ``system`` message comes first and the volatile
    ``user`` content last. ``response_format`` keeps the output parseable JSON.
    """
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }


class _BaseLLMExtractor:
    """Shared JSON parsing + ``extract``/``align`` for every LLM extractor.

    Holds everything that is *not* provider-specific: the ``_loads`` /
    ``_parse_propositions`` / ``_parse_alignment`` helpers (pure, no network) and
    the ``extract`` / ``align`` Protocol surface. A concrete subclass supplies a
    single ``_complete(system, user) -> str`` method that issues one chat
    completion against its provider; that method is the only network seam, so it
    is the only thing a test would ever need to mock or fake.

    This base intentionally has no ``__init__`` — each concrete family owns its
    own constructor (and its own lazy SDK import), so a subclass can also be
    instantiated bare via ``__new__`` to drive the pure parsers offline.
    """

    # -- the single network seam (subclass responsibility) ----------------- #

    def _complete(self, system: str, user: str) -> str:
        """Issue one chat completion and return the raw text. Only mock-point."""
        raise NotImplementedError

    # -- parsing (pure; no network) ---------------------------------------- #

    @staticmethod
    def _loads(raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"extractor returned non-JSON output: {exc}") from exc

    def _parse_propositions(self, document_id: str, raw: str) -> PropositionSet:
        data = self._loads(raw)
        if not isinstance(data, dict) or "propositions" not in data:
            raise ValueError("extractor output missing 'propositions' key")
        items = data["propositions"]
        if not isinstance(items, list):
            raise ValueError("'propositions' must be a list")
        props: list[Proposition] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"proposition entry must be an object: {item!r}")
            try:
                mentions = tuple(int(s) for s in item["mention_sentences"])
                prop = Proposition(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    kind=str(item["kind"]),
                    tier=_tier_from(item.get("tier")),
                    mention_sentences=mentions,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"malformed proposition {item!r}: {exc}") from exc
            props.append(prop)
        return PropositionSet(document_id=document_id, propositions=tuple(props))

    def _parse_alignment(
        self, source: PropositionSet, target: PropositionSet, raw: str
    ) -> Alignment:
        data = self._loads(raw)
        if not isinstance(data, dict) or "links" not in data:
            raise ValueError("extractor output missing 'links' key")
        rows = data["links"]
        if not isinstance(rows, list):
            raise ValueError("'links' must be a list")
        links: list[PropositionLink] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"link entry must be an object: {row!r}")
            try:
                target_id = row.get("target_id")
                link = PropositionLink(
                    source_id=str(row["source_id"]),
                    target_id=None if target_id is None else str(target_id),
                    relation=_relation_from(row["relation"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"malformed link {row!r}: {exc}") from exc
            links.append(link)
        return Alignment(source=source, target=target, links=tuple(links))

    # -- Protocol surface --------------------------------------------------- #

    def extract(self, document_id: str, text: str) -> PropositionSet:
        ontology = getattr(self, "ontology", INDEPENDENT_ONTOLOGY)
        raw = self._complete(_extract_instructions(ontology), f"DOCUMENT:\n{text}")
        return self._parse_propositions(document_id, raw)

    def align(self, source: PropositionSet, target: PropositionSet) -> Alignment:
        src_txt = "\n".join(f"{p.id}: {p.text}" for p in source.propositions)
        tgt_txt = "\n".join(f"{p.id}: {p.text}" for p in target.propositions)
        raw = self._complete(
            _ALIGN_INSTRUCTIONS,
            f"SOURCE PROPOSITIONS:\n{src_txt}\n\nTARGET PROPOSITIONS:\n{tgt_txt}",
        )
        return self._parse_alignment(source, target, raw)


# --------------------------------------------------------------------------- #
# AnthropicExtractor — reference cross-family extractor (lazy anthropic import)
# --------------------------------------------------------------------------- #


class AnthropicExtractor(_BaseLLMExtractor):
    """Reference cross-family extractor. Lazy-imports ``anthropic``.

    The module imports fine without the ``llm`` extra; the import only happens
    when an ``AnthropicExtractor`` is *constructed*. Missing extra surfaces as an
    ``ImportError`` with an actionable install hint.

    Validity note (issue #10, fix #1): run this on a *different model family*
    than the generator/evaluator under test, and feed it ``INDEPENDENT_ONTOLOGY``
    (the default) so it never inherits change ②'s keep-categories.
    """

    def __init__(
        self,
        model: str,
        *,
        ontology: str | tuple[str, ...] = INDEPENDENT_ONTOLOGY,
        api_key: str | None = None,
    ) -> None:
        try:
            import anthropic  # noqa: F401  (lazy: keeps module import-safe)
        except ImportError as exc:  # pragma: no cover - exercised via test w/o extra
            raise ImportError(
                "AnthropicExtractor requires the optional 'anthropic' "
                "dependency. Install it with: "
                "pip install 'eval-overexplanation[llm]'"
            ) from exc

        self.model = model
        self.ontology = ontology
        self._client = anthropic.Anthropic(api_key=api_key)

    # -- the single network seam ------------------------------------------- #

    def _complete(self, system: str, user: str) -> str:
        """Issue one chat completion and return the raw text. Only mock-point."""
        message = self._client.messages.create(
            **_anthropic_request(self.model, system, user)
        )
        # The anthropic SDK returns content as a list of blocks; concatenate text.
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
        return "".join(parts)


# --------------------------------------------------------------------------- #
# OpenAIExtractor — second cross-family extractor (lazy openai import)
# --------------------------------------------------------------------------- #


class OpenAIExtractor(_BaseLLMExtractor):
    """Second cross-family extractor (issue #10, fix #1). Lazy-imports ``openai``.

    Same parsing/Protocol surface as ``AnthropicExtractor`` (both inherit
    ``_BaseLLMExtractor``); only ``_complete`` differs. The module imports fine
    without the ``llm`` extra; ``openai`` is imported only when an
    ``OpenAIExtractor`` is *constructed*, and a missing extra surfaces as an
    ``ImportError`` with the same actionable install hint.

    ``base_url`` lets this target any OpenAI-compatible endpoint (vLLM, a local
    server, a hosted open-weights model), so "the OpenAI family" is configurable
    rather than pinned to OpenAI's own hosted models — useful for getting a
    genuinely *different* model family than the system under test.
    """

    def __init__(
        self,
        model: str,
        *,
        ontology: str | tuple[str, ...] = INDEPENDENT_ONTOLOGY,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        try:
            import openai  # noqa: F401  (lazy: keeps module import-safe)
        except ImportError as exc:  # pragma: no cover - exercised via test w/o extra
            raise ImportError(
                "OpenAIExtractor requires the optional 'openai' "
                "dependency. Install it with: "
                "pip install 'eval-overexplanation[llm]'"
            ) from exc

        self.model = model
        self.ontology = ontology
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    # -- the single network seam ------------------------------------------- #

    def _complete(self, system: str, user: str) -> str:
        """Issue one chat completion and return the raw text. Only mock-point."""
        response = self._client.chat.completions.create(
            **_openai_request(self.model, system, user)
        )
        content = response.choices[0].message.content
        return content if content is not None else ""
