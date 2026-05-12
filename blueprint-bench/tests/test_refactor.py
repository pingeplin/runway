from pathlib import Path

from scorers import refactor


def _make_task_wt(tmp_path: Path, src: str, oracle: str) -> tuple[Path, Path]:
    task = tmp_path / "task"
    (task / "oracle" / "tests").mkdir(parents=True)
    (task / "oracle" / "tests" / "test_oracle.py").write_text(oracle)
    wt = tmp_path / "wt"
    (wt / "src" / "subject").mkdir(parents=True)
    (wt / "src" / "subject" / "__init__.py").write_text(src)
    (wt / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'pythonpath = ["src"]\n'
    )
    return task, wt


def test_rename_locals_renames_assigned_names(tmp_path):
    f = tmp_path / "f.py"
    f.write_text(
        "def f(a, b):\n"
        "    tmp = a + b\n"
        "    out = tmp * 2\n"
        "    return out\n"
    )
    changed = refactor._refactor_rename_locals(f)
    assert changed
    content = f.read_text()
    assert "tmp" not in content
    assert "out" not in content
    assert "_r1" in content and "_r2" in content
    assert "a + b" in content  # params untouched


def test_rename_locals_skips_parameters(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("def f(a, b):\n    return a + b\n")
    changed = refactor._refactor_rename_locals(f)
    assert not changed  # no local assignments → nothing to rename


def test_reorder_swaps_adjacent_function_defs(tmp_path):
    f = tmp_path / "f.py"
    f.write_text(
        "def a():\n    return 1\n"
        "def b():\n    return 2\n"
    )
    changed = refactor._refactor_reorder_toplevel(f)
    assert changed
    content = f.read_text()
    assert content.index("def b") < content.index("def a")


def test_reorder_noop_on_single_function(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("def a():\n    return 1\n")
    changed = refactor._refactor_reorder_toplevel(f)
    assert not changed


def test_score_passes_under_behavior_preserving_refactor(tmp_path):
    """Refactorings are behavior-preserving by construction — oracle tests
    must still pass after each refactoring is applied."""
    task, wt = _make_task_wt(
        tmp_path,
        src=(
            "def add(a, b):\n"
            "    result = a + b\n"
            "    return result\n"
            "def sub(a, b):\n"
            "    diff = a - b\n"
            "    return diff\n"
        ),
        oracle=(
            "from subject import add, sub\n"
            "def test_add(): assert add(2, 3) == 5\n"
            "def test_sub(): assert sub(5, 2) == 3\n"
        ),
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = refactor.score(task, wt, run_dir)
    assert result.score == 1.0
    assert all(r.score == 1.0 for r in result.refactorings if r.total > 0)


def test_score_restores_originals_after_run(tmp_path):
    task, wt = _make_task_wt(
        tmp_path,
        src=(
            "def add(a, b):\n"
            "    result = a + b\n"
            "    return result\n"
        ),
        oracle="def test_smoke(): assert True\n",
    )
    original = (wt / "src" / "subject" / "__init__.py").read_text()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    refactor.score(task, wt, run_dir)
    assert (wt / "src" / "subject" / "__init__.py").read_text() == original


def test_score_refactors_every_eligible_file(tmp_path, monkeypatch):
    """Regression: `any(fn(p) for p in sources)` short-circuits, leaving
    later files unrefactored. Make sure every eligible file gets touched."""
    task, wt = _make_task_wt(
        tmp_path,
        src="# placeholder, real files below\n",
        oracle="def test_smoke(): assert True\n",
    )
    # Create two source files; both have rename-eligible locals.
    a = wt / "src" / "subject" / "a.py"
    b = wt / "src" / "subject" / "b.py"
    a.write_text("def f(x):\n    tmp = x + 1\n    return tmp\n")
    b.write_text("def g(x):\n    tmp = x * 2\n    return tmp\n")

    touched: list[str] = []
    real_rename = refactor._refactor_rename_locals

    def spy(path):
        touched.append(path.name)
        return real_rename(path)

    monkeypatch.setattr(refactor, "_refactor_rename_locals", spy)
    # The REFACTORINGS table holds the original fn reference — patch it too.
    monkeypatch.setattr(
        refactor,
        "REFACTORINGS",
        [(name, spy if name == "rename_locals" else fn) for name, fn in refactor.REFACTORINGS],
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    refactor.score(task, wt, run_dir)

    # Every source file must have been considered by the refactor pass.
    assert "a.py" in touched
    assert "b.py" in touched


def test_score_no_sources(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = refactor.score(task, wt, run_dir)
    assert result.score == 0.0
    assert result.note and "no source files" in result.note
