"""Deterministic ground truth for referee accuracy (layer 1) and attribution (layer 2).

For each task: B's failing FAIL_TO_PASS tests, clustered by root error, with how
many tests of each cluster C and C0 fixed. Read from fb eval outputs only.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent / "results"
RUNS = json.loads((RUN / "runs.json").read_text())
ARMS = ("B", "C", "C0")
SECTION_RE = re.compile(r"^_{3,} (?:ERROR at (?:setup|teardown) of )?(.+?) _{3,}$")
FRAME_RE = re.compile(r"^(astropy/\S+?\.py):(\d+): in (\S+)")


def eval_dir(arm: str, task: str) -> Path:
    run_dir = Path(RUNS[arm]["output_jsonl"]).parent
    return next((run_dir / "eval_outputs" / task).glob("attempt-*"))


def f2p(arm: str, task: str) -> tuple[set[str], set[str]]:
    report = json.loads((eval_dir(arm, task) / "report.json").read_text())
    status = (report.get(task) or report)["tests_status"]["FAIL_TO_PASS"]
    return set(status["success"]), set(status["failure"])


def root_errors(arm: str, task: str) -> dict[str, tuple[str, str]]:
    """pytest section name -> (first E line, deepest non-test astropy frame)."""
    out: dict[str, tuple[str, str]] = {}
    name, frame, err, pending = None, "", None, ""
    for line in (eval_dir(arm, task) / "test_output.txt").read_text(errors="replace").splitlines():
        m = SECTION_RE.match(line)
        if m:
            if name and err:
                out.setdefault(name, (err, frame))
            name, frame, err, pending = m.group(1), "", None, ""
            continue
        if name is None:
            continue
        fm = FRAME_RE.match(line)
        if fm and "/tests/" not in fm.group(1):
            pending = f"{fm.group(1)}:{fm.group(3)}"
        if line.startswith("E   "):
            # Chained tracebacks print the handled inner exception first; the
            # last E line in a section is the exception that failed the test.
            err, frame = line[4:].strip(), pending
    if name and err:
        out.setdefault(name, (err, frame))
    return out


def section_key(node_id: str) -> str:
    parts = node_id.split("::")[1:]
    return ".".join(parts)


def normalise(err: str) -> str:
    err = re.sub(r"0x[0-9a-f]+", "0x…", err)
    err = re.sub(r"(None|/\S+?):\d+:\d+:", "<pos>:", err)
    return err[:160]


def group(arm: str, task: str, nodes: set[str]) -> dict[tuple[str, str], list[str]]:
    errors = root_errors(arm, task)
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node in sorted(nodes):
        err, frame = errors.get(section_key(node), ("(no traceback captured)", ""))
        grouped[(normalise(err), frame)].append(node)
    return grouped


def regressions(task: str) -> list[dict]:
    b_ok, _ = f2p("B", task)
    out = []
    for arm in ("C", "C0"):
        broke = b_ok & f2p(arm, task)[1]
        for (err, frame), nodes in sorted(group(arm, task, broke).items(), key=lambda kv: -len(kv[1])):
            out.append({"arm": arm, "n_tests": len(nodes), "root_error": err,
                        "deepest_source_frame": frame, "sample_tests": nodes[:3]})
    return out


def clusters(task: str) -> list[dict]:
    b_ok, b_fail = f2p("B", task)
    errors = root_errors("B", task)
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node in sorted(b_fail):
        err, frame = errors.get(section_key(node), ("(no traceback captured)", ""))
        grouped[(normalise(err), frame)].append(node)
    passes = {arm: f2p(arm, task)[0] for arm in ("C", "C0")}
    result = []
    for i, ((err, frame), nodes) in enumerate(sorted(grouped.items(), key=lambda kv: -len(kv[1])), 1):
        result.append({
            "cluster": f"F{i}",
            "n_tests": len(nodes),
            "root_error": err,
            "deepest_source_frame": frame,
            "sample_tests": nodes[:4],
            "fixed_in_C": sum(n in passes["C"] for n in nodes),
            "fixed_in_C0": sum(n in passes["C0"] for n in nodes),
        })
    return result


def main() -> None:
    tasks = [l.strip() for l in (RUN.parent / "panel.txt").read_text().splitlines() if l.strip()]
    gt = {}
    for task in tasks:
        totals = {arm: len(f2p(arm, task)[0]) for arm in ARMS}
        n = sum(len(s) for s in f2p("B", task))
        gt[task] = {"n_f2p": n, "passing": totals, "b_failure_clusters": clusters(task), "round2_regressions": regressions(task)}
    (Path(__file__).parent / "ground_truth.json").write_text(json.dumps(gt, indent=2))
    for task, g in gt.items():
        print(f"\n{task.split('.')[2]}  F2P={g['n_f2p']}  pass B/C/C0={g['passing']['B']}/{g['passing']['C']}/{g['passing']['C0']}")
        for c in g["b_failure_clusters"]:
            print(f"  {c['cluster']:>4} n={c['n_tests']:<3} C+{c['fixed_in_C']:<3} C0+{c['fixed_in_C0']:<3} {c['deepest_source_frame'][:48]:<48} {c['root_error'][:70]}")
        for r in g["round2_regressions"]:
            print(f"  REGR {r['arm']:<3} n={r['n_tests']:<3} {r['deepest_source_frame'][:48]:<48} {r['root_error'][:70]}")


if __name__ == "__main__":
    sys.exit(main())
