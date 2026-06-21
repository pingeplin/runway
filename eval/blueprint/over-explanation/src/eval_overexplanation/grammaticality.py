"""Grammaticality screen — the no-word-drop guardrail (issue #10).

Enforces the user's "keep full sentences" constraint: no article/preposition/
word dropping, no telegraphic register shift. The :class:`A3b_dumb_brevity` arm
is a positive control whose output (``"Returns list."``, ``"If error, retry."``)
a correct checker MUST flag.

Two implementations behind the ``GrammaticalityChecker`` Protocol:

* :class:`DefaultGrammaticalityChecker` — dependency-free, deterministic, coarse.
  A *screen*, not a parser. It biases toward flagging: a word-drop false
  negative (a telegraphic fragment passing as a full sentence) is the dangerous
  failure this guardrail exists to prevent, so the heuristics err toward
  ``ok=False`` when in doubt.
* :class:`SpacyGrammaticalityChecker` — parse-based, higher fidelity, behind the
  optional ``nlp`` extra. ``spacy`` is imported lazily inside ``check``.

Plus :func:`split_sentences`, an approximate deterministic sentence splitter.
"""

from __future__ import annotations

import re

from .models import GrammaticalityReport, SentenceVerdict

# --------------------------------------------------------------------------- #
# Sentence splitting
# --------------------------------------------------------------------------- #

# List markers we strip from the head of a candidate sentence before judging it:
# bullets ("- ", "* ", "• "), and ordered markers ("1. ", "2) ", "a. ").
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]\s+|\(?[0-9a-zA-Z]{1,3}[.)]\s+)")

# Split on terminal punctuation (. ! ?) followed by whitespace/end, and on
# newlines. This is approximate: it does not understand abbreviations
# ("e.g.", "Dr.") or decimal numbers and will over-split them. Documented as
# good-enough to feed the checkers, not a linguistic tokenizer.
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> tuple[str, ...]:
    """Split prose into sentence-ish chunks. Deterministic and approximate.

    Splits on terminal punctuation (``.!?``) followed by whitespace and on
    newlines. Does NOT handle abbreviations or decimals — it is a coarse feed
    for the grammaticality checkers, not a real sentence tokenizer.
    """
    chunks = _SPLIT.split(text)
    return tuple(c.strip() for c in chunks if c.strip())


# --------------------------------------------------------------------------- #
# Default (dependency-free) checker
# --------------------------------------------------------------------------- #

# Small, inline word lists. This is a screen, not a lexicon — deliberately tiny.

# Common verbs / auxiliaries / copulas. If a sentence contains one of these,
# heuristic #1 (no-verb) does not fire.
_VERBS = frozenset(
    {
        # copula / auxiliary / modal
        "is", "are", "am", "was", "were", "be", "been", "being",
        "have", "has", "had",
        "do", "does", "did",
        "will", "would", "shall", "should", "can", "could",
        "may", "might", "must", "ought",
        # very common lexical verbs (base form — -s/-ed/-ing handled separately)
        "return", "raise", "set", "get", "use", "call", "run", "make",
        "take", "give", "send", "read", "write", "add", "remove", "check",
        "throw", "catch", "store", "load", "save", "parse", "build", "create",
        "delete", "update", "fetch", "handle", "accept", "reject", "allow",
        "ensure", "let", "see", "go", "come", "keep", "find", "show", "need",
        "want", "know", "think", "provide", "support", "require", "contain",
        "hold", "put", "cut", "hit", "split", "let",
    }
)

# Irregular past/participle forms that don't end in the regular suffixes above,
# so heuristic #1 still credits them as verbs.
_IRREGULAR_VERB_FORMS = frozenset(
    {
        "ran", "went", "came", "took", "gave", "made", "saw", "found",
        "kept", "held", "told", "sent", "read", "wrote", "written", "thrown",
        "thought", "knew", "known", "built", "bought", "caught", "taught",
        "left", "met", "paid", "said", "sold", "stood", "understood", "won",
        "got", "gotten",
    }
)

