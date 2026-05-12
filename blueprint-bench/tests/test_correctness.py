from pathlib import Path

from scorers import correctness


def _make_task_with_oracle(tmp_path: Path, oracle_body: str) -> tuple[Path, Path]:
    task = tmp_path / "task"
    oracle = task / "oracle" / "tests"
    oracle.mkdir(parents=True)
    (oracle / "test_oracle.py").write_text(oracle_body)
    wt = tmp_path / "wt"
    (wt / "subject").mkdir(parents=True)
    (wt / "subject" / "__init__.py").write_text("VALUE = 42\n")
    return task, wt


def test_all_passing_scores_one(tmp_path):
    task, wt = _make_task_with_oracle(
        tmp_path,
        "from subject import VALUE\n"
        "def test_a(): assert VALUE == 42\n"
        "def test_b(): assert VALUE * 2 == 84\n",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = correctness.score(task, wt, run_dir)
    assert result.score == 1.0
    assert result.passed == 2
    assert result.total == 2
    assert result.failures == []


def test_partial_fail_scores_fraction(tmp_path):
    task, wt = _make_task_with_oracle(
        tmp_path,
        "from subject import VALUE\n"
        "def test_a(): assert VALUE == 42\n"
        "def test_b(): assert VALUE == 0\n",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = correctness.score(task, wt, run_dir)
    assert result.passed == 1
    assert result.total == 2
    assert result.score == 0.5
    assert len(result.failures) == 1


def test_all_failing_scores_zero(tmp_path):
    task, wt = _make_task_with_oracle(
        tmp_path,
        "def test_a(): assert False\n"
        "def test_b(): assert False\n",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = correctness.score(task, wt, run_dir)
    assert result.score == 0.0
    assert result.passed == 0
    assert result.total == 2


def test_src_layout_pythonpath_is_honored(tmp_path):
    task = tmp_path / "task"
    oracle = task / "oracle" / "tests"
    oracle.mkdir(parents=True)
    (oracle / "test_oracle.py").write_text(
        "from mypkg import answer\n"
        "def test_a(): assert answer() == 42\n"
    )
    wt = tmp_path / "wt"
    (wt / "src" / "mypkg").mkdir(parents=True)
    (wt / "src" / "mypkg" / "__init__.py").write_text("def answer():\n    return 42\n")
    (wt / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'pythonpath = ["src"]\n'
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = correctness.score(task, wt, run_dir)
    assert result.score == 1.0, result.note
    assert result.passed == 1


def test_missing_module_surfaces_as_collection_error(tmp_path):
    task, wt = _make_task_with_oracle(
        tmp_path,
        "from totally_not_a_real_module import x\n"
        "def test_a(): assert x() == 1\n",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = correctness.score(task, wt, run_dir)
    assert result.score == 0.0
    assert result.total == 0
    assert result.note and "no tests collected" in result.note
    assert any("ModuleNotFoundError" in (f.get("longrepr") or "")
               for f in result.failures)
