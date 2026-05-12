"""Mutation scorer — apply small AST mutations to the agent's SUT, run the
agent's visible tests against each mutant, score = killed / total.

Operators: arithmetic swaps, comparison swaps, boolean inversion, and 0↔1
swaps — a small subset of the mutmut/PIT catalog, enough to surface
tautological test suites.
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import libcst as cst

from scorers._shared import discover_sources


@dataclass
class Mutant:
    path: str
    line: int
    operator: str
    killed: bool


@dataclass
class MutationScore:
    score: float
    killed: int
    total: int
    timed_out: bool = False
    note: str | None = None
    samples: list[Mutant] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_ARITH_SWAPS: dict[type, type] = {
    cst.Add: cst.Subtract,
    cst.Subtract: cst.Add,
    cst.Multiply: cst.Divide,
    cst.Divide: cst.Multiply,
}

_COMPARE_SWAPS: dict[type, type] = {
    cst.LessThan: cst.LessThanEqual,
    cst.LessThanEqual: cst.LessThan,
    cst.GreaterThan: cst.GreaterThanEqual,
    cst.GreaterThanEqual: cst.GreaterThan,
    cst.Equal: cst.NotEqual,
    cst.NotEqual: cst.Equal,
}

_BOOL_FLIP = {"True": "False", "False": "True"}
_INT_FLIP = {"0": "1", "1": "0"}


@dataclass(frozen=True)
class MutationSite:
    """One concrete mutation we could apply."""

    file: Path
    line: int
    col: int
    category: str  # "arith" | "compare" | "bool" | "int"
    op_name: str   # e.g. "Add", "True", "0"

    @property
    def operator(self) -> str:
        return f"{self.category}:{self.op_name}"


class _SiteCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, file: Path) -> None:
        super().__init__()
        self.file = file
        self.sites: list[MutationSite] = []

    def _record(self, node: cst.CSTNode, category: str, op_name: str) -> None:
        pos = self.get_metadata(cst.metadata.PositionProvider, node).start
        self.sites.append(MutationSite(self.file, pos.line, pos.column, category, op_name))

    def visit_BinaryOperation(self, node: cst.BinaryOperation) -> None:
        op_type = type(node.operator)
        if op_type in _ARITH_SWAPS:
            self._record(node.operator, "arith", op_type.__name__)

    def visit_ComparisonTarget(self, node: cst.ComparisonTarget) -> None:
        op_type = type(node.operator)
        if op_type in _COMPARE_SWAPS:
            self._record(node.operator, "compare", op_type.__name__)

    def visit_Name(self, node: cst.Name) -> None:
        if node.value in _BOOL_FLIP:
            self._record(node, "bool", node.value)

    def visit_Integer(self, node: cst.Integer) -> None:
        if node.value in _INT_FLIP:
            self._record(node, "int", node.value)


class _ApplyMutation(cst.CSTTransformer):
    """Apply exactly one mutation, identified by (line, col, category)."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, target: MutationSite) -> None:
        super().__init__()
        self.target = target
        self.applied = False

    def _matches(self, node: cst.CSTNode) -> bool:
        if self.applied:
            return False
        pos = self.get_metadata(cst.metadata.PositionProvider, node).start
        return pos.line == self.target.line and pos.column == self.target.col

    def leave_BinaryOperation(
        self, orig: cst.BinaryOperation, updated: cst.BinaryOperation
    ) -> cst.BinaryOperation:
        if self.target.category != "arith":
            return updated
        op_type = type(orig.operator)
        if op_type in _ARITH_SWAPS and self._matches(orig.operator):
            self.applied = True
            return updated.with_changes(operator=_ARITH_SWAPS[op_type]())
        return updated

    def leave_ComparisonTarget(
        self, orig: cst.ComparisonTarget, updated: cst.ComparisonTarget
    ) -> cst.ComparisonTarget:
        if self.target.category != "compare":
            return updated
        op_type = type(orig.operator)
        if op_type in _COMPARE_SWAPS and self._matches(orig.operator):
            self.applied = True
            return updated.with_changes(operator=_COMPARE_SWAPS[op_type]())
        return updated

    def leave_Name(self, orig: cst.Name, updated: cst.Name) -> cst.Name:
        if self.target.category != "bool":
            return updated
        if orig.value in _BOOL_FLIP and self._matches(orig):
            self.applied = True
            return updated.with_changes(value=_BOOL_FLIP[orig.value])
        return updated

    def leave_Integer(self, orig: cst.Integer, updated: cst.Integer) -> cst.Integer:
        if self.target.category != "int":
            return updated
        if orig.value in _INT_FLIP and self._matches(orig):
            self.applied = True
            return updated.with_changes(value=_INT_FLIP[orig.value])
        return updated


