"""Refactor-robustness scorer — apply trusted behavior-preserving
refactorings to the agent's SUT, rerun oracle tests, score = avg pass rate.
Surfaces oracle tests that over-fit to implementation detail.
"""
from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import libcst as cst

from scorers import correctness
from scorers._shared import discover_sources


@dataclass
class RefactoringResult:
    name: str
    score: float
    passed: int
    total: int
    note: str | None = None


@dataclass
class RefactorScore:
    score: float
    refactorings: list[RefactoringResult] = field(default_factory=list)
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class _RenameLocalsTransformer(cst.CSTTransformer):
    """Rename every non-parameter, non-global Name inside a function body.

    This is conservative: we only rename names that are *assigned* inside the
    function (and aren't function parameters). Imported names, globals, and
    method-resolution names stay put.
    """

    def __init__(self) -> None:
        super().__init__()
        self._scopes: list[dict[str, str]] = []
        self._counter = 0

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        scope: dict[str, str] = {}
        params = node.params
        param_names: set[str] = set()
        for p in (
            list(params.params)
            + list(params.kwonly_params)
            + list(params.posonly_params)
        ):
            param_names.add(p.name.value)
        if params.star_arg and isinstance(params.star_arg, cst.Param):
            param_names.add(params.star_arg.name.value)
        if params.star_kwarg:
            param_names.add(params.star_kwarg.name.value)

        for target in _iter_assigned_names(node.body):
            if target in param_names or target.startswith("_r"):
                continue
            self._counter += 1
            scope[target] = f"_r{self._counter}"
        self._scopes.append(scope)

    def leave_FunctionDef(
        self, orig: cst.FunctionDef, updated: cst.FunctionDef
    ) -> cst.FunctionDef:
        self._scopes.pop()
        return updated

    def leave_Name(self, orig: cst.Name, updated: cst.Name) -> cst.Name:
        for scope in reversed(self._scopes):
            if orig.value in scope:
                return updated.with_changes(value=scope[orig.value])
        return updated


class _AssignedNameCollector(cst.CSTVisitor):
    """Best-effort: collect every Name that's assigned somewhere in the subtree."""

    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()

    def visit_Assign(self, node: cst.Assign) -> None:
        for target in node.targets:
            self._extract(target.target)

    def visit_AugAssign(self, node: cst.AugAssign) -> None:
        self._extract(node.target)

    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:
        self._extract(node.target)

    def visit_For(self, node: cst.For) -> None:
        self._extract(node.target)

    def _extract(self, target: cst.CSTNode) -> None:
        if isinstance(target, cst.Name):
            self.names.add(target.value)
        elif isinstance(target, (cst.Tuple, cst.List)):
            for elt in target.elements:
                self._extract(elt.value)


def _iter_assigned_names(body: cst.CSTNode) -> set[str]:
    collector = _AssignedNameCollector()
    body.visit(collector)
    return collector.names


def _refactor_rename_locals(file: Path) -> bool:
    """Return True iff the file was modified."""
    original = file.read_text()
    try:
        module = cst.parse_module(original)
    except cst.ParserSyntaxError:
        return False
    transformed = module.visit(_RenameLocalsTransformer())
    if transformed.code == original:
        return False
    file.write_text(transformed.code)
    return True


def _refactor_reorder_toplevel(file: Path) -> bool:
    """Swap adjacent independent top-level function definitions.

    Only operates when there are 2+ consecutive FunctionDef nodes with no
    intervening statements. Class definitions and imports are not reordered.
    """
    original = file.read_text()
    try:
        module = cst.parse_module(original)
    except cst.ParserSyntaxError:
        return False

    body = list(module.body)
    changed = False
    i = 0
    while i < len(body) - 1:
        a, b = body[i], body[i + 1]
        if isinstance(a, cst.FunctionDef) and isinstance(b, cst.FunctionDef):
            body[i], body[i + 1] = b, a
            changed = True
            i += 2
        else:
            i += 1

    if not changed:
        return False
    transformed = module.with_changes(body=body)
    file.write_text(transformed.code)
    return True


REFACTORINGS: list[tuple[str, Callable[[Path], bool]]] = [
    ("rename_locals", _refactor_rename_locals),
    ("reorder_toplevel_funcs", _refactor_reorder_toplevel),
]


def _snapshot_sources(sources: list[Path]) -> dict[Path, str]:
    return {p: p.read_text() for p in sources}


def _restore_sources(snapshot: dict[Path, str]) -> None:
    for path, content in snapshot.items():
        path.write_text(content)


def score(
    task_dir: Path,
    wt: Path,
    run_dir: Path,
) -> RefactorScore:
    """Apply each refactoring, run oracle tests, average pass-rate.

    A refactoring that doesn't modify any source file is skipped and reported
    with a note rather than counted as 0 — that way pass-throughs (like
    `reorder_toplevel_funcs` on a single-function module) don't drag the
    score down.
    """
    sources = discover_sources(wt)
    if not sources:
        return RefactorScore(score=0.0, note="no source files under wt/src/")

    snapshot = _snapshot_sources(sources)
    results: list[RefactoringResult] = []

    refactor_work_dir = run_dir / "refactor"
    refactor_work_dir.mkdir(parents=True, exist_ok=True)

    try:
        for name, fn in REFACTORINGS:
            # Eager list — `any(fn(p) for ...)` short-circuits, which would
            # apply `fn` only until the first file mutates and silently leave
            # subsequent files untouched (oracle then runs against a
            # partially-refactored tree).
            applied = [fn(path) for path in sources]
            if not any(applied):
                results.append(
                    RefactoringResult(
                        name=name, score=1.0, passed=0, total=0,
                        note="no-op (no eligible sites)",
                    )
                )
                continue

            this_run_dir = refactor_work_dir / name
            this_run_dir.mkdir(parents=True, exist_ok=True)
            try:
                corr = correctness.score(task_dir, wt, this_run_dir)
            finally:
                _restore_sources(snapshot)

            results.append(
                RefactoringResult(
                    name=name,
                    score=corr.score,
                    passed=corr.passed,
                    total=corr.total,
                    note=corr.note,
                )
            )
    finally:
        _restore_sources(snapshot)
        shutil.rmtree(refactor_work_dir, ignore_errors=True)

    counted = [r for r in results if r.total > 0]
    if not counted:
        return RefactorScore(
            score=1.0,
            refactorings=results,
            note="all refactorings were no-ops",
        )
    avg = sum(r.score for r in counted) / len(counted)
    return RefactorScore(score=avg, refactorings=results)
