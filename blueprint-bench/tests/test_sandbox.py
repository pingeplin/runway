from pathlib import Path

from harness import sandbox


def _make_task(tmp_path: Path) -> Path:
    task = tmp_path / "task"
    starter = task / "starter"
    starter.mkdir(parents=True)
    (starter / "hello.py").write_text("print('hi')\n")
    (starter / "tests").mkdir()
    (starter / "tests" / "test_hello.py").write_text("def test_x():\n    assert 1\n")
    oracle = task / "oracle" / "tests"
    oracle.mkdir(parents=True)
    (oracle / "test_oracle.py").write_text("def test_o():\n    assert 1\n")
    return task


def test_build_copies_only_starter(tmp_path):
    task = _make_task(tmp_path)
    sb = sandbox.build(task, tmp_path / "run")

    assert sb.wt.is_dir()
    assert (sb.wt / "hello.py").exists()
    assert (sb.wt / "tests" / "test_hello.py").exists()

    # Oracle MUST NOT be present in the working tree.
    assert not (sb.wt / "oracle").exists()
    for p in sb.wt.rglob("*"):
        assert "oracle" not in p.name.lower()


def test_build_initializes_git_baseline(tmp_path):
    task = _make_task(tmp_path)
    sb = sandbox.build(task, tmp_path / "run")
    assert (sb.wt / ".git").is_dir()


def test_capture_diff_reports_post_starter_changes(tmp_path):
    task = _make_task(tmp_path)
    sb = sandbox.build(task, tmp_path / "run")

    (sb.wt / "hello.py").write_text("print('hello world')\n")
    diff = sandbox.capture_diff(sb.wt, baseline=sb.starter_sha)
    assert "hello world" in diff
    assert "diff --git" in diff


def test_capture_diff_survives_agent_commit(tmp_path):
    """The /tdd flow ends with /commit, advancing HEAD inside wt/. The
    captured diff must still show the agent's work, not zero changes."""
    import subprocess

    task = _make_task(tmp_path)
    sb = sandbox.build(task, tmp_path / "run")

    (sb.wt / "hello.py").write_text("print('hello world')\n")
    env = {
        "GIT_AUTHOR_NAME": "agent",
        "GIT_AUTHOR_EMAIL": "a@b.c",
        "GIT_COMMITTER_NAME": "agent",
        "GIT_COMMITTER_EMAIL": "a@b.c",
    }
    import os
    env = {**os.environ, **env}
    subprocess.run(["git", "add", "-A"], cwd=sb.wt, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "agent-work"], cwd=sb.wt, check=True, env=env)

    diff = sandbox.capture_diff(sb.wt, baseline=sb.starter_sha)
    assert "hello world" in diff
    assert "diff --git" in diff


def test_build_is_idempotent(tmp_path):
    task = _make_task(tmp_path)
    sandbox.build(task, tmp_path / "run")
    sb2 = sandbox.build(task, tmp_path / "run")
    assert sb2.wt.is_dir()
    assert (sb2.wt / "hello.py").exists()
