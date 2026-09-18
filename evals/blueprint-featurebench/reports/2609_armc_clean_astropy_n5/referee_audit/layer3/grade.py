"""Layer-3 grader: do an arm's tests catch bugs in the specified behaviour?

Every arm is graded against the same target — the task's unmasked reference
(`/root/my_repo`) — and the same deterministic mutants, generated only on the lines
the dataset's mask removes and kept only if the hidden FAIL_TO_PASS tests kill them.

Controls, all per task:
  identity   ast.unparse of each mutated file must leave the hidden tests' results unchanged
  positive   split the passing hidden tests in half; score each half on the other's mutants
  negative   a suite that only imports the masked modules
Arm tests are the test functions the arm's patch added or modified, applied after the
oracle test files are deleted (as fb does), selected by exact node id.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent.parent / "results"
RUNS = json.loads((RUN / "runs.json").read_text())
OUT = HERE / "results"
PRELUDE = "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && "
PYTEST = "pytest -p no:cacheprovider -rA --color=no -q --timeout=60"
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
STATUS = re.compile(r"^(PASSED|FAILED|ERROR|XPASS|XFAIL) (.+?)(?: - .*)?$")
ARMS = ("B", "C", "C0")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Box:
    def __init__(self, image: str) -> None:
        p = subprocess.run(["docker", "run", "-d", "--platform", "linux/amd64", "-w", "/testbed",
                            image, "tail", "-f", "/dev/null"], capture_output=True, text=True, timeout=900)
        if p.returncode:
            raise RuntimeError(p.stderr)
        self.cid = p.stdout.strip().splitlines()[-1]

    def sh(self, script: str, timeout: int = 1200, stdin: str | None = None) -> tuple[int | None, str]:
        try:
            p = subprocess.run(["docker", "exec", "-i", self.cid, "bash", "-c", PRELUDE + script],
                               capture_output=True, text=True, timeout=timeout, input=stdin)
            return p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            return None, "outer timeout"

    def put(self, path: str, text: str) -> None:
        rc, out = self.sh(f"cat > {shlex.quote(path)}", 120, text)
        if rc:
            raise RuntimeError(out)

    def close(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.cid], capture_output=True, timeout=300)


def pytest(box: Box, ids: list[str]) -> tuple[int | None, set[str], set[str]]:
    """Returns (rc, passed node ids, failed-or-errored node ids)."""
    rc, out = box.sh(f"cd /testbed && {PYTEST} " + " ".join(shlex.quote(i) for i in ids))
    passed, failed = set(), set()
    for line in out.splitlines():
        m = STATUS.match(line)
        if m:
            (passed if m.group(1) in ("PASSED", "XFAIL") else failed).add(m.group(2).strip())
    return rc, passed, failed


def row_for(task: str) -> dict:
    return next(json.loads(l) for l in open(RUN / "dataset_arm_b/data/fast.jsonl") if json.loads(l)["instance_id"] == task)


def arm_test_blocks(arm: str, task: str) -> list[str]:
    patch = next(json.loads(l)["model_patch"] for l in open(RUNS[arm]["output_jsonl"]) if json.loads(l)["instance_id"] == task)
    blocks = re.split(r"(?=^diff --git )", patch, flags=re.M)
    return [b for b in blocks if re.match(r"diff --git a/\S*tests?/\S+\.py ", b)]


def changed_b_lines(block: str) -> set[int]:
    lines, b, in_hunk = set(), 0, False
    for line in block.splitlines():
        m = HUNK.match(line)
        if m:
            b, in_hunk = int(m.group(3)), True
            continue
        if not in_hunk or line.startswith("\\"):
            continue
        if line.startswith("+"):
            lines.add(b)
            b += 1
        elif line.startswith("-"):
            lines.add(b)
        else:
            b += 1
    return lines


def grade_task(task: str, cap: int, arms: tuple[str, ...]) -> dict:
    row = row_for(task)
    f2p = row["FAIL_TO_PASS"]
    f2p = json.loads(f2p) if isinstance(f2p, str) else f2p
    oracle_files = sorted({t.split("::")[0] for t in f2p})
    arm_blocks = {a: arm_test_blocks(a, task) for a in arms}
    graded_arms = [a for a in arms if arm_blocks[a]]
    res: dict = {"task": task, "cap": cap, "oracle_files": oracle_files,
                 "arms_without_tests": [a for a in arms if not arm_blocks[a]]}
    if not graded_arms:
        log(f"{task}: no arm wrote tests — every arm scores 0, nothing to run")
        return res

    box = Box(row["image_name"])
    try:
        rc, out = box.sh("rm -rf /testbed/* && cp -r /root/my_repo/* /testbed/ && python -V && python -c 'import pytest_timeout; print(\"pytest-timeout ok\")'", 1800)
        log(f"{task}: reference restored — {' '.join(out.split()[-4:])}")
        box.put("/tmp/l3_helper.py", (HERE / "l3_helper.py").read_text())
        box.put("/tmp/mask.patch", row["patch"])

        _, out = box.sh(f"python /tmp/l3_helper.py sites /tmp/mask.patch {cap} > /tmp/mutants.json && cat /tmp/mutants.json", 1800)
        sites = json.loads(out.strip().splitlines()[-1])
        res["sites"] = {k: v for k, v in sites.items() if k != "mutants"}
        mutants = sites["mutants"]
        log(f"{task}: {len(mutants)} mutants ({sites['n_candidates']} candidates, {sites['n_invalid']} invalid)")

        rc, base_pass, base_fail = pytest(box, f2p)
        res["oracle_baseline"] = {"rc": rc, "passed": len(base_pass), "failed": len(base_fail)}
        log(f"{task}: oracle baseline rc={rc} passed={len(base_pass)} failed={len(base_fail)}")

        bad_files = []
        for rel in sorted({m["file"] for m in mutants}):
            box.sh(f"python /tmp/l3_helper.py identity {shlex.quote(rel)}")
            rc, p, _ = pytest(box, f2p)
            box.sh(f"python /tmp/l3_helper.py unidentity {shlex.quote(rel)}")
            if p != base_pass:
                bad_files.append(rel)
        res["identity_failed_files"] = bad_files
        mutants = [m for m in mutants if m["file"] not in bad_files]
        log(f"{task}: identity control dropped {len(bad_files)} file(s); {len(mutants)} mutants remain")

        for m in mutants:
            box.sh(f"python /tmp/l3_helper.py apply /tmp/mutants.json {m['id']}")
            rc, _, failed = pytest(box, f2p)
            box.sh(f"python /tmp/l3_helper.py revert /tmp/mutants.json {m['id']}")
            m["oracle_rc"] = rc
            m["oracle_killed_by"] = sorted(base_pass if rc == 2 else failed & base_pass)
            m["oracle_error"] = rc not in (0, 1, 2)
        killable = [m for m in mutants if m["oracle_killed_by"] and not m["oracle_error"]]
        res["mutants"] = mutants
        log(f"{task}: {len(killable)}/{len(mutants)} mutants killed by the hidden tests")

        order = sorted(base_pass)
        halves = {"A": set(order[0::2]), "B": set(order[1::2])}
        pos = {}
        for src, dst in (("A", "B"), ("B", "A")):
            k_src = [m for m in killable if set(m["oracle_killed_by"]) & halves[src]]
            hit = [m for m in k_src if set(m["oracle_killed_by"]) & halves[dst]]
            pos[f"{dst}_on_{src}"] = {"killed": len(hit), "of": len(k_src)}
        res["positive_control"] = pos

        box.sh("cd /testbed && rm -f " + " ".join(shlex.quote(f) for f in oracle_files))
        modules = sorted({m["file"][:-3].replace("/", ".") for m in killable})
        vac = "import importlib\n\n" + "\n".join(
            f"def test_import_{i}():\n    importlib.import_module({mod!r})\n" for i, mod in enumerate(modules))
        box.put("/testbed/test_l3_vacuous_control.py", vac)
        rc, vp, _ = pytest(box, ["test_l3_vacuous_control.py"])
        neg_killed = 0
        # An empty id list would make pytest run the whole repository.
        for m in killable if vp else []:
            box.sh(f"python /tmp/l3_helper.py apply /tmp/mutants.json {m['id']}")
            rc, _, _ = pytest(box, sorted(vp))
            box.sh(f"python /tmp/l3_helper.py revert /tmp/mutants.json {m['id']}")
            neg_killed += rc in (1, 2)
        box.sh("rm -f /testbed/test_l3_vacuous_control.py")
        res["negative_control"] = {"baseline_passed": len(vp), "killed": neg_killed, "of": len(killable)}
        log(f"{task}: negative control killed {neg_killed}/{len(killable)}; positive {pos}")

        res["arms"] = {}
        for arm in graded_arms:
            blocks = arm_blocks[arm]
            files = [re.match(r"diff --git a/(\S+)", b).group(1) for b in blocks]
            box.put("/tmp/arm.patch", "".join(blocks))
            rc, out = box.sh("cd /testbed && git apply --whitespace=nowarn /tmp/arm.patch && echo APPLIED", 300)
            if "APPLIED" not in out:
                res["arms"][arm] = {"error": f"test hunks did not apply: {out[-300:]}"}
                log(f"{task}: {arm} test hunks did not apply")
                continue
            box.put("/tmp/changed.json", json.dumps({f: sorted(changed_b_lines(b)) for f, b in zip(files, blocks)}))
            _, out = box.sh("python /tmp/l3_helper.py agent_tests /tmp/changed.json")
            agent_ids = json.loads(out.strip().splitlines()[-1])
            rc, a_pass, a_fail = pytest(box, agent_ids) if agent_ids else (None, set(), set())
            kills, errors = [], []
            for m in killable if a_pass else []:
                box.sh(f"python /tmp/l3_helper.py apply /tmp/mutants.json {m['id']}")
                rc_m, _, _ = pytest(box, sorted(a_pass))
                box.sh(f"python /tmp/l3_helper.py revert /tmp/mutants.json {m['id']}")
                (kills if rc_m in (1, 2) else errors if rc_m != 0 else []).append(m["id"])
            res["arms"][arm] = {"test_files": files, "agent_test_functions": len(agent_ids),
                                "pass_on_reference": len(a_pass), "fail_on_reference": sorted(a_fail),
                                "killed": len(kills), "errors": len(errors), "of": len(killable),
                                "killed_ids": kills}
            log(f"{task}: {arm} fns={len(agent_ids)} pass_on_ref={len(a_pass)} fail_on_ref={len(a_fail)} killed {len(kills)}/{len(killable)} errors={len(errors)}")
            steps = ["cd /testbed"]
            for f in files:
                q = shlex.quote(f)
                steps.append(f"rm -f {q}" if f in oracle_files
                             else f"(cp /root/my_repo/{q} {q} 2>/dev/null || rm -f {q})")
            rc, out = box.sh(" ; ".join(steps) + " ; git status --short 2>/dev/null | head -0 ; echo RESET")
            if "RESET" not in out:
                raise RuntimeError(f"could not reset {arm}'s test files: {out[-300:]}")
    finally:
        box.close()
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", action="append")
    ap.add_argument("--cap", type=int, default=200)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    tasks = args.task or [l.strip() for l in (HERE.parent.parent / "panel.txt").read_text().splitlines() if l.strip()]
    OUT.mkdir(exist_ok=True)
    for task in tasks:
        started = time.time()
        res = grade_task(task, args.cap, ARMS)
        res["wall_seconds"] = round(time.time() - started)
        (OUT / f"{task}{args.tag}.json").write_text(json.dumps(res, indent=1))
        log(f"{task}: done in {res['wall_seconds']}s")


if __name__ == "__main__":
    sys.exit(main())