# Words ending in -s/-ed/-ing that are NOT verbs — plural nouns, gerund-nouns,
# adjectives — so heuristic #1's suffix rule doesn't credit them as verbs.
# Kept tiny on purpose; over-listing defeats the screen.
_NON_VERB_SUFFIX_WORDS = frozenset(
    {
        # plural / mass nouns commonly seen in technical prose
        "is", "as", "was", "has", "this", "its", "yes", "less", "thus",
        "args", "kwargs", "props", "tests", "results", "values", "keys",
        "items", "errors", "bytes", "logs", "notes", "docs", "ms", "ttl",
        # -ing nouns / adjectives
        "string", "thing", "ring", "during", "morning", "nothing", "something",
        "everything", "anything", "warning", "meaning", "setting", "settings",
        # -ed adjectives
        "red", "bed", "fed",
    }
)

# Bare singular count nouns that, when they immediately follow a verb or
# preposition with no determiner, signal a dropped article ("returns [a] list",
# "raise [an] error", "in [the] cache"). Heuristic #2.
_BARE_COUNT_NOUNS = frozenset(
    {
        "list", "error", "value", "result", "cache", "string", "object",
        "dict", "array", "set", "map", "file", "user", "request", "response",
        "session", "token", "key", "field", "record", "row", "table", "queue",
        "message", "node", "page", "item", "input", "output", "function",
        "method", "class", "module", "buffer", "socket", "thread", "process",
        "exception", "flag", "field", "header", "path", "directory", "folder",
    }
)

# Words that, appearing right before a bare count noun, legitimately replace a
# determiner (so heuristic #2 should NOT fire): determiners, possessives,
# quantifiers, prepositions-of-amount, etc.
_DETERMINER_LIKE = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those", "its", "their",
        "our", "your", "my", "his", "her", "no", "any", "some", "each",
        "every", "another", "one", "two", "per", "each", "all", "both",
        "which", "what", "whose", "such",
    }
)

# Verbs / prepositions whose object, if a bare count noun, indicates a dropped
# article. Heuristic #2 looks for one of these immediately before a bare noun.
_DROP_TRIGGERS = frozenset(
    {
        # transitive verbs (base + common inflections)
        "return", "returns", "returned",
        "raise", "raises", "raised",
        "throw", "throws", "throwing",
        "get", "gets", "fetch", "fetches", "load", "loads",
        "store", "stores", "save", "saves", "create", "creates",
        "delete", "deletes", "use", "uses", "send", "sends",
        "accept", "accepts", "build", "builds", "parse", "parses",
        "read", "reads", "write", "writes", "update", "updates",
        "validate", "validates", "process", "processes", "handle", "handles",
        "check", "checks", "drop", "drops", "expect", "expects",
        # prepositions
        "in", "on", "to", "from", "with", "into", "via", "for", "of", "at",
        "by",
    }
)

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_TERMINAL_PUNCT = (".", "!", "?")


def _tokens(sentence: str) -> list[str]:
    return _WORD.findall(sentence)


def _looks_like_verb(word: str) -> bool:
    w = word.lower()
    if w in _VERBS or w in _IRREGULAR_VERB_FORMS:
        return True
    if w in _NON_VERB_SUFFIX_WORDS:
        return False
    # Regular inflection suffixes. Coarse: this can false-positive on plural
    # nouns ("tests"), which is why _NON_VERB_SUFFIX_WORDS exists as an escape
    # hatch and the no-verb rule is only one of three flagging conditions.
    if w.endswith(("ed", "ing")):
        return True
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        return True
    return False


def _strip_list_marker(sentence: str) -> str:
    return _LIST_MARKER.sub("", sentence, count=1)


