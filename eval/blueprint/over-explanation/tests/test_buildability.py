from __future__ import annotations

import sys
from pathlib import Path

from eval_overexplanation.buildability import (
    MutationResult,
    OracleResult,
    run_mutations,
    run_oracle,
)
from eval_overexplanation.models import Mutation, OracleCase


# --------------------------------------------------------------------------- #
# Fixtures: a tiny real impl + a tiny real pytest test written into tmp_path.
# --------------------------------------------------------------------------- #

_IMPL_SOURCE = '''\
def add(a, b):
    return a + b
'''

# A real pytest test that pins add()'s behaviour. The semantic mutation below
# (+ -> -) makes add(2, 3) == -1 != 5, so this suite fails => mutant killed.
_TEST_SOURCE = '''\
from impl import add


def test_add():
    assert add(2, 3) == 5
    assert add(0, 0) == 0
'''


def _make_impl(root: Path) -> Path:
    impl_dir = root / "impl_dir"
    impl_dir.mkdir()
    (impl_dir / "impl.py").write_text(_IMPL_SOURCE)
    (impl_dir / "test_impl.py").write_text(_TEST_SOURCE)
    return impl_dir


# --------------------------------------------------------------------------- #
# Oracle
# --------------------------------------------------------------------------- #


def test_oracle_counts_pass_and_fail(tmp_path):
    """Correct cases pass; a wrong-expected case is counted failed and reported."""
    impl_dir = _make_impl(tmp_path)
    cases = (
        OracleCase(label="two_plus_three", args=(2, 3), expected=5),
        OracleCase(label="zeros", args=(0, 0), expected=0),
        OracleCase(label="wrong_expectation", args=(1, 1), expected=99),
    )

    result = run_oracle(impl_dir, module="impl", entrypoint="add", cases=cases)

    assert isinstance(result, OracleResult)
    assert result.passed == 2
    assert result.failed == 1
    assert result.total == 3
    assert result.correctness == 2 / 3
    assert len(result.errors) == 1
    assert "wrong_expectation" in result.errors[0]


def test_oracle_does_not_mutate_impl_dir(tmp_path):
    """The oracle runs in a copy; impl_dir is left byte-for-byte unchanged."""
    impl_dir = _make_impl(tmp_path)
    before = (impl_dir / "impl.py").read_text()
    listing_before = sorted(p.name for p in impl_dir.iterdir())

    run_oracle(
        impl_dir,
        module="impl",
        entrypoint="add",
        cases=(OracleCase(label="c", args=(1, 2), expected=3),),
    )

    assert (impl_dir / "impl.py").read_text() == before
    assert sorted(p.name for p in impl_dir.iterdir()) == listing_before


def test_oracle_empty_cases_is_zero_correctness(tmp_path):
    """No cases => nothing demonstrated => correctness 0.0, no errors."""
    impl_dir = _make_impl(tmp_path)

    result = run_oracle(impl_dir, module="impl", entrypoint="add", cases=())

    assert result.total == 0
    assert result.correctness == 0.0
    assert result.errors == ()


def test_oracle_exception_is_counted_failed(tmp_path):
    """An impl that raises is a failed case, surfaced in errors (not a crash)."""
    impl_dir = tmp_path / "boom"
    impl_dir.mkdir()
    (impl_dir / "impl.py").write_text("def add(a, b):\n    raise RuntimeError('nope')\n")

    result = run_oracle(
        impl_dir,
        module="impl",
        entrypoint="add",
        cases=(OracleCase(label="c", args=(1, 2), expected=3),),
    )

    assert result.passed == 0
    assert result.failed == 1
    assert "c" in result.errors[0]
    # The case must fail because the impl *raised*, not because import/lookup
    # failed. Pin the in-impl exception so a regression to instant-import
    # shadowing (which would also satisfy failed==1) cannot pass vacuously.
    assert "raised" in result.errors[0]
    assert "RuntimeError" in result.errors[0]
    assert "import/lookup failed" not in result.errors[0]


