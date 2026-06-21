"""Assemble a ``results.json`` from raw run cells using a cross-family extractor.

This is the bridge between the *generation* half (``scripts/run-arm.sh`` writes
one cell per arm/brief/seed under a results root) and the *analysis* half (the
``overexpl restatement|guardrails|stats`` subcommands read a ``results.json``).
For each cell it reads the produced design-doc / spec text, runs the configured
proposition extractor (fix #1: a different model family than the
generator/evaluator under test), and emits the transport records.

It needs the live extractor, so it is a *script*, not part of the offline unit
suite. Pick the family explicitly:

    uv run python analysis/assemble.py \
        --results-root results --corpus corpus/demo \
        --family openai --out results/results.json   # --model defaults to gpt-5.4

The two pinned families are Anthropic ``claude-sonnet-4-6`` and OpenAI
``gpt-5.4`` (see ``_DEFAULT_MODEL``). Pass ``--model`` to override; with
``--base-url`` the "openai" family can target any OpenAI-compatible endpoint
(vLLM / a local open-weights model) for a genuinely different, cheaper family.

``--family fixture --fixtures f.json`` runs fully offline (for wiring tests):
``f.json`` maps ``document_id -> PropositionSet`` in the gold-set JSON shape.

Cross-family note: to satisfy the >=2-family requirement, assemble TWICE with
two ``--family`` values and compare; the manifest records both families.
Merge-fidelity needs the *pre*-evaluator document too, which ``run-arm.sh`` does
not yet capture separately — assemble emits restatement + substance + sentences;
merge-fidelity is left to a run that captures pre/post evaluator artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval_overexplanation.grammaticality import split_sentences
from eval_overexplanation.interfaces import PropositionExtractor
from eval_overexplanation.models import Alignment, PropositionSet


# The two pinned cross-family extractor models (fix #1 wants >=2 families). Both
# are overridable with --model; the "openai" family can also be pointed at an
# OpenAI-compatible endpoint via --base-url (local/open-weights = a cheaper but
# still genuinely different family).
_DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.4",
}


def _resolve_model(family: str, model: str) -> str:
    """Use an explicit --model, else the per-family default."""
    return model or _DEFAULT_MODEL.get(family, "")


def _build_extractor(args: argparse.Namespace) -> PropositionExtractor:
    if args.family == "fixture":
        from eval_overexplanation.corpus import load_gold  # reuse the gold JSON shape
        from eval_overexplanation.extractor import FixtureExtractor

        if not args.fixtures:
            raise SystemExit("--family fixture requires --fixtures <file>")
        raw = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
        # raw: {document_id: <PropositionSet-shaped dict>}
        from eval_overexplanation.cli import _build_proposition_set  # transport reuse

        sets = {k: _build_proposition_set(v) for k, v in raw.items()}
        return FixtureExtractor(sets)
    if args.family == "anthropic":
        from eval_overexplanation.extractor import AnthropicExtractor

        return AnthropicExtractor(_resolve_model("anthropic", args.model))
    if args.family == "openai":
        from eval_overexplanation.extractor import OpenAIExtractor

        return OpenAIExtractor(_resolve_model("openai", args.model), base_url=args.base_url)
    raise SystemExit(f"unknown family {args.family!r}")


def _read_artifact_text(cell_dir: Path) -> str:
    """Concatenate every captured markdown artifact in a cell, in sorted order."""
    artifacts = cell_dir / "artifacts"
    if not artifacts.is_dir():
        return ""
    parts = [p.read_text(encoding="utf-8", errors="replace")
             for p in sorted(artifacts.rglob("*.md"))]
    return "\n\n".join(parts)


def _propset_to_dict(s: PropositionSet) -> dict:
    return {
        "document_id": s.document_id,
        "propositions": [
            {"id": p.id, "text": p.text, "kind": p.kind, "tier": p.tier.value,
             "mention_sentences": list(p.mention_sentences)}
            for p in s.propositions
        ],
    }


def _alignment_to_dict(a: Alignment) -> dict:
    return {
        "source": _propset_to_dict(a.source),
        "target": _propset_to_dict(a.target),
        "links": [
            {"source_id": l.source_id, "target_id": l.target_id, "relation": l.relation.value}
            for l in a.links
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assemble results.json from run cells.")
    ap.add_argument("--results-root", required=True, type=Path)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--family", required=True, choices=["fixture", "anthropic", "openai"])
    ap.add_argument("--model", default="",
                    help="extractor model id; empty -> per-family default "
                         "(anthropic: claude-sonnet-4-6, openai: gpt-5.4)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--fixtures", default=None)
    ap.add_argument("--baseline-arm", default="A0", help="arm id to align others against")
    ap.add_argument("--noise-floor", type=float, default=0.0)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)

    extractor = _build_extractor(args)
    root = args.results_root

    # First pass: extract every cell's proposition set, keyed for alignment.
    cells: list[dict] = []
    sets_by_cell: dict[tuple[str, str, int], PropositionSet] = {}
    for brief_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        brief_id = brief_dir.name
        for arm_dir in sorted(p for p in brief_dir.iterdir() if p.is_dir()):
            arm_id = arm_dir.name
            for seed_dir in sorted(arm_dir.glob("seed-*")):
                seed = int(seed_dir.name.split("-", 1)[1])
                text = _read_artifact_text(seed_dir)
                if not text.strip():
                    print(f"warn: no artifact text for {brief_id}/{arm_id}/seed-{seed}",
                          file=sys.stderr)
                    continue
                doc_id = f"{brief_id}:{arm_id}:{seed}"
                pset = extractor.extract(doc_id, text)
                sets_by_cell[(brief_id, arm_id, seed)] = pset
                cells.append({"brief_id": brief_id, "arm_id": arm_id, "seed": seed,
                              "word_count": len(text.split()), "text": text})

    # Second pass: build records, aligning each non-baseline arm onto the baseline.
    records = []
    for c in cells:
        key = (c["brief_id"], c["arm_id"], c["seed"])
        pset = sets_by_cell[key]
        rec = {
            "arm_id": c["arm_id"], "brief_id": c["brief_id"], "seed": c["seed"],
            "word_count": c["word_count"],
            "propositions": _propset_to_dict(pset),
            "sentences": list(split_sentences(c["text"])),
        }
        if c["arm_id"] != args.baseline_arm:
            base = sets_by_cell.get((c["brief_id"], args.baseline_arm, c["seed"]))
            if base is not None:
                rec["substance_alignment"] = _alignment_to_dict(extractor.align(base, pset))
        records.append(rec)

    out = {"noise_floor": args.noise_floor, "records": records}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {len(records)} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
