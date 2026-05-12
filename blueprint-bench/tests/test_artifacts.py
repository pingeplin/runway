from harness import artifacts, sandbox


def test_collect_flags_no_code_when_only_spec_written(tmp_path, make_task):
    """A cell that produces only a spec/plan markdown file but no
    production code is the workflow failure that motivated this signal —
    `code_files_touched` must come back empty so the runner can mark
    failure_mode='no_code_written'."""
    task = make_task()
    sb = sandbox.build(task, tmp_path / "run")

    (sb.wt / "specs").mkdir()
    (sb.wt / "specs" / "2605.0001_thing.md").write_text("# spec\n")
    (sb.wt / "plans").mkdir()
    (sb.wt / "plans" / "2605.0001_thing_graph.md").write_text("# plan\n")

    captured = artifacts.collect(sb.wt, sb.artifacts_dir, baseline=sb.starter_sha)
    assert captured["code_files_touched"] == []
    assert "specs" in captured["plugin_dirs"]
    assert "plans" in captured["plugin_dirs"]


def test_collect_reports_code_files_when_production_code_changed(tmp_path, make_task):
    """When the agent actually edits production code, the touched paths
    show up under code_files_touched (relative to the working tree)."""
    task = make_task()
    sb = sandbox.build(task, tmp_path / "run")

    (sb.wt / "hello.py").write_text("print('world')\n")
    (sb.wt / "new_module.py").write_text("def f():\n    return 1\n")
    (sb.wt / "specs").mkdir()
    (sb.wt / "specs" / "2605.0001_thing.md").write_text("# spec\n")

    captured = artifacts.collect(sb.wt, sb.artifacts_dir, baseline=sb.starter_sha)
    touched = set(captured["code_files_touched"])
    assert touched == {"hello.py", "new_module.py"}


def test_collect_treats_test_files_as_code(tmp_path, make_task):
    """Tests live under tests/ in the starter. A run that adds tests but
    leaves production code untouched still counts as having written code
    — only specs/ and plans/ are excluded."""
    task = make_task()
    sb = sandbox.build(task, tmp_path / "run")

    (sb.wt / "tests").mkdir(exist_ok=True)
    (sb.wt / "tests" / "test_new.py").write_text("def test_x():\n    assert True\n")

    captured = artifacts.collect(sb.wt, sb.artifacts_dir, baseline=sb.starter_sha)
    assert "tests/test_new.py" in captured["code_files_touched"]