def test_oracle_timeout_fails_every_case(tmp_path):
    """A hanging impl times out and fails all cases rather than blocking forever."""
    import time

    impl_dir = tmp_path / "hang"
    impl_dir.mkdir()
    (impl_dir / "impl.py").write_text(
        "import time\n\n\ndef add(a, b):\n    time.sleep(30)\n    return a + b\n"
    )

    start = time.monotonic()
    result = run_oracle(
        impl_dir,
        module="impl",
        entrypoint="add",
        cases=(OracleCase(label="slow", args=(1, 2), expected=3),),
        timeout=1.0,
    )
    elapsed = time.monotonic() - start

    assert result.passed == 0
    assert result.failed == 1
    assert "slow" in result.errors[0]
    # The subprocess must actually have run and been killed by the timeout, not
    # returned instantly via an import-failure shortcut. Pin elapsed >= timeout
    # (with slack above) so a regression to instant-import-failure can't make
    # this test vacuously pass again.
    assert "timed out" in result.errors[0]
    assert elapsed >= 1.0
    assert elapsed < 1.0 + 15.0


# --------------------------------------------------------------------------- #
# Mutation testing (real subprocess pytest runs)
# --------------------------------------------------------------------------- #

# Invoke pytest as a subprocess via the harness interpreter. test_cmd is
# caller-supplied per the contract; this keeps the unit test offline and
# uv-free while still being a real subprocess test run.
_TEST_CMD = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]


def test_mutations_kill_survive_and_invalid(tmp_path):
    """A semantic mutation is killed, a no-op survives, a non-matching one is invalid."""
    impl_dir = _make_impl(tmp_path)
    mutations = (
        # Semantic: flips add to subtract -> suite fails -> killed.
        Mutation(label="plus_to_minus", filename="impl.py", find="a + b", replace="a - b"),
        # No-op: equivalent reformatting that keeps the result -> suite passes -> survives.
        Mutation(label="noop_reorder", filename="impl.py", find="a + b", replace="b + a"),
        # Invalid: find-string absent from the file -> reported invalid, excluded.
        Mutation(label="absent", filename="impl.py", find="a * b", replace="a / b"),
    )

    result = run_mutations(impl_dir, _TEST_CMD, mutations)

    assert isinstance(result, MutationResult)
    assert result.killed == 1
    assert result.survived == ("noop_reorder",)
    assert result.invalid == ("absent",)
    # Invalid is excluded from the denominator: 1 killed of 2 valid.
    assert result.total == 2
    assert result.kill_rate == 0.5


def test_mutation_find_occurring_twice_is_invalid(tmp_path):
    """A find-string matching more than once is ambiguous => invalid, not applied."""
    impl_dir = tmp_path / "dup"
    impl_dir.mkdir()
    (impl_dir / "impl.py").write_text("X = 1\nY = 1\n")
    (impl_dir / "test_impl.py").write_text(
        "from impl import X, Y\n\n\ndef test_x():\n    assert X == 1 and Y == 1\n"
    )

    result = run_mutations(
        impl_dir,
        _TEST_CMD,
        (Mutation(label="dup_one", filename="impl.py", find="1", replace="2"),),
    )

    assert result.invalid == ("dup_one",)
    assert result.killed == 0
    assert result.survived == ()
    assert result.total == 0
    assert result.kill_rate == 0.0


def test_mutation_does_not_touch_impl_dir(tmp_path):
    """Mutations are applied only in copies; the original file is unchanged."""
    impl_dir = _make_impl(tmp_path)
    before = (impl_dir / "impl.py").read_text()

    run_mutations(
        impl_dir,
        _TEST_CMD,
        (Mutation(label="plus_to_minus", filename="impl.py", find="a + b", replace="a - b"),),
    )

    assert (impl_dir / "impl.py").read_text() == before


def test_mutation_timeout_counts_as_killed(tmp_path):
    """A mutant that makes the suite hang is killed (suite did not green-light it)."""
    impl_dir = tmp_path / "hangmut"
    impl_dir.mkdir()
    (impl_dir / "impl.py").write_text("DELAY = 0\n")
    # The test sleeps for DELAY seconds; mutating DELAY 0 -> 30 makes it hang.
    (impl_dir / "test_impl.py").write_text(
        "import time\nfrom impl import DELAY\n\n\n"
        "def test_quick():\n    time.sleep(DELAY)\n    assert True\n"
    )

    result = run_mutations(
        impl_dir,
        _TEST_CMD,
        (Mutation(label="slow_down", filename="impl.py", find="DELAY = 0", replace="DELAY = 30"),),
        timeout=2.0,
    )

    assert result.killed == 1
    assert result.survived == ()
    assert result.invalid == ()
    assert result.kill_rate == 1.0
