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

Merge-fidelity (change ②'s delete-or-merge step) needs the *pre*-evaluator
document. We recover it from the cell's ``transcript.jsonl`` (captured by
``run-arm.sh``): blueprint's generator *Writes* each artifact and the evaluator
then *Edits* it, so the lone ``Write`` to each artifact file is its
pre-evaluator snapshot and the final ``artifacts/`` file is that Write plus the
evaluator's Edits. ``reconstruct_pre_evaluator`` rebuilds it, we extract + align
it onto the post-evaluator set, and emit a ``merge_alignment`` record — which
``overexpl guardrails`` already turns into a merge-fidelity block.

This is **fail-closed**. An under-captured pre-document would hide a real dropped
claim — a false *pass* in the exact guardrail meant to catch drops — so we emit a
``merge_alignment`` ONLY when the single-Write boundary observably holds
(``status == "ok"``). If any artifact file was Written more than once
(``"ambiguous"``), or no artifact Write is present / there is no transcript
(``"none"``), or the extractor errors on the cell, merge-fidelity is *skipped*
for that cell with a reason — never silently passed. Reliable capture for the
ambiguous cases ultimately wants a generator-side pre-eval snapshot; until then
those cells contribute no merge-fidelity signal rather than a false one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

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
        from eval_overexplanation.cli import (  # transport reuse
            _build_alignment,
            _build_proposition_set,
        )
        from eval_overexplanation.extractor import FixtureExtractor

        if not args.fixtures:
            raise SystemExit("--family fixture requires --fixtures <file>")
        raw = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
        # Two accepted shapes. Legacy: a bare {document_id: <PropositionSet>} map
        # (extract only). Extended: {"sets": {...}, "alignments": {...}} where an
        # alignment key is "<source_doc_id>|<target_doc_id>" — needed offline for
        # substance (A0->A1) and merge-fidelity (pre->post) alignments.
        if isinstance(raw, dict) and ("sets" in raw or "alignments" in raw):
            sets = {k: _build_proposition_set(v) for k, v in raw.get("sets", {}).items()}
            alignments = {}
            for key, adict in raw.get("alignments", {}).items():
                src_id, tgt_id = str(key).split("|", 1)
                alignments[(src_id, tgt_id)] = _build_alignment(adict)
            return FixtureExtractor(sets, alignments)
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


# Artifact-path dirs run-arm.sh captures; an artifact is a markdown file whose
# path contains one of these as consecutive path *components* (blueprint 3.6+ and
# the pre-3.6 fallbacks). Component-matching (not substring) so `tests/specs_x.md`
# does not masquerade as a `specs/` artifact.
_ARTIFACT_SEGMENTS = (
    "blueprint/specs", "blueprint/plans", "blueprint/designs",
    "specs", "plans", "docs/designs", "docs/testing",
)


def _is_artifact_path(file_path: str) -> bool:
    p = file_path.replace("\\", "/")
    if not p.endswith(".md"):
        return False
    dirparts = p.split("/")[:-1]  # drop the filename
    for seg in _ARTIFACT_SEGMENTS:
        sp = seg.split("/")
        for i in range(len(dirparts) - len(sp) + 1):
            if dirparts[i:i + len(sp)] == sp:
                return True
    return False


def _iter_tool_uses(obj: object):
    """Yield ``(tool_name, input_dict)`` for every tool_use block in a transcript
    line object, tolerant of the stream-json envelope shape."""
    if not isinstance(obj, dict):
        return
    msg = obj.get("message")
    content = msg.get("content") if isinstance(msg, dict) else obj.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and isinstance(block.get("name"), str)
            and isinstance(block.get("input"), dict)
        ):
            yield block["name"], block["input"]


