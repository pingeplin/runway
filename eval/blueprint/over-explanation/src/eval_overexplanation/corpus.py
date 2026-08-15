"""Load human-authored corpus assets into the inert model value objects.

A *brief* lives in one directory under the corpus root and is described by a
small set of JSON files plus a Markdown body:

* ``brief.json``             — id / title / regime / buildable metadata.
* ``brief.md``               — the prose body fed to every arm (-> ``Brief.text``).
* ``gold_propositions.json`` — the *blind* gold proposition set: the load-bearing
                               claims a faithful build must carry, authored from
                               the brief alone (-> :class:`PropositionSet`).
* ``cases.json``             — the hidden executed-oracle cases, present only for
                               buildable briefs (-> :class:`OracleCase` tuple).

The exact JSON shapes are documented in ``corpus/schema.md`` and the authoring
protocol in ``corpus/README.md``; a complete worked example lives in
``corpus/example-brief/``. These loaders are pure I/O + validation: every domain
invariant (unique proposition ids, >=1 mention, etc.) is enforced by the model
constructors in :mod:`eval_overexplanation.models`, so a malformed asset surfaces
as a ``ValueError`` here rather than corrupting a downstream metric.

Tolerance policy (issue #10 contract):

* A missing ``cases.json`` is *tolerated* — a non-buildable brief simply has no
  oracle, so :func:`load_oracle_cases` returns ``()``.
* A missing ``cases_holdout.json`` / ``mutations.json`` (the BLUEPRINT-BENCH
  blind O2/O3 assets) is *tolerated* as ``None`` — the dimension cell is then
  SKIPPED, never passed; the skip is counted upstream, fail-closed.
* A *malformed* asset of any of the above (bad JSON, wrong shape) is *strict* —
  it raises, because a present-but-broken asset is an authoring error, not an
  absence.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import (
    Brief,
    Mutation,
    OracleCase,
    Proposition,
    PropositionSet,
    Regime,
    Tier,
)

BRIEF_JSON = "brief.json"
BRIEF_MD = "brief.md"
GOLD_JSON = "gold_propositions.json"
CASES_JSON = "cases.json"
HOLDOUT_JSON = "cases_holdout.json"
MUTATIONS_JSON = "mutations.json"


def _read_json(path: Path) -> object:
    """Read and parse a JSON file, re-raising parse errors as ``ValueError``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - environment dependent
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc


def _require_mapping(obj: object, path: Path) -> dict:
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected a JSON object, got {type(obj).__name__}")
    return obj


def _parse_regime(value: object, path: Path) -> Regime:
    """Map a ``regime`` string onto the :class:`Regime` enum (unknown => error)."""
    if not isinstance(value, str):
        raise ValueError(f"{path}: 'regime' must be a string, got {type(value).__name__}")
    try:
        return Regime(value)
    except ValueError as exc:
        allowed = ", ".join(r.value for r in Regime)
        raise ValueError(
            f"{path}: unknown regime {value!r}; expected one of: {allowed}"
        ) from exc


def _parse_tier(value: object, path: Path) -> Tier:
    """Map a ``tier`` string onto the :class:`Tier` enum (default SHOULD)."""
    if value is None:
        return Tier.SHOULD
    if not isinstance(value, str):
        raise ValueError(f"{path}: 'tier' must be a string, got {type(value).__name__}")
    try:
        return Tier(value)
    except ValueError as exc:
        allowed = ", ".join(t.value for t in Tier)
        raise ValueError(
            f"{path}: unknown tier {value!r}; expected one of: {allowed}"
        ) from exc


def load_brief(brief_dir: Path) -> Brief:
    """Load ``brief.json`` + ``brief.md`` from ``brief_dir`` into a :class:`Brief`.

    ``brief.json`` carries ``{id, title, regime, buildable}``; the body text is
    read from the sibling ``brief.md`` and becomes ``Brief.text``. An unknown
    ``regime`` value raises ``ValueError``.
    """
    brief_dir = Path(brief_dir)
    meta_path = brief_dir / BRIEF_JSON
    meta = _require_mapping(_read_json(meta_path), meta_path)

    for key in ("id", "title", "regime", "buildable"):
        if key not in meta:
            raise ValueError(f"{meta_path}: missing required key {key!r}")

    if not isinstance(meta["buildable"], bool):
        raise ValueError(f"{meta_path}: 'buildable' must be a boolean")

    md_path = brief_dir / BRIEF_MD
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        # brief.md is the body; absence yields an empty body rather than a hard
        # error so a metadata-only brief can still load.
        text = ""

    return Brief(
        id=str(meta["id"]),
        title=str(meta["title"]),
        regime=_parse_regime(meta["regime"], meta_path),
        buildable=bool(meta["buildable"]),
        text=text,
    )


def load_gold(brief_dir: Path) -> PropositionSet:
    """Load ``gold_propositions.json`` into the blind gold :class:`PropositionSet`.

    Shape::

        {
          "document_id": "<id>",
          "propositions": [
            {"id", "text", "kind", "tier", "mention_sentences": [int, ...]},
            ...
          ]
        }

    ``tier`` defaults to SHOULD when omitted; ``mention_sentences`` must hold at
    least one sentence index (enforced by :class:`Proposition`). Duplicate ids
    are rejected by :class:`PropositionSet`.
    """
    brief_dir = Path(brief_dir)
    gold_path = brief_dir / GOLD_JSON
    data = _require_mapping(_read_json(gold_path), gold_path)

    if "document_id" not in data:
        raise ValueError(f"{gold_path}: missing required key 'document_id'")
    raw_props = data.get("propositions")
    if not isinstance(raw_props, list):
        raise ValueError(f"{gold_path}: 'propositions' must be a list")

    propositions = tuple(_parse_proposition(p, gold_path) for p in raw_props)
    return PropositionSet(
        document_id=str(data["document_id"]),
        propositions=propositions,
    )


