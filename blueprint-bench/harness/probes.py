from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProbeResult:
    pre_clean: bool
    pre_offenders: list[str] = field(default_factory=list)
    post_clean: bool = True
    post_offenders: list[str] = field(default_factory=list)
    transcript_hits: list[str] = field(default_factory=list)
    liveness_reads_blocked: bool = True
    liveness_failures: list[str] = field(default_factory=list)

    @property
    def compromised(self) -> bool:
        return not (
            self.pre_clean
            and self.post_clean
            and not self.transcript_hits
            and self.liveness_reads_blocked
        )

    def to_dict(self) -> dict:
        return {
            "compromised": self.compromised,
            "pre_clean": self.pre_clean,
            "pre_offenders": self.pre_offenders,
            "post_clean": self.post_clean,
            "post_offenders": self.post_offenders,
            "transcript_hits": self.transcript_hits,
            "liveness_reads_blocked": self.liveness_reads_blocked,
            "liveness_failures": self.liveness_failures,
        }


_ORACLE_TOKEN = re.compile(r"oracle", re.IGNORECASE)


def scan_for_oracle_files(wt: Path) -> list[str]:
    """Return any paths inside `wt` whose name mentions 'oracle' (case-insensitive).

    The working tree should never contain oracle artifacts. A pre-run match
    means the sandbox builder leaked; a post-run match means the agent
    fetched or wrote oracle content into the tree.
    """
    offenders: list[str] = []
    for p in wt.rglob("*"):
        if ".git" in p.parts:
            continue
        if _ORACLE_TOKEN.search(p.name):
            offenders.append(str(p.relative_to(wt)))
    return offenders


def scan_transcript(transcript_path: Path, leak_paths: list[str]) -> list[str]:
    """Return any oracle paths referenced in the agent's transcript.

    Reads a JSONL stream-json transcript and flags any occurrence of a known
    leak path. A match means the agent referenced an oracle artifact during
    its run (read, listed, or wrote about it).
    """
    if not transcript_path.exists():
        return []
    body = transcript_path.read_text(errors="replace")
    hits: list[str] = []
    for path in leak_paths:
        if path and path in body:
            hits.append(path)
    return hits


def liveness_check(wt: Path, leak_paths: list[str]) -> tuple[bool, list[str]]:
    """Verify each leak path is unreadable from inside `wt`.

    A path is considered blocked iff a relative-from-wt resolution fails to
    find the file. Absolute paths in `leak_paths` are skipped — if the agent
    guessed an absolute path, post-run transcript scanning would catch it.
    """
    failures: list[str] = []
    for raw in leak_paths:
        if not raw:
            continue
        candidate = (wt / raw).resolve()
        if candidate.exists():
            failures.append(str(candidate))
    return (not failures, failures)


def run_probes(
    wt: Path,
    transcript_path: Path | None,
    leak_paths: list[str],
    stage: str = "post",
) -> ProbeResult:
    """Run the configured probes against a working tree.

    `stage='pre'` only inspects the working tree (before the agent runs).
    `stage='post'` runs all probes including transcript scanning.
    """
    pre_offenders = scan_for_oracle_files(wt)
    result = ProbeResult(
        pre_clean=not pre_offenders,
        pre_offenders=pre_offenders,
    )
    if stage == "pre":
        return result

    post_offenders = scan_for_oracle_files(wt)
    result.post_offenders = post_offenders
    result.post_clean = not post_offenders

    if transcript_path is not None:
        result.transcript_hits = scan_transcript(transcript_path, leak_paths)

    ok, failures = liveness_check(wt, leak_paths)
    result.liveness_reads_blocked = ok
    result.liveness_failures = failures
    return result


def load_leak_paths(task_dir: Path) -> list[str]:
    """Read oracle/leak_paths.txt; one path per line; '#' lines ignored."""
    path = task_dir / "oracle" / "leak_paths.txt"
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            lines.append(s)
    return lines


def write_probe_report(result: ProbeResult, dest: Path) -> None:
    dest.write_text(json.dumps(result.to_dict(), indent=2))
