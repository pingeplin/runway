"""Blind opus judge: referee claim accuracy (layer 1) and attribution (layer 2).

The judge sees the verdict, B's patch, B's failure clusters (without fix counts),
referenced test sources, and the two round-2 patches under random X/Y labels.
It runs through `claude -p` with every tool disabled, in an empty directory,
with the prompt on stdin (argv would hit ARG_MAX on the larger packets).
"""
import argparse
import json
import random
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / "results"
RUNS = json.loads((RUN / "runs.json").read_text())
OUT = HERE / "judge"
REF_RE = re.compile(r"((?:astropy/)?[\w/]+\.py)::((?:\w+::)?\w+)")


def patch(arm: str, task: str) -> str:
    for line in open(RUNS[arm]["output_jsonl"]):
        row = json.loads(line)
        if row["instance_id"] == task:
            return row["model_patch"]
    raise KeyError(task)


def block(source: str, name: str) -> str | None:
    lines = source.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*)def {re.escape(name)}\b", line)
        if not m:
            continue
        indent = len(m.group(1))
        body = [line]
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent and not nxt.lstrip().startswith(("@", ")", "]")):
                break
            body.append(nxt)
        return "\n".join(body[:60])
    return None


def resolve(task: str, path: str, base: str) -> Path | None:
    """Verdicts often cite a bare basename; pick the copy nearest the base patch's files."""
    ws = RUN / "workspaces" / task
    direct = ws / path
    if direct.exists():
        return direct
    touched = re.findall(r"^diff --git a/(\S+)", base, re.M)
    candidates = sorted(ws.glob(f"**/{Path(path).name}"))
    if not candidates:
        return None

    def shared(c: Path) -> int:
        rel = c.relative_to(ws).parts
        return max((sum(1 for _ in __import__("itertools").takewhile(lambda ab: ab[0] == ab[1], zip(rel, Path(t).parts))) for t in touched), default=0)

    return max(candidates, key=shared)


def referenced_tests(task: str, verdict: str, base: str) -> str:
    added = "\n".join(l[1:] for l in base.splitlines() if l.startswith("+") and not l.startswith("+++"))
    parts, seen = [], set()
    for path, qual in REF_RE.findall(verdict):
        name = qual.split("::")[-1]
        if not name.startswith("test") or (path, name) in seen:
            continue
        seen.add((path, name))
        src = None
        ws_file = resolve(task, path, base)
        if ws_file is not None:
            path = str(ws_file.relative_to(RUN / "workspaces" / task))
            src = block(ws_file.read_text(errors="replace"), name)
        where = "existing repository test"
        if src is None:
            src, where = block(added, name), "added by the BASE PATCH"
        if src:
            parts.append(f"### {path}::{qual} ({where})\n```python\n{src}\n```")
        else:
            parts.append(f"### {path}::{qual}\n(not found in the repository or the BASE PATCH)")
    return "\n\n".join(parts) or "(the verdict names no test functions)"


def packet(task: str) -> tuple[str, dict]:
    gt = json.loads((HERE / "ground_truth.json").read_text())[task]
    verdict = (RUN / "verdicts" / f"{task}.md").read_text()
    base = patch("B", task)
    clusters = [{k: c[k] for k in ("cluster", "n_tests", "root_error", "deepest_source_frame", "sample_tests")}
                for c in gt["b_failure_clusters"]]
    tasks = [l.strip() for l in (HERE.parent / "panel.txt").read_text().splitlines() if l.strip()]
    # Alternate by panel position so neither arm sits in the X slot on most tasks.
    first = "C" if tasks.index(task) % 2 == 0 else "C0"
    mapping = {"X": first, "Y": "C0" if first == "C" else "C"}
    body = "\n\n".join([
        (HERE / "judge_prompt.md").read_text(),
        f"# VERDICT\n\n{verdict}",
        f"# BASE PATCH\n\n```diff\n{base}\n```",
        "# BASE FAILURES\n\n" + (json.dumps(clusters, indent=1) if clusters else "(none — the base patch passes every hidden test)"),
        f"# REFERENCED TEST SOURCES\n\n{referenced_tests(task, verdict, base)}",
        f"# PATCH X\n\n```diff\n{patch(mapping['X'], task)}\n```",
        f"# PATCH Y\n\n```diff\n{patch(mapping['Y'], task)}\n```",
    ])
    return body, mapping


def run(task: str, rep: int, model: str, timeout: int) -> dict:
    out = OUT / f"{task}.r{rep}.json"
    if out.exists() and json.loads(out.read_text()).get("parsed"):
        return json.loads(out.read_text())
    prompt, mapping = packet(task)
    started = time.time()
    with tempfile.TemporaryDirectory() as blind:
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--tools", "", "--model", model],
            input=prompt, cwd=blind, capture_output=True, text=True, timeout=timeout,
        )
    rec = {"task": task, "rep": rep, "model": model, "mapping": mapping, "prompt_chars": len(prompt),
           "wall_seconds": round(time.time() - started, 1), "returncode": proc.returncode}
    try:
        payload = json.loads(proc.stdout)
        rec["cost_usd"] = payload.get("total_cost_usd")
        text = payload.get("result", "")
        rec["raw"] = text
        rec["parsed"] = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (json.JSONDecodeError, ValueError) as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}; stderr={proc.stderr[-400:]}"
    OUT.mkdir(exist_ok=True)
    out.write_text(json.dumps(rec, indent=2))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--repeats-task", default="astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tasks = [l.strip() for l in (HERE.parent / "panel.txt").read_text().splitlines() if l.strip()]
    if args.dry_run:
        for t in tasks:
            body, mapping = packet(t)
            refs = body.split("# REFERENCED TEST SOURCES")[1].split("# PATCH X")[0]
            print(f"{t.split('.')[2]:<28} {len(body):>7} chars  X={mapping['X']:<2} Y={mapping['Y']:<2} tests_found={refs.count('```python')} not_found={refs.count('not found')}")
        return
    jobs = [(t, 1) for t in tasks] + [(args.repeats_task, r) for r in range(2, args.repeats + 1)]
    with ThreadPoolExecutor(args.parallel) as pool:
        for rec in pool.map(lambda j: run(j[0], j[1], args.model, args.timeout), jobs):
            status = "ok" if rec.get("parsed") else f"FAILED {rec.get('error', '')[:120]}"
            print(f"{rec['task'].split('.')[2]:<28} r{rec['rep']} ${rec.get('cost_usd') or 0:.2f} {rec['wall_seconds']}s {status}", flush=True)


if __name__ == "__main__":
    main()