class DefaultGrammaticalityChecker:
    """Dependency-free deterministic screen for fragments / dropped words.

    A coarse but deterministic screen, not a full parser. Its contract is: it
    MUST flag telegraphic / article-dropped / verbless fragments (the
    A3b_dumb_brevity failure mode) and MUST pass ordinary full sentences. The
    spaCy-backed checker is the higher-fidelity option behind ``[nlp]``.

    A sentence is a fragment (``ok=False``) if ANY hold:

    1. **No verb.** No token is in the curated verb/auxiliary/copula set and no
       token carries a regular ``-s/-ed/-ing`` inflection (minus a small
       plural-noun exception list). Coarse: may false-positive on
       verb-less-but-grammatical fragments; acceptable, we bias toward flagging.
    2. **Dropped determiner.** A ``verb|preposition + bare-singular-count-noun``
       bigram with no intervening determiner ("returns list", "raise error",
       "in cache").
    3. **Surface form.** Does not start with a capital letter, or does not end
       with terminal punctuation, after trimming list markers.

    This biases toward flagging: a missed telegraphic fragment (false negative)
    is the dangerous failure; an over-flagged odd-but-fine sentence is cheap.
    """

    def check(self, sentences: tuple[str, ...]) -> GrammaticalityReport:
        verdicts: list[SentenceVerdict] = []
        for i, raw in enumerate(sentences):
            ok, reason = self._judge(raw)
            verdicts.append(SentenceVerdict(index=i, text=raw, ok=ok, reason=reason))
        return GrammaticalityReport(verdicts=tuple(verdicts))

    def _judge(self, raw: str) -> tuple[bool, str]:
        stripped = _strip_list_marker(raw).strip()
        if not stripped:
            return False, "empty sentence"

        # Heuristic #3a: must start with a capital letter.
        first = stripped[0]
        if first.isalpha() and not first.isupper():
            return False, "does not start with a capital letter"

        # Heuristic #3b: must end with terminal punctuation.
        if not stripped.endswith(_TERMINAL_PUNCT):
            return False, "does not end with terminal punctuation"

        toks = _tokens(stripped)
        if not toks:
            return False, "contains no words"

        # Heuristic #2: dropped-determiner bigram (verb/prep + bare count noun).
        lowered = [t.lower() for t in toks]
        for prev, cur in zip(lowered, lowered[1:]):
            if (
                prev in _DROP_TRIGGERS
                and cur in _BARE_COUNT_NOUNS
                and prev not in _DETERMINER_LIKE
            ):
                return False, (
                    f"dropped determiner before bare count noun "
                    f"({prev!r} {cur!r})"
                )

        # Heuristic #1: no verb anywhere.
        if not any(_looks_like_verb(t) for t in toks):
            return False, "no verb / copula found (telegraphic fragment)"

        return True, ""


# --------------------------------------------------------------------------- #
# spaCy-backed checker (optional, behind the [nlp] extra)
# --------------------------------------------------------------------------- #


class SpacyGrammaticalityChecker:
    """Parse-based checker. Lazy-imports spacy; raises ImportError without [nlp].

    Flags a sentence when its dependency parse has no finite root verb (no
    token whose ``pos_`` is ``VERB``/``AUX``), the canonical signature of a
    verbless telegraphic fragment. ``spacy`` and the language model are loaded
    lazily on first ``check`` so importing this module never requires the
    ``nlp`` extra.
    """

    def __init__(self, model: str = "en_core_web_sm") -> None:
        self._model_name = model
        self._nlp = None  # loaded lazily

    def _load(self):  # pragma: no cover - exercised only with [nlp] installed
        if self._nlp is not None:
            return self._nlp
        try:
            import spacy
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "SpacyGrammaticalityChecker needs the 'nlp' extra: "
                "pip install 'eval-overexplanation[nlp]'"
            ) from exc
        try:
            self._nlp = spacy.load(self._model_name)
        except OSError as exc:  # pragma: no cover
            raise ImportError(
                f"spaCy model {self._model_name!r} is not installed: "
                f"python -m spacy download {self._model_name}"
            ) from exc
        return self._nlp

    def check(self, sentences: tuple[str, ...]) -> GrammaticalityReport:  # pragma: no cover - needs [nlp]
        nlp = self._load()
        verdicts: list[SentenceVerdict] = []
        for i, raw in enumerate(sentences):
            doc = nlp(raw)
            has_verb = any(tok.pos_ in ("VERB", "AUX") for tok in doc)
            if not has_verb:
                verdicts.append(
                    SentenceVerdict(
                        index=i,
                        text=raw,
                        ok=False,
                        reason="parse has no finite verb (verbless fragment)",
                    )
                )
                continue
            stripped = raw.strip()
            if stripped and stripped[0].isalpha() and not stripped[0].isupper():
                verdicts.append(
                    SentenceVerdict(
                        index=i,
                        text=raw,
                        ok=False,
                        reason="does not start with a capital letter",
                    )
                )
                continue
            verdicts.append(SentenceVerdict(index=i, text=raw, ok=True, reason=""))
        return GrammaticalityReport(verdicts=tuple(verdicts))
