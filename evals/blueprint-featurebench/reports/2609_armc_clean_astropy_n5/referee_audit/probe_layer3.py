"""Layer-3 feasibility: do an arm's added tests run against the unmasked reference?

Restores /testbed from /root/my_repo (the reference, no mask), applies only the
arm's test-file hunks, and runs only the test functions the arm added.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / "results"
RUNS = json.loads((RUN / "runs.json").read_text())
PRELUDE = "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && "


def sh(argv, timeout=900, stdin=None):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=stdin)
    return p.returncode, (p.stdout + p.stderr)


def main(task: str, arm: str) -> None:
    row = next(json.loads(l) for l in open(RUN / "dataset_arm_b/data/fast.jsonl") if json.loads(l)["instance_id"] == task)
    patch = next(json.loads(l)["model_patch"] for l in open(RUNS[arm]["output_jsonl"]) if json.loads(l)["instance_id"] == task)
    hunks = re.findall(r"^diff --git a/(\S+) .*?(?=^diff --git |\Z)", patch, re.S | re.M)
    blocks = re.split(r"(?=^diff --git )", patch, flags=re.M)
    test_blocks = [b for b in blocks if re.match(r"diff --git a/\S*tests?/\S+\.py", b)]
    added = sorted(set(re.findall(r"^\+\s*def (test_\w+)", "".join(test_blocks), re.M)))
    files = [re.match(r"diff --git a/(\S+)", b).group(1) for b in test_blocks]
    print(f"{arm} {task.split('.')[2]}: {len(test_blocks)} test file(s), {len(added)} added test fns: {files}")
    if not added:
        return
    rc, cid = sh(["docker", "run", "-d", "--platform", "linux/amd64", "-w", "/testbed", row["image_name"], "tail", "-f", "/dev/null"], 600)
    cid = cid.strip().splitlines()[-1]
    try:
        rc, out = sh(["docker", "exec", cid, "bash", "-c", PRELUDE + "rm -rf /testbed/* && cp -r /root/my_repo/* /testbed/ && cd /testbed && git status --short | head -3; echo restored"], 900)
        print("restore:", out.strip().splitlines()[-1])
        f2p = row["FAIL_TO_PASS"]
        f2p = json.loads(f2p) if isinstance(f2p, str) else f2p
        oracle_files = sorted({t.split("::")[0] for t in f2p})
        # Mirror fb's _initialize_level1 step 3: the oracle test files are gone in
        # every state an agent ever saw, so an arm may have created its own file
        # at that path. The source stays unmasked — that is the point.
        rc, out = sh(["docker", "exec", cid, "bash", "-c", "cd /testbed && rm -f " + " ".join(oracle_files) + " && echo removed"], 120)
        print("oracle test files removed:", oracle_files)
        rc, out = sh(["docker", "exec", "-i", cid, "bash", "-c", "cd /testbed && cat > /tmp/tests.patch && git apply --check /tmp/tests.patch && git apply /tmp/tests.patch && echo APPLIED || (git apply --3way /tmp/tests.patch && echo APPLIED_3WAY)"], 300, "".join(test_blocks))
        print("apply:", out.strip()[-300:])
        k = " or ".join(added)
        rc, out = sh(["docker", "exec", cid, "bash", "-c", PRELUDE + f"cd /testbed && pytest -p no:cacheprovider --color=no -q {' '.join(files)} -k '{k}' 2>&1 | tail -25"], 900)
        print(f"pytest rc={rc}\n{out.strip()}")
    finally:
        sh(["docker", "rm", "-f", cid], 120)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
