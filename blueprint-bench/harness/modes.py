from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class UsageStats:
    """Parsed from the final `type=result` event in stream-json."""

    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    num_turns: int
    is_error: bool
    duration_api_ms: int


@dataclass(frozen=True)
class ModeResult:
    mode: str
    model: str
    returncode: int
    runtime_s: float
    transcript_path: Path
    stderr_path: Path
    timed_out: bool
    command: list[str]
    usage: UsageStats | None


def _build_prompt(mode: str, description: str) -> str:
    if mode == "full":
        # --headless tells the /tdd orchestrator to skip its two human
        # approval gates (Step 1 "Approve spec?" and Step 2 "Approve plan?").
        # Without it, claude -p exits cleanly after writing the plan and the
        # bug never gets fixed. See plugins/blueprint/commands/tdd.md.
        return f"/tdd --headless {description}"
    if mode == "naked":
        return description
    raise ValueError(f"unknown mode: {mode!r}")


def _env_for_claude() -> dict[str, str]:
    """Strip CLAUDECODE so the child invocation isn't treated as nested."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def parse_usage_from_transcript(path: Path) -> UsageStats | None:
    """Walk a stream-json transcript and pull stats from its final result event.

    `claude -p --output-format stream-json` emits one `{"type":"result",...}`
    event at the very end of every successful run with `total_cost_usd`,
    `usage` (input/output/cache tokens), `num_turns`, `duration_api_ms`, and
    `is_error`. Returns None if no result event was emitted (e.g. timeout).
    """
    last_result: dict | None = None
    try:
        f = path.open("r")
    except FileNotFoundError:
        return None
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                last_result = ev
    if last_result is None:
        return None
    usage = last_result.get("usage") or {}
    return UsageStats(
        cost_usd=float(last_result.get("total_cost_usd") or 0.0),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        num_turns=int(last_result.get("num_turns") or 0),
        is_error=bool(last_result.get("is_error", False)),
        duration_api_ms=int(last_result.get("duration_api_ms") or 0),
    )


def run(
    mode: str,
    description: str,
    wt: Path,
    artifacts_dir: Path,
    timeout: int,
    model: str,
) -> ModeResult:
    """Spawn `claude -p` against the working tree and capture its output.

    The transcript is streamed to `{artifacts_dir}/transcript.jsonl` and
    stderr to `{artifacts_dir}/stderr.log`. The agent's CWD is `wt`. `model`
    is passed through as `--model <id>` so each cell pins the model that
    actually ran the work (cost numbers are meaningless otherwise).
    """
    prompt = _build_prompt(mode, description)
    transcript_path = artifacts_dir / "transcript.jsonl"
    stderr_path = artifacts_dir / "stderr.log"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        model,
    ]

    started = time.monotonic()
    timed_out = False
    with transcript_path.open("w") as tout, stderr_path.open("w") as terr:
        try:
            proc = subprocess.run(
                command,
                cwd=wt,
                env=_env_for_claude(),
                stdout=tout,
                stderr=terr,
                timeout=timeout,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            rc = -1
    elapsed = time.monotonic() - started

    usage = parse_usage_from_transcript(transcript_path)

    return ModeResult(
        mode=mode,
        model=model,
        returncode=rc,
        runtime_s=elapsed,
        transcript_path=transcript_path,
        stderr_path=stderr_path,
        timed_out=timed_out,
        command=command,
        usage=usage,
    )


def usage_to_dict(usage: UsageStats | None) -> dict | None:
    return asdict(usage) if usage is not None else None