def _parse_proposition(obj: object, path: Path) -> Proposition:
    prop = _require_mapping(obj, path)
    for key in ("id", "text", "kind"):
        if key not in prop:
            raise ValueError(f"{path}: proposition missing required key {key!r}")

    raw_mentions = prop.get("mention_sentences", ())
    if not isinstance(raw_mentions, (list, tuple)):
        raise ValueError(
            f"{path}: proposition {prop['id']!r} 'mention_sentences' must be a list"
        )
    try:
        mentions = tuple(int(i) for i in raw_mentions)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{path}: proposition {prop['id']!r} 'mention_sentences' must be ints"
        ) from exc

    return Proposition(
        id=str(prop["id"]),
        text=str(prop["text"]),
        kind=str(prop["kind"]),
        tier=_parse_tier(prop.get("tier"), path),
        mention_sentences=mentions,
    )


def load_oracle_cases(brief_dir: Path) -> tuple[OracleCase, ...]:
    """Load ``cases.json`` into a tuple of :class:`OracleCase`.

    Returns ``()`` when ``cases.json`` is absent (a non-buildable brief has no
    oracle). A present-but-malformed ``cases.json`` raises ``ValueError`` — a
    broken oracle is an authoring error, not an absence.

    Shape::

        {"cases": [{"label": str, "args": [...], "expected": <any>}, ...]}

    ``args`` is a JSON array materialised into a tuple; ``expected`` is any JSON
    value compared by ``==`` against ``entrypoint(*args)``.
    """
    brief_dir = Path(brief_dir)
    cases_path = brief_dir / CASES_JSON
    if not cases_path.exists():
        return ()
    return _parse_cases_file(cases_path)


def _parse_cases_file(cases_path: Path) -> tuple[OracleCase, ...]:
    """Parse a present ``cases*.json`` file (shared by visible + holdout)."""
    data = _require_mapping(_read_json(cases_path), cases_path)
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError(f"{cases_path}: 'cases' must be a list")

    cases: list[OracleCase] = []
    for entry in raw_cases:
        case = _require_mapping(entry, cases_path)
        for key in ("label", "args", "expected"):
            if key not in case:
                raise ValueError(f"{cases_path}: case missing required key {key!r}")
        if not isinstance(case["args"], list):
            raise ValueError(
                f"{cases_path}: case {case['label']!r} 'args' must be a list"
            )
        cases.append(
            OracleCase(
                label=str(case["label"]),
                args=tuple(case["args"]),
                expected=case["expected"],
            )
        )
    return tuple(cases)


def load_holdout_cases(brief_dir: Path) -> tuple[OracleCase, ...] | None:
    """Load ``cases_holdout.json`` (O2's blind holdout), tolerant of absence.

    Returns ``None`` when the file is absent — the O2 cell is then *skipped*,
    never passed (BENCHMARK.md §1 O2: no holdout means no signal; the skip is
    counted into ``o2_skipped_fraction`` upstream, and over 30% skips force
    dimension O underpowered). Same shape and same strictness as
    :func:`load_oracle_cases` when the file is present: a malformed holdout is
    an authoring error and raises ``ValueError``.
    """
    brief_dir = Path(brief_dir)
    holdout_path = brief_dir / HOLDOUT_JSON
    if not holdout_path.exists():
        return None
    return _parse_cases_file(holdout_path)


def load_mutations(brief_dir: Path) -> tuple[Mutation, ...] | None:
    """Load ``mutations.json`` (O3's blind battery), tolerant of absence.

    Returns ``None`` when the file is absent — the O3 cell is then *skipped*,
    never passed (the skip is counted into ``o3_skipped_fraction`` upstream).
    Present-but-malformed raises ``ValueError``.

    Shape::

        {"mutations": [{"label": str, "filename": str,
                        "find": str, "replace": str}, ...]}

    ``filename`` is relative to the O3 merged reference dir the CLI assembles
    (the frozen reference staged as ``<brief.module>.py`` + the arm's tests),
    so mutations target the module file the arm's tests import.
    """
    brief_dir = Path(brief_dir)
    mutations_path = brief_dir / MUTATIONS_JSON
    if not mutations_path.exists():
        return None

    data = _require_mapping(_read_json(mutations_path), mutations_path)
    raw = data.get("mutations")
    if not isinstance(raw, list):
        raise ValueError(f"{mutations_path}: 'mutations' must be a list")

    mutations: list[Mutation] = []
    for entry in raw:
        mut = _require_mapping(entry, mutations_path)
        for key in ("label", "filename", "find", "replace"):
            if key not in mut:
                raise ValueError(
                    f"{mutations_path}: mutation missing required key {key!r}")
        mutations.append(
            Mutation(
                label=str(mut["label"]),
                filename=str(mut["filename"]),
                find=str(mut["find"]),
                replace=str(mut["replace"]),
            )
        )
    return tuple(mutations)


def load_corpus(root: Path) -> tuple[Brief, ...]:
    """Load every brief under ``root`` (each immediate subdir with a ``brief.json``).

    Subdirectories without a ``brief.json`` are skipped (scaffold dirs, docs).
    Briefs are returned sorted by id for a deterministic order.
    """
    root = Path(root)
    briefs: list[Brief] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if not (child / BRIEF_JSON).exists():
            continue
        briefs.append(load_brief(child))
    return tuple(sorted(briefs, key=lambda b: b.id))
