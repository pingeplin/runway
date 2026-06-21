"""Executed oracle + strategic mutation testing (issue #10, fix #3).

The implementation under test is **untrusted generated code**. This module
never imports it into the harness process: it copies ``impl_dir`` into a fresh
temporary directory and runs everything in a **subprocess** under a timeout, so
the harness cannot be crashed, hung, or compromised by a bad impl, and so the
original ``impl_dir`` is never mutated in place.

Two measurements live here:

* ``run_oracle`` — does the impl produce the right answers? Runs a frozen set
  of ``OracleCase`` calls against ``entrypoint`` inside a sandbox subprocess and
  counts pass/fail.
* ``run_mutations`` — does the brief's own test suite actually have teeth? For
  each strategic source mutation we copy the impl, apply one literal text
  replacement, run the suite, and check whether it noticed (killed) the change.
  A mutation whose ``find`` string does not occur exactly once is *invalid* and
  is reported (not silently skipped — a silent skip would inflate the kill
  rate). A mutant on which the suite times out counts as *killed* (the suite
  hung on the mutant rather than passing it).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .models import Mutation, OracleCase


# --------------------------------------------------------------------------- #
# Oracle: executed correctness over a frozen case list
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OracleResult:
    """Outcome of running the hidden oracle cases against one impl.

    ``errors`` carries human-readable descriptions of every case that did not
    pass (wrong answer, exception, import failure, timeout). ``failed`` is the
    count of non-passing cases and always equals ``len(errors)``.
    """

    passed: int
    failed: int
    errors: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def correctness(self) -> float:
        """passed / total; 0.0 for an empty case list (nothing demonstrated)."""
        if self.total == 0:
            return 0.0
        return self.passed / self.total


# The runner executed in the sandbox subprocess. It imports the impl module,
# calls the entrypoint for each case, compares ``== expected`` and prints a
# single JSON object on stdout. The subprocess is launched with ``cwd`` set to
# the *copied* impl dir, but Python does NOT put cwd on ``sys.path`` for a
# ``python script.py`` invocation (sys.path[0] is the runner script's own
# directory). So the runner explicitly prepends its cwd — the copied impl dir —
# to ``sys.path``, so a plain ``import <module>`` resolves the untrusted copy.
# The harness process never imports it.
_ORACLE_RUNNER = r'''
import json, os, sys, traceback, importlib

sys.path.insert(0, os.getcwd())

spec_path = sys.argv[1]
with open(spec_path) as fh:
    spec = json.load(fh)

module_name = spec["module"]
entrypoint = spec["entrypoint"]
cases = spec["cases"]

results = []
try:
    mod = importlib.import_module(module_name)
    fn = getattr(mod, entrypoint)
    import_error = None
except Exception:
    import_error = traceback.format_exc(limit=3)
    mod = None
    fn = None

for case in cases:
    label = case["label"]
    if import_error is not None:
        results.append({"label": label, "ok": False,
                        "error": "import/lookup failed: " + import_error.strip().splitlines()[-1]})
        continue
    try:
        got = fn(*case["args"])
        if got == case["expected"]:
            results.append({"label": label, "ok": True})
        else:
            results.append({"label": label, "ok": False,
                            "error": "expected %r got %r" % (case["expected"], got)})
    except Exception:
        tb = traceback.format_exc(limit=3).strip().splitlines()[-1]
        results.append({"label": label, "ok": False, "error": "raised " + tb})

sys.stdout.write(json.dumps({"results": results}))
'''


def run_oracle(
    impl_dir: Path,
    module: str,
    entrypoint: str,
    cases: Sequence[OracleCase],
    *,
    timeout: float = 30.0,
) -> OracleResult:
    """Run the frozen oracle cases against the impl in a sandbox subprocess.

    Copies ``impl_dir`` to a tempdir, writes a runner that imports ``module``,
    calls ``entrypoint(*case.args)`` and compares ``== case.expected`` for each
    case, executes it via ``[sys.executable, runner]`` in the copy, and parses
    the pass/fail results. The original ``impl_dir`` is never touched and the
    untrusted impl is never imported into this process. A timeout or crash of
    the whole runner fails *every* case (the impl could not even be exercised).
    Always cleans up the tempdir.
    """
    cases = tuple(cases)
    if not cases:
        return OracleResult(passed=0, failed=0, errors=())

    with tempfile.TemporaryDirectory(prefix="oracle_") as tmp:
        tmp_path = Path(tmp)
        # Name the copy dir something OTHER than a plausible module name so it
        # cannot be picked up as an implicit namespace package that shadows the
        # real ``<module>.py`` living inside it. The runner resolves ``module``
        # from its cwd (this dir), not from the parent tmp dir.
        work = tmp_path / "impl_copy"
        shutil.copytree(impl_dir, work)

        spec = {
            "module": module,
            "entrypoint": entrypoint,
            "cases": [
                {"label": c.label, "args": list(c.args), "expected": c.expected}
                for c in cases
            ],
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        runner_path = tmp_path / "_oracle_runner.py"
        runner_path.write_text(_ORACLE_RUNNER)

        try:
            proc = subprocess.run(
                [sys.executable, str(runner_path), str(spec_path)],
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            errors = tuple(
                f"{c.label}: timed out after {timeout}s" for c in cases
            )
            return OracleResult(passed=0, failed=len(cases), errors=errors)

        parsed = _parse_oracle_output(proc, cases)
        return parsed


def _parse_oracle_output(
    proc: subprocess.CompletedProcess[str], cases: tuple[OracleCase, ...]
) -> OracleResult:
    """Map the runner's JSON stdout to an OracleResult.

    If the runner crashed before emitting parseable JSON (non-zero exit, garbled
    stdout), every case is counted as failed with the captured stderr — the impl
    could not be exercised, so nothing is demonstrated.
    """
    try:
        payload = json.loads(proc.stdout)
        results = payload["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        detail = (proc.stderr or proc.stdout or "no output").strip()
        detail = detail.splitlines()[-1] if detail else "no output"
        errors = tuple(f"{c.label}: runner failed: {detail}" for c in cases)
        return OracleResult(passed=0, failed=len(cases), errors=errors)

    passed = 0
    errors: list[str] = []
    for entry in results:
        if entry.get("ok"):
            passed += 1
        else:
            errors.append(f"{entry['label']}: {entry.get('error', 'failed')}")
    return OracleResult(passed=passed, failed=len(errors), errors=tuple(errors))


# --------------------------------------------------------------------------- #
# Mutation testing: does the brief's own suite have teeth?
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MutationResult:
    """Outcome of strategic mutation testing over one impl + its test suite.

    ``survived`` holds the labels of mutations the suite passed (a real defect
    the tests did not catch). ``invalid`` holds the labels whose ``find`` string
    did not occur exactly once in the target file — those are excluded from the
    denominator and reported, never silently dropped.
    """

    killed: int
    survived: tuple[str, ...]
    invalid: tuple[str, ...]

    @property
    def total(self) -> int:
        """Valid mutants only: killed + survived. Invalid ones are excluded."""
        return self.killed + len(self.survived)

    @property
    def kill_rate(self) -> float:
        """killed / total over valid mutants; 0.0 if there are no valid ones."""
        if self.total == 0:
            return 0.0
        return self.killed / self.total


def run_mutations(
    impl_dir: Path,
    test_cmd: Sequence[str],
    mutations: Sequence[Mutation],
    *,
    timeout: float = 120.0,
) -> MutationResult:
    """Run strategic mutation testing against the impl's own test suite.

    For each mutation: copy ``impl_dir`` to a fresh tempdir, apply the single
    literal ``find`` -> ``replace`` replacement in ``mutation.filename``, and run
    ``test_cmd`` (e.g. ``["uv", "run", "pytest", "-q"]``) as a subprocess with
    cwd set to the copy. A non-zero exit means the suite *killed* the mutant; a
    zero exit means it *survived* (a defect the tests missed); a timeout counts
    as killed (the suite hung on the mutant rather than green-lighting it).

    A mutation whose ``find`` string does not occur exactly once in the target
    file is *invalid*: it is reported and excluded from the kill-rate denominator
    rather than silently skipped (a silent skip would inflate the kill rate).
    ``impl_dir`` is never mutated in place.
    """
    test_cmd = list(test_cmd)
    killed = 0
    survived: list[str] = []
    invalid: list[str] = []

    for mut in mutations:
        verdict = _run_single_mutation(impl_dir, test_cmd, mut, timeout)
        if verdict == "invalid":
            invalid.append(mut.label)
        elif verdict == "killed":
            killed += 1
        else:  # "survived"
            survived.append(mut.label)

    return MutationResult(
        killed=killed,
        survived=tuple(survived),
        invalid=tuple(invalid),
    )


def _run_single_mutation(
    impl_dir: Path,
    test_cmd: list[str],
    mut: Mutation,
    timeout: float,
) -> str:
    """Apply one mutation in a copy and report 'killed' / 'survived' / 'invalid'.

    The ``find`` count is validated against the *original* file content before
    any write, so an absent or ambiguous find-string is invalid without ever
    touching the impl copy's behaviour.
    """
    with tempfile.TemporaryDirectory(prefix="mutate_") as tmp:
        work = Path(tmp) / "impl"
        shutil.copytree(impl_dir, work)

        target = work / mut.filename
        if not target.is_file():
            return "invalid"

        original = target.read_text()
        if original.count(mut.find) != 1:
            return "invalid"

        target.write_text(original.replace(mut.find, mut.replace, 1))

        try:
            proc = subprocess.run(
                test_cmd,
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            # The suite hung on the mutant: treat as killed, not survived.
            return "killed"

        return "killed" if proc.returncode != 0 else "survived"
