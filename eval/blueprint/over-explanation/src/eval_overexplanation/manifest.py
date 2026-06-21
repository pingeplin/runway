"""Pre-registration manifest (anti p-hacking).

The pre-registration is the audit anchor: it is authored and its
``content_hash`` recorded *before* any A1 (treatment) run, so the analysis
plan cannot be retro-fitted to the data. ``content_hash`` is a sha256 over a
canonical (sorted-key) JSON serialization, so two registrations with identical
content hash to the same value and changing any frozen field changes the hash.

This module is pure data + I/O over the frozen value objects in ``models``. It
has no LLM/NLP dependency and is import-safe with only the stdlib + the package
value objects present.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .models import Arm, Brief, Regime


@dataclass(frozen=True)
class DecisionThresholds:
    """Pre-registered decision knobs for the statistics layer.

    ``noise_floor_multiple`` scales the empirical noise floor; ``tost_margin``
    is the non-inferiority margin for guardrail metrics; ``min_power`` is the
    minimum achieved power below which a TOST result is "underpowered", never
    "safe".
    """

    noise_floor_multiple: float = 2.0
    tost_margin: float = 0.0
    min_power: float = 0.8


@dataclass(frozen=True)
class PreRegistration:
    """The frozen analysis plan for one milestone.

    Carries the arms, briefs (each with its frozen difficulty regime), seeds,
    the extractor model families, and the decision thresholds. ``validate``
    reports structural problems as strings; ``content_hash`` is the tamper
    evidence.
    """

    version: str
    arms: tuple[Arm, ...]
    briefs: tuple[Brief, ...]
    seeds: tuple[int, ...]
    extractor_families: tuple[str, ...]
    thresholds: DecisionThresholds

    def validate(self) -> tuple[str, ...]:
        """Return structural problems; empty tuple means the manifest is ok.

        Checks: >=1 seed; an ``A0``-id and an ``A1``-id arm are present; every
        brief carries a regime; thresholds are present. Also *warns* (as a
        problem string, not an exception) when fewer than two extractor families
        are declared — fix #1 wants >=2 model families for cross-family
        validity.
        """
        problems: list[str] = []

        if len(self.seeds) < 1:
            problems.append("at least one seed is required")

        arm_ids = {a.id for a in self.arms}
        if not any(aid == "A0" or aid.startswith("A0") for aid in arm_ids):
            problems.append("a baseline arm with an A0 id is required")
        if not any(aid == "A1" or aid.startswith("A1") for aid in arm_ids):
            problems.append("a treatment arm with an A1 id is required")

        if len(self.briefs) == 0:
            problems.append("at least one brief is required")
        for brief in self.briefs:
            if not isinstance(brief.regime, Regime):
                problems.append(
                    f"brief {brief.id!r} has no valid regime"
                )

        if self.thresholds is None:  # type: ignore[comparison-overlap]
            problems.append("decision thresholds are required")

        if len(self.extractor_families) < 2:
            problems.append(
                "fewer than two extractor families declared "
                f"(have {len(self.extractor_families)}); fix #1 requires >=2 "
                "model families for cross-family validity"
            )

        return tuple(problems)

    def content_hash(self) -> str:
        """sha256 over canonical (sorted-key) JSON — the audit anchor.

        Identical registrations hash identically; changing any frozen field
        changes the hash. This is how "frozen before any A1 run" is audited.
        """
        canonical = dump_manifest(self)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# (De)serialization
# --------------------------------------------------------------------------- #


def _arm_to_dict(arm: Arm) -> dict:
    return {
        "id": arm.id,
        "label": arm.label,
        "plugin_ref": arm.plugin_ref,
        "evaluator": dict(arm.evaluator),
        "description": arm.description,
    }


def _arm_from_dict(d: dict) -> Arm:
    return Arm(
        id=d["id"],
        label=d["label"],
        plugin_ref=d["plugin_ref"],
        evaluator=dict(d.get("evaluator", {})),
        description=d.get("description", ""),
    )


def _brief_to_dict(brief: Brief) -> dict:
    return {
        "id": brief.id,
        "title": brief.title,
        "regime": brief.regime.value,
        "buildable": brief.buildable,
        "text": brief.text,
    }


def _brief_from_dict(d: dict) -> Brief:
    raw_regime = d["regime"]
    try:
        regime = Regime(raw_regime)
    except ValueError as exc:
        raise ValueError(f"unknown regime {raw_regime!r}") from exc
    return Brief(
        id=d["id"],
        title=d["title"],
        regime=regime,
        buildable=bool(d["buildable"]),
        text=d.get("text", ""),
    )


def _thresholds_to_dict(t: DecisionThresholds) -> dict:
    return {
        "noise_floor_multiple": t.noise_floor_multiple,
        "tost_margin": t.tost_margin,
        "min_power": t.min_power,
    }


def _thresholds_from_dict(d: dict) -> DecisionThresholds:
    return DecisionThresholds(
        noise_floor_multiple=float(d.get("noise_floor_multiple", 2.0)),
        tost_margin=float(d.get("tost_margin", 0.0)),
        min_power=float(d.get("min_power", 0.8)),
    )


def _reg_to_dict(reg: PreRegistration) -> dict:
    return {
        "version": reg.version,
        "arms": [_arm_to_dict(a) for a in reg.arms],
        "briefs": [_brief_to_dict(b) for b in reg.briefs],
        "seeds": list(reg.seeds),
        "extractor_families": list(reg.extractor_families),
        "thresholds": _thresholds_to_dict(reg.thresholds),
    }


def _reg_from_dict(d: dict) -> PreRegistration:
    return PreRegistration(
        version=d["version"],
        arms=tuple(_arm_from_dict(a) for a in d["arms"]),
        briefs=tuple(_brief_from_dict(b) for b in d["briefs"]),
        seeds=tuple(int(s) for s in d["seeds"]),
        extractor_families=tuple(d["extractor_families"]),
        thresholds=_thresholds_from_dict(d["thresholds"]),
    )


def load_manifest(path: Path) -> PreRegistration:
    """Read a pre-registration JSON file into a ``PreRegistration``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _reg_from_dict(raw)


def dump_manifest(reg: PreRegistration) -> str:
    """Serialize to canonical JSON (sorted keys, fixed separators).

    Canonical so that ``content_hash`` is stable across runs and machines and a
    load -> dump round-trip is byte-stable.
    """
    return json.dumps(
        _reg_to_dict(reg),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