def _collect_for_file(file: Path) -> tuple[cst.Module, str, list[MutationSite]] | None:
    """Parse a file once, return its module + original text + every mutation site."""
    source = file.read_text()
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return None
    wrapper = cst.MetadataWrapper(module)
    collector = _SiteCollector(file)
    wrapper.visit(collector)
    return module, source, collector.sites


def _collect_sites(file: Path) -> list[MutationSite]:
    """Single-file site collection (exposed for tests)."""
    result = _collect_for_file(file)
    return [] if result is None else result[2]


def _apply_to_module(module: cst.Module, site: MutationSite) -> str | None:
    """Apply `site` to a pre-parsed module. Returns mutated source or None."""
    wrapper = cst.MetadataWrapper(module)
    transformer = _ApplyMutation(site)
    mutated = wrapper.visit(transformer)
    if not transformer.applied:
        return None
    return mutated.code


def _apply_mutation(site: MutationSite) -> str | None:
    """Single-shot apply (exposed for tests). Re-parses the file."""
    result = _collect_for_file(site.file)
    if result is None:
        return None
    return _apply_to_module(result[0], site)


def _purge_pycache(wt: Path) -> None:
    """Drop every __pycache__ under wt. Python's mtime-based bytecode cache
    can serve stale bytecode when we rewrite a .py file within the same
    second — fix is to drop the cache directories outright."""
    for cache_dir in wt.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


def _run_tests(wt: Path, timeout: int) -> int:
    """Run the agent's visible test suite. Return pytest's exit code.

    Uses `sys.executable -m pytest` rather than `uv run pytest` — the harness
    is already inside uv, so the project's resolved env is on PATH. `uv run`
    would re-resolve the lock on every invocation, adding ~1s of dead time
    per mutant.
    """
    cmd = [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-o", "addopts="]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(
            cmd, cwd=wt, env=env, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        return -1


def score(
    wt: Path,
    max_mutants: int = 30,
    per_mutant_timeout: int = 30,
    total_timeout: int = 180,
    seed: int = 0,
) -> MutationScore:
    """Sample up to `max_mutants` mutation sites, apply each, run tests."""
    sources = discover_sources(wt)
    if not sources:
        return MutationScore(score=0.0, killed=0, total=0, note="no source files under wt/src/")

    parsed: dict[Path, cst.Module] = {}
    originals: dict[Path, str] = {}
    all_sites: list[MutationSite] = []
    for path in sources:
        result = _collect_for_file(path)
        if result is None:
            continue
        module, source, sites = result
        parsed[path] = module
        originals[path] = source
        all_sites.extend(sites)
    if not all_sites:
        return MutationScore(score=0.0, killed=0, total=0, note="no mutation sites found")

    _purge_pycache(wt)
    baseline_rc = _run_tests(wt, timeout=per_mutant_timeout)
    if baseline_rc != 0:
        return MutationScore(
            score=0.0, killed=0, total=0,
            note=f"baseline test run failed (rc={baseline_rc}); mutation skipped",
        )

    rng = random.Random(seed)
    sites = rng.sample(all_sites, max_mutants) if len(all_sites) > max_mutants else list(all_sites)

    killed = 0
    timed_out = False
    samples: list[Mutant] = []
    started = time.monotonic()

    for site in sites:
        if time.monotonic() - started > total_timeout:
            timed_out = True
            break
        mutated_src = _apply_to_module(parsed[site.file], site)
        if mutated_src is None or mutated_src == originals[site.file]:
            continue
        try:
            site.file.write_text(mutated_src)
            rc = _run_tests(wt, timeout=per_mutant_timeout)
        finally:
            site.file.write_text(originals[site.file])
        was_killed = rc != 0
        if was_killed:
            killed += 1
        samples.append(
            Mutant(
                path=str(site.file.relative_to(wt)),
                line=site.line,
                operator=site.operator,
                killed=was_killed,
            )
        )

    total = len(samples)
    score_val = (killed / total) if total else 0.0
    note = None
    if timed_out:
        note = f"hit total_timeout={total_timeout}s after {total}/{len(sites)} mutants"
    return MutationScore(
        score=score_val,
        killed=killed,
        total=total,
        timed_out=timed_out,
        note=note,
        samples=samples,
    )
