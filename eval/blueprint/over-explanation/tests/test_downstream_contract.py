"""Contract tests for ``scripts/run-implementer.sh`` (BENCHMARK.md §3).

Fully offline: every test drives the script as a subprocess with hand-built
``tmp_path`` fixtures and — for the happy/retry paths — a stub ``claude``
binary that emits a canned stream-json transcript. No network, no live CLI.

Covered contract surface:

* usage / argument validation exits 2 with a message (§2 exit-code table);
  input-state failures (missing brief, spec count != 1, config dir absent,
  workroot inside the repo tree) exit 1 and fail closed;
* the workspace stages the SPEC ONLY — never ``brief.md``/corpus assets
  (§1 U0 leakage rule: isolation is reachability);
* ``impl-cell.json`` carries the §3 provenance record, and ``prompt_sha`` is
  sha256 over the exact prompt handed to the CLI (U0's gate input);
* ``error_during_execution`` retries with ``retried: true``; the last
  transcript wins.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-implementer.sh"

SPEC_BODY = "# Spec\n\nMaintain a running total over a list of integers.\n"

STUB_OK = """#!/usr/bin/env bash
printf '%s\\0' "$@" > "$CLAUDE_STUB_ARGS"
echo run >> "$CLAUDE_STUB_CALLS"
cat <<'EOF'
{"type":"system","subtype":"init"}
not json at all
{"type":"result","subtype":"success","num_turns":3,"usage":{"output_tokens":42},"total_cost_usd":0.01,"duration_ms":5}
EOF
"""

STUB_ERROR = """#!/usr/bin/env bash
printf '%s\\0' "$@" > "$CLAUDE_STUB_ARGS"
echo run >> "$CLAUDE_STUB_CALLS"
cat <<'EOF'
{"type":"result","subtype":"error_during_execution","num_turns":1}
EOF
"""


@dataclass(frozen=True)
class Fixture:
    """Paths for one staged (arm, brief, seed) downstream cell."""

    env: dict[str, str]
    corpus: Path
    results: Path
    impl_root: Path
    workroot: Path
    home: Path
    artifacts: Path

    @property
    def cell(self) -> Path:
        return self.impl_root / "b01" / "A0" / "seed-0"


def _make_fixture(tmp_path: Path, *, spec_count: int = 1) -> Fixture:
    corpus = tmp_path / "corpus"
    brief_dir = corpus / "b01"
    brief_dir.mkdir(parents=True)
    (brief_dir / "brief.json").write_text(
        json.dumps(
            {
                "id": "b01",
                "title": "Running total",
                "regime": "neutral",
                "buildable": True,
                "module": "running_total",
                "entrypoint": "compute_total",
            }
        )
    )
    # brief.md exists in the corpus but must NEVER reach the workspace.
    (brief_dir / "brief.md").write_text("# Brief\n\nSecret brief text.\n")

    results = tmp_path / "results"
    artifacts = results / "b01" / "A0" / "seed-0" / "artifacts" / "blueprint" / "specs"
    artifacts.mkdir(parents=True)
    for i in range(spec_count):
        name = "spec.md" if i == 0 else f"spec-{i}.md"
        (artifacts / name).write_text(SPEC_BODY)

    home = tmp_path / "home"
    (home / ".claude-implementer").mkdir(parents=True)

    impl_root = tmp_path / "impl"
    workroot = tmp_path / "workroot"

    env = os.environ.copy()
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.update(
        {
            "HOME": str(home),
            "IMPLEMENTER_MODEL": "pinned-model-x",
            "CORPUS_ROOT": str(corpus),
            "RESULTS_ROOT": str(results),
            "IMPL_ROOT": str(impl_root),
            "IMPL_WORKROOT": str(workroot),
        }
    )
    return Fixture(
        env=env,
        corpus=corpus,
        results=results,
        impl_root=impl_root,
        workroot=workroot,
        home=home,
        artifacts=artifacts,
    )


def _stub_claude(tmp_path: Path, fixture: Fixture, body: str) -> Path:
    stub = tmp_path / "bin" / "claude-stub"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(body)
    stub.chmod(0o755)
    fixture.env["CLAUDE_BIN"] = str(stub)
    fixture.env["CLAUDE_STUB_ARGS"] = str(tmp_path / "stub-args.bin")
    fixture.env["CLAUDE_STUB_CALLS"] = str(tmp_path / "stub-calls.txt")
    return stub


def _run(
    args: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    run_env = env if env is not None else {**os.environ, "IMPLEMENTER_MODEL": "pinned-model-x"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=run_env,
        cwd=str(cwd) if cwd is not None else str(ROOT),
        timeout=120,
    )


def _stub_prompt(fixture: Fixture) -> str:
    argv = Path(fixture.env["CLAUDE_STUB_ARGS"]).read_bytes().split(b"\0")[:-1]
    args = [a.decode() for a in argv]
    return args[args.index("-p") + 1]


# ---------------------------------------------------------------------------
# Script hygiene + usage/argument validation (exit 2).
# ---------------------------------------------------------------------------


def test_script_is_bash_n_clean() -> None:
    proc = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr


def test_help_prints_usage_and_exits_zero() -> None:
    proc = _run(["--help"])
    assert proc.returncode == 0
    assert "Usage: run-implementer.sh <ARM_ID> <BRIEF> <SEED>" in proc.stdout


def test_no_arguments_is_usage_error() -> None:
    proc = _run([])
    assert proc.returncode == 2
    assert "expected exactly 3 arguments" in proc.stderr
    assert "Usage:" in proc.stderr


def test_wrong_argument_count_is_usage_error() -> None:
    for args in (["A0"], ["A0", "b01"], ["A0", "b01", "0", "extra"]):
        proc = _run(args)
        assert proc.returncode == 2, (args, proc.stderr)
        assert "expected exactly 3 arguments" in proc.stderr


def test_dash_arm_id_is_usage_error() -> None:
    proc = _run(["--bogus", "b01", "0"])
    assert proc.returncode == 2
    assert "ARM_ID" in proc.stderr


def test_dash_brief_is_usage_error() -> None:
    proc = _run(["A0", "--bogus", "0"])
    assert proc.returncode == 2
    assert "BRIEF" in proc.stderr


def test_non_integer_seed_is_usage_error() -> None:
    proc = _run(["A0", "b01", "one"])
    assert proc.returncode == 2
    assert "SEED must be an integer" in proc.stderr


def test_missing_implementer_model_is_usage_error() -> None:
    env = os.environ.copy()
    env.pop("IMPLEMENTER_MODEL", None)
    proc = _run(["A0", "b01", "0"], env=env)
    assert proc.returncode == 2
    assert "IMPLEMENTER_MODEL" in proc.stderr


# ---------------------------------------------------------------------------
# Fail-closed input-state paths (exit 1) — never reach a live CLI.
# ---------------------------------------------------------------------------


def test_missing_brief_json_exits_one(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    proc = _run(["A0", "no-such-brief", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert "brief.json not found" in proc.stderr


def test_non_buildable_brief_exits_one(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    brief_json = fixture.corpus / "b01" / "brief.json"
    data = json.loads(brief_json.read_text())
    data["buildable"] = False
    brief_json.write_text(json.dumps(data))
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert "not buildable" in proc.stderr


def test_brief_without_interface_pin_exits_one(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    brief_json = fixture.corpus / "b01" / "brief.json"
    data = json.loads(brief_json.read_text())
    del data["module"]
    brief_json.write_text(json.dumps(data))
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert "module/entrypoint" in proc.stderr


def test_zero_specs_records_missing_cell_and_exits_one(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path, spec_count=0)
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert "exactly 1 spec artifact" in proc.stderr
    cell = json.loads((fixture.cell / "impl-cell.json").read_text())
    assert cell["status"] == "missing"
    assert cell["arm"] == "A0" and cell["brief_id"] == "b01" and cell["seed"] == 0


def test_ambiguous_specs_record_missing_cell_and_exit_one(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path, spec_count=2)
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert "found 2" in proc.stderr
    assert json.loads((fixture.cell / "impl-cell.json").read_text())["status"] == "missing"


def test_workroot_inside_repo_tree_is_refused(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    fixture.env["IMPL_WORKROOT"] = str(ROOT / "scripts")
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert "inside the repo tree" in proc.stderr


def test_missing_implementer_config_dir_exits_one(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    (fixture.home / ".claude-implementer").rmdir()
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 1
    assert ".claude-implementer" in proc.stderr


# ---------------------------------------------------------------------------
# Stubbed end-to-end: staging, prompt shape, provenance record, retry.
# ---------------------------------------------------------------------------


def test_stub_run_stages_spec_only_and_records_cell(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    _stub_claude(tmp_path, fixture, STUB_OK)
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr

    # U0 leakage rule: the SPEC ONLY reaches the workspace — never brief.md,
    # brief.json, or any corpus asset.
    captured = fixture.cell / "workspace"
    assert (captured / "SPEC.md").read_text() == SPEC_BODY
    staged = {p.name for p in captured.rglob("*") if p.is_file()}
    assert "brief.md" not in staged and "brief.json" not in staged
    assert not (captured / ".git").exists()  # audit lives in git-log.txt
    assert (fixture.cell / "git-log.txt").exists()

    # Transcript captured verbatim; last result event wins downstream.
    transcript = (fixture.cell / "transcript.jsonl").read_text()
    assert '"type":"result"' in transcript.replace(" ", "")

    cell = json.loads((fixture.cell / "impl-cell.json").read_text())
    assert cell["implementer_model"] == "pinned-model-x"
    assert cell["module"] == "running_total"
    assert cell["entrypoint"] == "compute_total"
    assert cell["status"] == "ok"
    assert cell["retried"] is False
    assert cell["return_code"] == 0
    assert cell["spec_sha"] == hashlib.sha256(SPEC_BODY.encode()).hexdigest()

    # Prompt = rendered preamble + spec text, nothing else; prompt_sha is the
    # sha256 of the exact string handed to the CLI (U0 gate input).
    prompt = _stub_prompt(fixture)
    assert "running_total" in prompt and "compute_total" in prompt
    assert prompt.endswith(SPEC_BODY.rstrip("\n"))
    assert "Secret brief text" not in prompt
    assert "A0" not in prompt  # no arm identity in the prompt
    assert cell["prompt_sha"] == hashlib.sha256(prompt.encode()).hexdigest()


def test_stub_run_pins_model_and_permission_flags(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    _stub_claude(tmp_path, fixture, STUB_OK)
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    argv = [a.decode() for a in Path(fixture.env["CLAUDE_STUB_ARGS"]).read_bytes().split(b"\0")[:-1]]
    assert argv[argv.index("--model") + 1] == "pinned-model-x"
    assert "--permission-mode" in argv and "acceptEdits" in argv
    assert "--output-format" in argv and "stream-json" in argv


def test_error_during_execution_retries_and_marks_retried(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    _stub_claude(tmp_path, fixture, STUB_ERROR)
    fixture.env["MAX_RETRIES"] = "1"
    fixture.env["RETRY_BACKOFF_SECS"] = "0"
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    # Fail-closed exit contract: status != "ok" exits non-zero even though the
    # stubbed CLI itself returned 0 (the orchestrator must count this cell).
    assert proc.returncode != 0, proc.stdout
    assert "fail-closed" in proc.stderr

    calls = Path(fixture.env["CLAUDE_STUB_CALLS"]).read_text().splitlines()
    assert len(calls) == 2  # initial attempt + exactly MAX_RETRIES=1 retry

    cell = json.loads((fixture.cell / "impl-cell.json").read_text())
    assert cell["retried"] is True
    assert cell["status"] == "error"


def test_no_result_event_cell_exits_nonzero_with_missing_status(
    tmp_path: Path,
) -> None:
    # The exact fabricated-cheap-cell case: the CLI exits 0 but the transcript
    # carries no result event. The cell must read status="missing" AND the
    # script must exit non-zero so the orchestrator counts the failure.
    fixture = _make_fixture(tmp_path)
    stub = """#!/usr/bin/env bash
