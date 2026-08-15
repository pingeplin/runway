"""Isolation-contract tests for ``scripts/run-arm.sh`` (generate cells).

The adversarial-review gap: the generate-cell workspace used to live inside
the repo (``results/<b>/<arm>/seed-<s>/workspace``), so the spec author could
read ``corpus/<b>/oracle.py`` by relative path. The contract now mirrors
``run-implementer.sh``: the LIVE workspace goes under ``ARM_WORKROOT`` which
must resolve OUTSIDE the repo tree (refused otherwise), and ``cell.json``
records that the isolation held. Fully offline: stub ``claude`` binary.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-arm.sh"

STUB = """#!/usr/bin/env bash
# Emits a plausible artifact from inside the workspace (cwd) plus a result
# event on stdout, like a real headless run would.
mkdir -p blueprint/specs
echo '# Spec' > blueprint/specs/spec.md
echo '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"brief.md"}}]}}'
echo '{"type":"result","subtype":"success","num_turns":1,"usage":{"output_tokens":5}}'
"""

LEAKY_STUB = """#!/usr/bin/env bash
# A spec author that Reads the frozen oracle by ABSOLUTE repo path: cwd
# isolation cannot stop this — only the post-hoc C0 transcript scan sees it.
mkdir -p blueprint/specs
echo '# Spec' > blueprint/specs/spec.md
echo '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"/repo/corpus/b01/oracle.py"}}]}}'
echo '{"type":"result","subtype":"success","num_turns":1,"usage":{"output_tokens":5}}'
"""

# Round-3 BLOCKER repro, verbatim: ONE Bash command touching the exempt
# staged brief.md AND the frozen oracle. With single-hit-per-tool_use
# counting, the brief.md-first order recorded only the exempt fragment,
# the exemption dropped it, and the cell scored leak_hits=0 — C0 green.
COMBINED_LEAK_STUB_BRIEF_FIRST = """#!/usr/bin/env bash
mkdir -p blueprint/specs
echo '# Spec' > blueprint/specs/spec.md
echo '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"cat brief.md; cat /repo/eval/blueprint/over-explanation/corpus/b01/oracle.py"}}]}}'
echo '{"type":"result","subtype":"success","num_turns":1,"usage":{"output_tokens":5}}'
"""

COMBINED_LEAK_STUB_BRIEF_LAST = """#!/usr/bin/env bash
mkdir -p blueprint/specs
echo '# Spec' > blueprint/specs/spec.md
echo '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"cat /repo/eval/blueprint/over-explanation/corpus/b01/oracle.py; cat brief.md"}}]}}'
echo '{"type":"result","subtype":"success","num_turns":1,"usage":{"output_tokens":5}}'
"""


def _fixture(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    brief_dir = tmp_path / "corpus" / "b01"
    brief_dir.mkdir(parents=True)
    (brief_dir / "brief.md").write_text("# Brief\n")
    (brief_dir / "brief.json").write_text(json.dumps({"id": "b01"}))

    home = tmp_path / "home"
    (home / ".claude-A0").mkdir(parents=True)

    stub = tmp_path / "bin" / "claude-stub"
    stub.parent.mkdir(parents=True)
    stub.write_text(STUB)
    stub.chmod(0o755)

    results = tmp_path / "results"
    workroot = tmp_path / "arm-workroot"
    env = os.environ.copy()
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.update({
        "HOME": str(home),
        "CLAUDE_BIN": str(stub),
        "RESULTS_ROOT": str(results),
        "ARM_WORKROOT": str(workroot),
    })
    return env, brief_dir, results


def _run(args: list[str], env: dict[str, str],
         cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                          text=True, env=env, cwd=str(cwd), timeout=120)


def test_script_is_bash_n_clean() -> None:
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                          text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_workroot_inside_repo_tree_is_refused(tmp_path: Path) -> None:
    env, brief_dir, _results = _fixture(tmp_path)
    env["ARM_WORKROOT"] = str(ROOT / "results")
    proc = _run(["A0", str(brief_dir), "0"], env, tmp_path)
    assert proc.returncode == 1
    assert "inside the repo tree" in proc.stderr


def test_stub_run_isolates_workspace_and_records_it(tmp_path: Path) -> None:
    env, brief_dir, results = _fixture(tmp_path)
    proc = _run(["A0", str(brief_dir), "0"], env, tmp_path)
    assert proc.returncode == 0, proc.stderr

    cell_dir = results / "b01" / "A0" / "seed-0"
    cell = json.loads((cell_dir / "cell.json").read_text())
    assert cell["workspace_outside_repo"] is True
    live = Path(cell["workspace"])
    # The LIVE workspace resolves outside the repo tree (isolation held).
    assert not str(live.resolve()).startswith(str(ROOT.resolve()) + os.sep)
    assert (live / "brief.md").is_file()

    # The cell is still self-contained: artifacts + a workspace snapshot.
    assert (cell_dir / "artifacts" / "blueprint" / "specs" / "spec.md").is_file()
    snapshot = cell_dir / "workspace"
    assert (snapshot / "brief.md").is_file()
    assert not (snapshot / ".git").exists()


def test_clean_transcript_scans_zero_leak_hits(tmp_path: Path) -> None:
    # §1 C0: the post-hoc scan runs on every cell; reading the cell's own
    # staged brief.md is the task input, never a leak hit.
    env, brief_dir, results = _fixture(tmp_path)
    proc = _run(["A0", str(brief_dir), "0"], env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    cell = json.loads(
        (results / "b01" / "A0" / "seed-0" / "cell.json").read_text())
    assert cell["leak_scanned"] is True
    assert cell["leak_hits"] == 0
    assert cell["leak_hit_details"] == []


@pytest.mark.parametrize("stub_body", [COMBINED_LEAK_STUB_BRIEF_FIRST,
                                       COMBINED_LEAK_STUB_BRIEF_LAST],
                         ids=["brief-md-first", "brief-md-last"])
def test_combined_brief_and_oracle_touch_still_records_leak_hits(
        tmp_path: Path, stub_body: str) -> None:
    # Round-3 BLOCKER: the brief.md staged-input exemption must be
    # order-independent. A single tool_use touching brief.md AND the corpus
    # oracle keeps its non-exempt hits in BOTH fragment orders — the exempt
    # brief.* fragments alone are dropped, never the whole tool_use.
    env, brief_dir, results = _fixture(tmp_path)
    stub = Path(env["CLAUDE_BIN"])
    stub.write_text(stub_body)
    proc = _run(["A0", str(brief_dir), "0"], env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    cell = json.loads(
        (results / "b01" / "A0" / "seed-0" / "cell.json").read_text())
    assert cell["leak_scanned"] is True
    assert cell["leak_hits"] >= 2  # "corpus" and "oracle.py" survive
    fragments = {hit.split(": ", 1)[-1] for hit in cell["leak_hit_details"]}
    assert {"corpus", "oracle.py"} <= fragments
    assert not fragments & {"brief.md", "brief.json"}  # exempt dropped


def test_failed_leak_scan_exits_nonzero_never_green(tmp_path: Path) -> None:
    # Round-3 MAJOR: a cell whose C0 scan cannot run records
    # leak_scanned:false AND the script must exit non-zero — an unscanned
    # cell has no signal and must never look green to the orchestrator.
    env, brief_dir, results = _fixture(tmp_path)
    env["BENCH_MANIFEST"] = str(tmp_path / "no-such-manifest.json")
    proc = _run(["A0", str(brief_dir), "0"], env, tmp_path)
    assert proc.returncode != 0
    assert "leak_scanned:false" in proc.stderr
    cell = json.loads(
        (results / "b01" / "A0" / "seed-0" / "cell.json").read_text())
    assert cell["leak_scanned"] is False
    assert "leak_hits" not in cell  # no signal, not a zero


def test_corpus_touch_in_transcript_records_leak_hits(tmp_path: Path) -> None:
    # The reachability gap the comment used to overclaim: cwd isolation does
    # NOT stop an absolute-path Read of the repo corpus. The C0 transcript
    # scan must see it and record it into cell.json (the score packer then
    # fails the C0_generate_isolation gate on any hit).
    env, brief_dir, results = _fixture(tmp_path)
    stub = Path(env["CLAUDE_BIN"])
    stub.write_text(LEAKY_STUB)
    proc = _run(["A0", str(brief_dir), "0"], env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    cell = json.loads(
        (results / "b01" / "A0" / "seed-0" / "cell.json").read_text())
    assert cell["leak_scanned"] is True
    assert cell["leak_hits"] > 0
    assert any("corpus" in hit for hit in cell["leak_hit_details"])