class PreEval(NamedTuple):
    """Outcome of recovering the pre-evaluator document from a run transcript.

    ``status`` is one of:

    * ``"ok"`` — a trustworthy single-Write-per-file snapshot; ``text`` holds it.
    * ``"none"`` — no transcript / no artifact ``Write`` (e.g. the model used the
      text-editor ``create`` tool, or there is no transcript at all).
    * ``"ambiguous"`` — at least one artifact file was ``Write``-ten more than
      once, so we cannot trust which write is the pre-evaluator draft.

    Only ``"ok"`` yields a ``merge_alignment``; ``"none"`` and ``"ambiguous"``
    both make the caller *skip* merge-fidelity for the cell (with a warning).
    This is the fail-closed contract: an uncertain boundary never produces a
    pass — it produces no claim.

    ``detail`` names the offending artifact path(s) on ``"ambiguous"`` so a real
    run can see *which* file eroded coverage (e.g. a regenerated conventions doc)
    rather than a bare "skipped"; it is empty otherwise.
    """

    text: str
    status: str
    detail: str = ""


def reconstruct_pre_evaluator(transcript_path: Path) -> PreEval:
    """Recover the pre-evaluator document from a stream-json run transcript.

    blueprint generates each artifact with a single ``Write`` (the generator's
    output) and the evaluator then *Edits* it — so the lone ``Write`` to each
    artifact markdown file is that file's pre-evaluator snapshot, and the final
    ``artifacts/`` file (post-evaluator) is that Write plus the evaluator's Edits.

    We require that single-Write invariant to *hold observably* before trusting
    the snapshot. If any artifact file was Written more than once — an
    incremental-draft generator, or a subagent that overwrites via ``Write`` —
    the boundary is unknowable, so we return ``status="ambiguous"`` and the cell
    is skipped. This is deliberately fail-closed: an under-captured pre-doc would
    hide a real dropped claim (a false *pass* in the exact guardrail meant to
    catch drops), so on any ambiguity we make no claim rather than risk one.

    Edits never affect the count — they are the expected evaluator action and the
    reason post differs from pre.
    """
    path = Path(transcript_path)
    if not path.is_file():
        return PreEval("", "none")
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return PreEval("", "none")

    content_by_path: dict[str, str] = {}
    write_count: dict[str, int] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        for name, inp in _iter_tool_uses(obj):
            if name != "Write":
                continue
            fp, content = inp.get("file_path"), inp.get("content")
            if not (isinstance(fp, str) and isinstance(content, str)):
                continue
            if not _is_artifact_path(fp):
                continue
            write_count[fp] = write_count.get(fp, 0) + 1
            content_by_path.setdefault(fp, content)  # keep the first write's body

    if not content_by_path:
        return PreEval("", "none")
    dups = sorted(p for p, n in write_count.items() if n > 1)
    if dups:
        # Fail-closed: even one twice-written artifact makes the whole cell's
        # boundary untrustworthy. We skip the cell rather than emit a partial
        # alignment that would read as a (false) pass for the omitted file.
        return PreEval("", "ambiguous", ", ".join(dups))
    return PreEval(
        "\n\n".join(content_by_path[k] for k in sorted(content_by_path)), "ok"
    )


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
                              "word_count": len(text.split()), "text": text,
                              "transcript": seed_dir / "transcript.jsonl"})

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
        cell_tag = f"{c['arm_id']}/{c['brief_id']}/seed-{c['seed']}"

        # Within-arm merge-fidelity: recover the pre-evaluator document from the
        # run transcript, align it onto this (post-evaluator) set, and emit the
        # alignment for `overexpl guardrails` to score. Fail-closed: emit ONLY on
        # a trustworthy "ok" snapshot; skip (with a reason) on "none"/"ambiguous"
        # and on any per-cell extractor error — never fabricate a pass.
        pre = reconstruct_pre_evaluator(c["transcript"])
        if pre.status == "ok" and pre.text.strip():
            try:
                pre_set = extractor.extract(
                    f"{c['brief_id']}:{c['arm_id']}:{c['seed']}:pre", pre.text
                )
                merge = extractor.align(pre_set, pset)
            except Exception as exc:  # noqa: BLE001 - one cell must not abort the run
                print(f"warn: merge-fidelity skipped for {cell_tag}: {exc}",
                      file=sys.stderr)
            else:
                rec["merge_alignment"] = _alignment_to_dict(merge)
        else:
            reason = {
                "none": "no pre-evaluator Write in transcript",
                "ambiguous": f"artifact written more than once ({pre.detail}) "
                             f"- boundary untrustworthy",
            }.get(pre.status, pre.status)
            print(f"warn: merge-fidelity skipped for {cell_tag}: {reason}",
                  file=sys.stderr)

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
