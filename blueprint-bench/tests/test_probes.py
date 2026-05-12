from pathlib import Path

from harness import probes


def test_clean_working_tree_passes_pre_probe(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "a.py").write_text("pass\n")
    result = probes.run_probes(wt, transcript_path=None, leak_paths=[], stage="pre")
    assert result.pre_clean is True
    assert result.compromised is False


def test_oracle_named_file_trips_pre_probe(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "oracle_notes.txt").write_text("oops\n")
    result = probes.run_probes(wt, transcript_path=None, leak_paths=[], stage="pre")
    assert result.pre_clean is False
    assert any("oracle_notes" in o for o in result.pre_offenders)


def test_transcript_hit_marks_compromised(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"tool_use","input":{"file_path":"oracle/tests/test_pagination_oracle.py"}}\n'
    )
    leak_paths = ["oracle/tests/test_pagination_oracle.py"]
    result = probes.run_probes(wt, transcript_path=transcript, leak_paths=leak_paths, stage="post")
    assert result.compromised is True
    assert "oracle/tests/test_pagination_oracle.py" in result.transcript_hits


def test_clean_transcript_passes_post_probe(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"type":"tool_use","input":{"file_path":"src/foo.py"}}\n')
    leak_paths = ["oracle/tests/test_pagination_oracle.py"]
    result = probes.run_probes(wt, transcript_path=transcript, leak_paths=leak_paths, stage="post")
    assert result.compromised is False


def test_liveness_blocks_when_path_unresolvable(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    # leak path resolves to wt / oracle / tests / ... — doesn't exist in this tree.
    result = probes.run_probes(
        wt,
        transcript_path=None,
        leak_paths=["oracle/tests/test_pagination_oracle.py"],
        stage="post",
    )
    assert result.liveness_reads_blocked is True


def test_liveness_fails_when_oracle_present(tmp_path):
    wt = tmp_path / "wt"
    (wt / "oracle" / "tests").mkdir(parents=True)
    (wt / "oracle" / "tests" / "test_x.py").write_text("# leaked\n")
    result = probes.run_probes(
        wt,
        transcript_path=None,
        leak_paths=["oracle/tests/test_x.py"],
        stage="post",
    )
    assert result.liveness_reads_blocked is False
    assert result.compromised is True


def test_load_leak_paths_strips_comments_and_blanks(tmp_path):
    task = tmp_path / "task"
    (task / "oracle").mkdir(parents=True)
    (task / "oracle" / "leak_paths.txt").write_text(
        "# header\n\n"
        "oracle/tests/test_a.py\n"
        "oracle/tests\n"
        "  # indented comment ignored\n"
        "oracle\n"
    )
    paths = probes.load_leak_paths(task)
    assert paths == ["oracle/tests/test_a.py", "oracle/tests", "oracle"]
