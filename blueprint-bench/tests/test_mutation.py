from pathlib import Path

from scorers import mutation


def _make_wt(tmp_path: Path, src: str, tests: str) -> Path:
    wt = tmp_path / "wt"
    (wt / "src" / "subject").mkdir(parents=True)
    (wt / "src" / "subject" / "__init__.py").write_text(src)
    (wt / "tests").mkdir()
    (wt / "tests" / "test_subject.py").write_text(tests)
    (wt / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'pythonpath = ["src"]\n'
        'testpaths = ["tests"]\n'
    )
    return wt


def test_collects_arith_compare_bool_int_sites(tmp_path):
    f = tmp_path / "f.py"
    f.write_text(
        "def add(a, b):\n"
        "    return a + b\n"
        "def gt(a, b):\n"
        "    return a > b\n"
        "def flag():\n"
        "    return True\n"
        "def zero():\n"
        "    return 0\n"
    )
    sites = mutation._collect_sites(f)
    ops = sorted({s.operator.split(":")[0] for s in sites})
    assert ops == ["arith", "bool", "compare", "int"]


def test_apply_mutation_swaps_operator(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("def add(a, b):\n    return a + b\n")
    sites = mutation._collect_sites(f)
    arith = [s for s in sites if s.operator.startswith("arith:")][0]
    mutated = mutation._apply_mutation(arith)
    assert mutated is not None
    assert "a - b" in mutated
    assert "a + b" not in mutated


def test_apply_mutation_returns_none_when_target_missing(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("def add(a, b):\n    return a + b\n")
    bogus = mutation.MutationSite(file=f, line=999, col=0, category="arith", op_name="Add")
    assert mutation._apply_mutation(bogus) is None


def test_score_kills_obvious_mutants(tmp_path):
    """Tight tests around an arithmetic function should kill arith mutations."""
    wt = _make_wt(
        tmp_path,
        src="def add(a, b):\n    return a + b\n",
        tests=(
            "from subject import add\n"
            "def test_add(): assert add(2, 3) == 5\n"
            "def test_add_zero(): assert add(0, 0) == 0\n"
            "def test_add_neg(): assert add(-1, 1) == 0\n"
        ),
    )
    result = mutation.score(wt, max_mutants=5, per_mutant_timeout=30)
    assert result.total >= 1
    assert result.killed == result.total
    assert result.score == 1.0


def test_score_survives_when_tests_are_tautological(tmp_path):
    """A trivial test that never depends on the SUT shouldn't kill mutants.

    The test below imports add() but only asserts something always-true. So
    every arithmetic mutation should *survive*."""
    wt = _make_wt(
        tmp_path,
        src="def add(a, b):\n    return a + b\n",
        tests=(
            "from subject import add\n"
            "def test_smoke():\n"
            "    add(1, 2)  # call it but don't check result\n"
            "    assert True\n"
        ),
    )
    result = mutation.score(wt, max_mutants=5, per_mutant_timeout=30)
    assert result.total >= 1
    assert result.killed == 0
    assert result.score == 0.0


def test_score_returns_zero_when_no_sources(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    result = mutation.score(wt)
    assert result.score == 0.0
    assert result.total == 0
    assert result.note and "no source files" in result.note


def test_score_skips_when_baseline_fails(tmp_path):
    """If the agent's tests don't even pass on unmutated code, we can't draw
    inferences from mutation testing. The scorer must skip cleanly."""
    wt = _make_wt(
        tmp_path,
        src="def add(a, b):\n    return a + b\n",
        tests=(
            "from subject import add\n"
            "def test_broken(): assert add(1, 1) == 3\n"
        ),
    )
    result = mutation.score(wt, max_mutants=5, per_mutant_timeout=30)
    assert result.score == 0.0
    assert result.total == 0
    assert result.note and "baseline" in result.note