printf '%s\\0' "$@" > "$CLAUDE_STUB_ARGS"
echo run >> "$CLAUDE_STUB_CALLS"
echo '{"type":"system","subtype":"init"}'
exit 0
"""
    _stub_claude(tmp_path, fixture, stub)
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode != 0, proc.stdout
    assert "fail-closed" in proc.stderr
    cell = json.loads((fixture.cell / "impl-cell.json").read_text())
    assert cell["status"] == "missing"
    assert cell["return_code"] == 0  # the CLI rc is still recorded verbatim


def test_garbled_result_event_exits_nonzero_with_missing_status(
    tmp_path: Path,
) -> None:
    # Regression (round-3 MINOR): the shell status derivation accepted any
    # result event with a subtype as "ok", while usage.parse_usage reads a
    # truncated event (no num_turns / usage.output_tokens) as "missing".
    # The script now derives status THROUGH parse_usage, so the two agree
    # and the script exits non-zero on the truncated cell.
    fixture = _make_fixture(tmp_path)
    stub = """#!/usr/bin/env bash
printf '%s\\0' "$@" > "$CLAUDE_STUB_ARGS"
echo run >> "$CLAUDE_STUB_CALLS"
echo '{"type":"result","subtype":"success"}'
exit 0
"""
    _stub_claude(tmp_path, fixture, stub)
    proc = _run(["A0", "b01", "0"], env=fixture.env, cwd=tmp_path)
    assert proc.returncode != 0, proc.stdout
    assert "fail-closed" in proc.stderr
    cell = json.loads((fixture.cell / "impl-cell.json").read_text())
    assert cell["status"] == "missing"  # exactly what the scorer will say
    assert cell["return_code"] == 0
