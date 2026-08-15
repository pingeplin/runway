#!/usr/bin/env python3
"""Stage 07 — mutation-score overlay on the AGENT-WRITTEN tests.

FeatureBench scores hidden fail-to-pass tests only; it cannot see the quality of
the tests the implementing agent wrote for itself. This stage measures exactly
that: per (task, arm) cell, reconstruct the container state the agent worked in,
apply the arm's `model_patch`, then run *only the agent's own test files*
against a handful of strategic mutations of the agent's own source changes.
Mutation kill rate = killed / applicable.

Everything that touches the repo runs INSIDE the task's docker image — the
dependencies (astropy, metaflow, …) live there and cannot be installed on the
host. Only the mutation *proposal* step runs on the host, via `claude -p`.

Container state reconstruction mirrors FeatureBench's own
`infer/runtime.py::_initialize_level1`, because `model_patch` is a diff against
that state and against nothing else:

  1. restore /testbed from /root/my_repo
  2. `git apply` the dataset's mask `patch` (warn-and-continue, as FB does)
  3. delete the FAIL_TO_PASS test files
  4. re-init git
  5. `git apply` the arm's `model_patch`   <- our addition

Usage:
    uv run --python 3.12 --with datasets python3 scripts/07_mutation.py --arm both
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from _common import (
    EVAL_ROOT,
    RESULTS_DIR,
    add_config_arg,
    die,
    load_config,
    load_split_rows,
    read_json,
    read_runs,
    write_json,
)

PROMPT_TEMPLATE = EVAL_ROOT / "prompts" / "mutations.md"
MUTATION_DIR = RESULTS_DIR / "mutation"
REPORT_PATH = RESULTS_DIR / "mutation_report.md"

TESTBED = "/testbed"
HELPER_PATH = "/tmp/fb_mutate.py"
MUTATIONS_PATH = "/tmp/fb_mutations.json"
MASK_PATCH_PATH = "/tmp/fb_mask.patch"
MODEL_PATCH_PATH = "/tmp/fb_model.patch"

# FeatureBench runs everything through the image's conda env.
CONDA_PRELUDE = "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && "
DEFAULT_TEST_CMD = "pytest -rA -p no:cacheprovider --color=no"
# featurebench/harness/test_parsers.py::MAP_REPO_TO_TEST_CMD
MAP_REPO_TO_TEST_CMD = {"pydantic/pydantic": "pytest -rA -v --color=no"}

DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)\s*$", re.MULTILINE)

# pytest exit codes: 0 pass, 1 tests failed, 2 interrupted, 3 internal error,
# 4 usage error, 5 no tests collected. 4/5 mean *we* mis-invoked pytest, so they
# are harness noise, never a kill and never a red baseline.
RC_NOT_SIGNAL = (4, 5)
# Docker.exec's own marker for "the host-side timeout fired".
RC_TIMEOUT = 124

STATUS_MEASURED = "measured"
STATUS_NO_AGENT_TESTS = "no_agent_tests"
STATUS_NO_SOURCE = "no_source_files"
STATUS_PATCH_FAILED = "patch_apply_failed"
STATUS_BASELINE_RED = "baseline_red"
STATUS_BASELINE_UNUSABLE = "baseline_unusable"
STATUS_NO_MUTATIONS = "no_mutations"
STATUS_TIMEOUT = "timeout_abandoned"
STATUS_ERROR = "error"

# Statuses that carry a kill rate, and those that count as a hard zero (the
# agent shipped no tests at all — that is the strongest possible signal, not a
# missing data point).
RATE_STATUSES = (STATUS_MEASURED,)
ZERO_STATUSES = (STATUS_NO_AGENT_TESTS,)


# Runs inside the container. Kept dependency-free (stdlib, py3.6+) because the
# image's python is whatever the repo pinned.
MUTATE_HELPER = r'''
import json, os, shutil, sys


def purge_bytecode(path):
    """Drop cached bytecode for `path`.

    CPython validates a .pyc against the source's (mtime, size) at *second*
    granularity. A boundary flip like `>= 90:` -> `>= 91:` keeps the size
    identical, so a mutation applied in the same second as the baseline import
    leaves the stale .pyc looking valid and the mutation silently invisible.
    """
    directory, name = os.path.split(path)
    stem = name[:-3] if name.endswith(".py") else name
    cache = os.path.join(directory, "__pycache__")
    if os.path.isdir(cache):
        for entry in os.listdir(cache):
            if entry.startswith(stem + ".") and entry.endswith((".pyc", ".pyo")):
                try:
                    os.remove(os.path.join(cache, entry))
                except OSError:
                    pass
    for legacy in (path + "c", path + "o"):
        if os.path.isfile(legacy):
            try:
                os.remove(legacy)
            except OSError:
                pass


def main(argv):
    root, mut_path, rest = "/testbed", "/tmp/fb_mutations.json", []
    i = 0
    while i < len(argv):
        if argv[i] == "--root":
            root = argv[i + 1]; i += 2
        elif argv[i] == "--mutations":
            mut_path = argv[i + 1]; i += 2
        else:
            rest.append(argv[i]); i += 1

    with open(mut_path) as f:
        muts = json.load(f)
    mode = rest[0] if rest else ""
    backup_dir = os.path.join(os.path.dirname(mut_path) or "/tmp", "fb_backups")

    if mode == "validate":
        out = []
        for idx, m in enumerate(muts):
            path = os.path.join(root, m["file"])
            if not os.path.isfile(path):
                out.append({"index": idx, "applicable": False, "reason": "file not found in container"})
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except Exception as exc:
                out.append({"index": idx, "applicable": False, "reason": "unreadable: %s" % exc})
                continue
            n = text.count(m["find"])
            if n == 0:
                out.append({"index": idx, "applicable": False, "reason": "find string absent"})
            elif n > 1:
                out.append({"index": idx, "applicable": False, "reason": "find string occurs %d times" % n})
            else:
                out.append({"index": idx, "applicable": True, "reason": None})
        print(json.dumps(out))
        return 0

    idx = int(rest[1])
    m = muts[idx]
    path = os.path.join(root, m["file"])
    backup = os.path.join(backup_dir, "%d.bak" % idx)

    if mode == "apply":
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(path, backup)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if text.count(m["find"]) != 1:
            sys.stderr.write("find string is no longer unique\n")
            return 2
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(m["find"], m["replace"], 1))
        os.utime(path, None)
        purge_bytecode(path)
        return 0

    if mode == "revert":
        if not os.path.isfile(backup):
            sys.stderr.write("no backup for index %d\n" % idx)
            return 2
        shutil.copyfile(backup, path)   # content only: mtime must move forward
        os.utime(path, None)
        purge_bytecode(path)
        os.remove(backup)
        return 0

    sys.stderr.write("unknown mode: %s\n" % mode)
    return 2


sys.exit(main(sys.argv[1:]))
'''


def log(msg: str) -> None:
    print(msg, flush=True)


def tail(text: str, n: int = 2000) -> str:
    text = (text or "").strip()
    return text[-n:]


# --------------------------------------------------------------- patch parsing

def patch_files(patch: str) -> list[str]:
    """b-side paths touched by a unified diff, minus deletions."""
    out: list[str] = []
    for chunk in split_patch(patch).values():
        m = DIFF_HEADER_RE.search(chunk)
        if not m:
            continue
        if re.search(r"^deleted file mode", chunk, re.MULTILINE):
            continue
        out.append(m.group(2))
    return out


def split_patch(patch: str) -> dict[str, str]:
    """Split a unified diff into {b-path: that file's chunk}, order preserved."""
    if not patch:
        return {}
    chunks: dict[str, str] = {}
    starts = [m.start() for m in DIFF_HEADER_RE.finditer(patch)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(patch)
        chunk = patch[start:end]
        m = DIFF_HEADER_RE.search(chunk)
        if m:
            chunks[m.group(2)] = chunk
    return chunks


def is_test_path(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    parts = Path(path).parts
    name = parts[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(p in ("test", "tests", "testing") for p in parts[:-1])


def classify(paths: list[str]) -> tuple[list[str], list[str]]:
    """(agent test files, mutable source files). Source is .py and non-test."""
    tests = [p for p in paths if is_test_path(p)]
    sources = [p for p in paths if p.endswith(".py") and not is_test_path(p)]
    return tests, sources


def source_diff(patch: str, sources: list[str]) -> str:
    chunks = split_patch(patch)
    return "\n".join(chunks[p] for p in sources if p in chunks)


# ------------------------------------------------------------------ repo config

def parse_repo_settings(row: dict[str, Any]) -> dict[str, Any]:
    settings = row.get("repo_settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError:
            settings = {}
    return settings if isinstance(settings, dict) else {}


def test_command(row: dict[str, Any]) -> str:
    """Mirror FeatureBench's runner choice, minus the per-test --timeout flag.

    FB appends `--timeout=<timeout_one>`, which needs pytest-timeout in the
    image; missing, pytest exits 4 (usage error) and every cell looks broken.
    We bound runtime with a host-side timeout on `docker exec` instead.
    """
    settings = parse_repo_settings(row)
    cmd = MAP_REPO_TO_TEST_CMD.get(row.get("repo", ""), settings.get("test_cmd") or DEFAULT_TEST_CMD)
    if settings.get("use_uv"):
        cmd = f"uv run {cmd}"
    return cmd


def fail_to_pass(row: dict[str, Any]) -> list[str]:
    f2p = row.get("FAIL_TO_PASS") or []
    if isinstance(f2p, str):
        try:
            parsed = json.loads(f2p)
            f2p = parsed if isinstance(parsed, list) else [f2p]
        except json.JSONDecodeError:
            f2p = [f2p]
    return [str(p) for p in f2p]


# ----------------------------------------------------------------------- docker

class Docker:
    """Thin CLI wrapper — one seam, so smoke tests can pass a mock binary."""

    def __init__(self, docker_cmd: str, exec_timeout: int) -> None:
        self.cmd = docker_cmd
        self.exec_timeout = exec_timeout

    def run(self, image: str) -> str:
        proc = subprocess.run(
            [self.cmd, "run", "-d", "--platform", "linux/amd64", "-w", TESTBED,
             image, "tail", "-f", "/dev/null"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {tail(proc.stderr or proc.stdout, 500)}")
        cid = proc.stdout.strip().splitlines()[-1].strip()
        if not cid:
            raise RuntimeError("docker run produced no container id")
        return cid

    def exec(self, cid: str, script: str, timeout: int | None = None) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                [self.cmd, "exec", cid, "bash", "-c", script],
                capture_output=True, text=True, timeout=timeout or self.exec_timeout,
            )
        except subprocess.TimeoutExpired:
            return 124, "timed out"
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def cp(self, cid: str, host_path: Path, dest: str) -> None:
        proc = subprocess.run(
            [self.cmd, "cp", str(host_path), f"{cid}:{dest}"],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker cp -> {dest} failed: {tail(proc.stderr or proc.stdout, 500)}")

    def rm(self, cid: str) -> None:
        subprocess.run([self.cmd, "rm", "-f", cid], capture_output=True, text=True, timeout=300)


def conda(script: str) -> str:
    return CONDA_PRELUDE + script


# ------------------------------------------------------------------------ claude

def run_claude(
    claude_cmd: str, prompt: str, model: str, claude_args: list[str], timeout_s: int,
) -> tuple[dict[str, Any], str | None]:
    """One headless claude pass. Mirrors 01_make_specs.run_claude."""
    argv = [claude_cmd, "-p", prompt, "--output-format", "json", *claude_args, "--model", model]
    try:
        proc = subprocess.run(argv, cwd=EVAL_ROOT, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {}, f"claude timed out after {timeout_s}s"
    except FileNotFoundError:
        return {}, f"claude command not found: {claude_cmd}"

    payload: dict[str, Any] = {"returncode": proc.returncode}
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return payload, f"claude stdout was not JSON (rc={proc.returncode}): {tail(proc.stderr or proc.stdout, 500)}"
    if isinstance(parsed, list):
        parsed = next((e for e in reversed(parsed) if isinstance(e, dict) and "result" in e), {})
    if not isinstance(parsed, dict):
        return payload, "claude JSON payload had an unexpected shape"
    payload.update(parsed)
    if proc.returncode != 0:
        return payload, f"claude exited {proc.returncode}"
    return payload, None


def extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """Pull the first well-formed JSON array out of a model reply."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [m for m in parsed if isinstance(m, dict)]
    return None


def sanitize_mutations(raw: list[dict[str, Any]], sources: list[str]) -> tuple[list[dict], list[dict]]:
    """Split proposals into (usable, rejected-with-reason) before touching docker."""
    good, bad = [], []
    for m in raw:
        rec = {
            "file": str(m.get("file", "")),
            "find": m.get("find"),
            "replace": m.get("replace"),
            "rationale": str(m.get("rationale", "")),
        }
        if not isinstance(rec["find"], str) or not isinstance(rec["replace"], str) or not rec["find"]:
            bad.append({**rec, "applicable": False, "skip_reason": "malformed find/replace"})
        elif rec["file"] not in sources:
            bad.append({**rec, "applicable": False, "skip_reason": "file is not a mutable source file of this patch"})
        elif rec["find"] == rec["replace"]:
            bad.append({**rec, "applicable": False, "skip_reason": "no-op mutation"})
        else:
            good.append(rec)
    return good, bad


# -------------------------------------------------------------------- one cell

def run_cell(
    arm: str,
    row: dict[str, Any],
    model_patch: str,
    args: argparse.Namespace,
    mut_cfg: dict[str, Any],
    template: str,
) -> dict[str, Any]:
    task_id = row["instance_id"]
    started = time.time()
    cell: dict[str, Any] = {
        "instance_id": task_id,
        "arm": arm,
        "image_name": row.get("image_name", ""),
        "status": STATUS_ERROR,
        "agent_test_files": [],
        "source_files": [],
        # Agent test files sitting on a deleted FAIL_TO_PASS path. Still
        # agent-authored (the file was removed before the agent ran), but the
        # coincidence is worth knowing when reading the cell.
        "agent_tests_on_f2p_path": [],
        "mask_patch_warning": None,
        "test_cmd": test_command(row),
        "baseline": None,
        "mutations": [],
        "n_proposed": 0,
        "n_applicable": 0,
        "n_killed": 0,
        "kill_rate": None,
        "claude": None,
        "error": None,
    }

    if not (model_patch or "").strip():
        cell.update(status=STATUS_PATCH_FAILED, error="prediction carried an empty model_patch")
        cell["wall_seconds"] = round(time.time() - started, 2)
        return cell

    touched = patch_files(model_patch)
    tests, sources = classify(touched)
    cell["agent_test_files"] = tests
    cell["source_files"] = sources
    f2p = fail_to_pass(row)
    f2p_rel = {p[len(TESTBED) + 1:] if p.startswith(TESTBED + "/") else p for p in f2p}
    cell["agent_tests_on_f2p_path"] = sorted(set(tests) & f2p_rel)

    # Cheap exits before paying for a container.
    if not tests:
        cell["status"] = STATUS_NO_AGENT_TESTS
        cell["wall_seconds"] = round(time.time() - started, 2)
        return cell
    if not sources:
        cell["status"] = STATUS_NO_SOURCE
        cell["wall_seconds"] = round(time.time() - started, 2)
        return cell

    docker = Docker(args.docker_cmd, int(mut_cfg.get("test_timeout_seconds", 1800)))
    cid = None
    tmpdir = Path(tempfile.mkdtemp(prefix="fb-mut-"))
    try:
        cid = docker.run(row.get("image_name", ""))

        # 1. restore /testbed from the pristine copy the image ships.
        rc, out = docker.exec(cid, conda(f"rm -rf {TESTBED}/* && cp -r /root/my_repo/* {TESTBED}/"), timeout=900)
        if rc != 0:
            cell.update(status=STATUS_ERROR, error=f"testbed restore failed (rc={rc}): {tail(out, 500)}")
            return cell

        # 2. mask patch — FeatureBench warns and continues on failure, so do we.
        mask = row.get("patch") or ""
        if mask.strip():
            mask_file = tmpdir / "mask.patch"
            mask_file.write_text(mask, encoding="utf-8")
            docker.cp(cid, mask_file, MASK_PATCH_PATH)
            rc, out = docker.exec(cid, f"cd {TESTBED} && git apply --whitespace=fix {MASK_PATCH_PATH}")
            if rc != 0:
                cell["mask_patch_warning"] = tail(out, 500)

        # 3. delete the hidden fail-to-pass test files.
        if f2p:
            rms = " ; ".join(
                f"rm -f {shlex.quote(p if p.startswith(TESTBED + '/') else f'{TESTBED}/{p}')}" for p in f2p
            )
            docker.exec(cid, rms)

        # 4. re-init git exactly as fb infer does.
        rc, out = docker.exec(cid, (
            f"cd {TESTBED} && rm -rf .git && git init -q && "
            'git config user.email "fb@bench.com" && git config user.name "FeatureBench" && '
            'git add -A && git commit -q -m "base" --allow-empty'
        ), timeout=900)
        if rc != 0:
            cell.update(status=STATUS_ERROR, error=f"git re-init failed (rc={rc}): {tail(out, 500)}")
            return cell

        # 5. apply the arm's model_patch.
        patch_file = tmpdir / "model.patch"
        patch_file.write_text(model_patch, encoding="utf-8")
        docker.cp(cid, patch_file, MODEL_PATCH_PATH)
        rc, out = docker.exec(cid, f"cd {TESTBED} && git apply --whitespace=fix {MODEL_PATCH_PATH}")
        if rc != 0:
            cell.update(status=STATUS_PATCH_FAILED, error=tail(out, 1000))
            return cell

        # Baseline: the agent's own tests must be green on the agent's own code.
        test_files = " ".join(shlex.quote(p) for p in tests)
        run_tests = conda(f"cd {TESTBED} && {cell['test_cmd']} {test_files}")
        rc, out = docker.exec(cid, run_tests)
        cell["baseline"] = {"rc": rc, "tail": tail(out)}
        if rc in RC_NOT_SIGNAL or rc not in (0, 1, 2, 3):
            cell["status"] = STATUS_BASELINE_UNUSABLE
            return cell
        if rc != 0:
            cell["status"] = STATUS_BASELINE_RED
            return cell

        # Propose mutations (host-side claude), then validate them in-container.
        prompt = (
            template.replace("{n_mutations}", str(int(mut_cfg.get("n_mutations", 6))))
            .replace("{instance_id}", task_id)
            .replace("{source_files}", "\n".join(f"- {p}" for p in sources))
            .replace("{source_diff}", source_diff(model_patch, sources))
        )
        payload, err = run_claude(
            claude_cmd=args.claude_cmd,
            prompt=prompt,
            model=mut_cfg.get("model", "claude-sonnet-4-5"),
            claude_args=list(mut_cfg.get("claude_args", [])),
            timeout_s=int(mut_cfg.get("timeout_seconds", 600)),
        )
        cell["claude"] = {
            "cost_usd": payload.get("total_cost_usd"),
            "duration_ms": payload.get("duration_ms"),
            "num_turns": payload.get("num_turns"),
            "returncode": payload.get("returncode"),
            "error": err,
        }
        if err:
            cell.update(status=STATUS_NO_MUTATIONS, error=err)
            return cell
        raw = extract_json_array(payload.get("result") or "")
        if not raw:
            cell.update(status=STATUS_NO_MUTATIONS, error="claude reply contained no JSON array of mutations")
            return cell
        cell["n_proposed"] = len(raw)

        usable, rejected = sanitize_mutations(raw, sources)
        cell["mutations"] = list(rejected)
        if not usable:
            cell.update(status=STATUS_NO_MUTATIONS, error="no proposal survived static validation")
            return cell

        helper = tmpdir / "fb_mutate.py"
        helper.write_text(MUTATE_HELPER, encoding="utf-8")
        docker.cp(cid, helper, HELPER_PATH)
        muts_file = tmpdir / "mutations.json"
        muts_file.write_text(json.dumps(usable), encoding="utf-8")
        docker.cp(cid, muts_file, MUTATIONS_PATH)

        helper_argv = f"python3 {HELPER_PATH} --root {TESTBED} --mutations {MUTATIONS_PATH}"
        rc, out = docker.exec(cid, conda(f"{helper_argv} validate"), timeout=300)
        verdicts = extract_json_array(out) or []
        by_index = {int(v["index"]): v for v in verdicts if "index" in v}
        if not by_index:
            cell.update(status=STATUS_NO_MUTATIONS, error=f"mutation validation produced no verdicts: {tail(out, 500)}")
            return cell

        killed = 0
        applicable = 0
        for idx, mut in enumerate(usable):
            verdict = by_index.get(idx, {"applicable": False, "reason": "no verdict"})
            rec = dict(mut)
            if not verdict.get("applicable"):
                rec.update(applicable=False, skip_reason=verdict.get("reason") or "not applicable")
                cell["mutations"].append(rec)
                log(f"      mutation {idx}: skipped — {rec['skip_reason']}")
                continue
            applicable += 1
            rc, out = docker.exec(cid, conda(f"{helper_argv} apply {idx}"), timeout=300)
            if rc != 0:
                rec.update(applicable=False, skip_reason=f"apply failed: {tail(out, 300)}")
                cell["mutations"].append(rec)
                applicable -= 1
                continue
            try:
                rc, out = docker.exec(cid, run_tests)
            finally:
                docker.exec(cid, conda(f"{helper_argv} revert {idx}"), timeout=300)
            # rc 4/5 mean we mis-invoked pytest, not that the mutation survived.
            is_killed = rc not in (0, *RC_NOT_SIGNAL)
            if rc == RC_TIMEOUT:
                # The host-side timeout killed `docker exec`, not the pytest
                # inside the container. That process is still running against
                # the same filesystem, so every later mutation in this cell
                # would race it. Abandon the cell rather than report noise.
                rec.update(applicable=False, killed=None, rc=rc,
                           skip_reason="test run timed out; cell abandoned (in-container pytest may still be live)")
                cell["mutations"].append(rec)
                applicable -= 1
                cell.update(n_applicable=applicable, n_killed=killed, kill_rate=None,
                            status=STATUS_TIMEOUT, error=f"mutation {idx} timed out")
                log(f"      mutation {idx}: TIMEOUT — abandoning cell")
                return cell
            if rc in RC_NOT_SIGNAL:
                rec.update(applicable=False, killed=None, rc=rc,
                           skip_reason=f"pytest exited {rc} (harness noise, not a verdict)")
                applicable -= 1
            else:
                rec.update(applicable=True, skip_reason=None, rc=rc, killed=is_killed, tail=tail(out, 800))
                killed += int(is_killed)
            cell["mutations"].append(rec)
            log(f"      mutation {idx}: {'KILLED' if is_killed else 'survived'} (rc={rc})")

        cell["n_applicable"] = applicable
        cell["n_killed"] = killed
        cell["kill_rate"] = round(killed / applicable, 4) if applicable else None
        cell["status"] = STATUS_MEASURED if applicable else STATUS_NO_MUTATIONS
        return cell
    except Exception as exc:  # container/CLI failures must not abort the panel
        cell.update(status=STATUS_ERROR, error=f"{type(exc).__name__}: {exc}")
        return cell
    finally:
        if cid:
            docker.rm(cid)
        shutil.rmtree(tmpdir, ignore_errors=True)
        cell["wall_seconds"] = round(time.time() - started, 2)


# ------------------------------------------------------------------------ report

def summarize(cells: list[dict[str, Any]]) -> dict[str, Any]:
    census = {
        "cells": len(cells),
        STATUS_MEASURED: 0,
        STATUS_NO_AGENT_TESTS: 0,
        STATUS_NO_SOURCE: 0,
        STATUS_PATCH_FAILED: 0,
        STATUS_BASELINE_RED: 0,
        STATUS_BASELINE_UNUSABLE: 0,
        STATUS_NO_MUTATIONS: 0,
        STATUS_TIMEOUT: 0,
        STATUS_ERROR: 0,
    }
    for c in cells:
        census[c["status"]] = census.get(c["status"], 0) + 1

    rated = [c["kill_rate"] for c in cells if c["status"] in RATE_STATUSES and c["kill_rate"] is not None]
    zeros = [0.0 for c in cells if c["status"] in ZERO_STATUSES]
    mean_measured = round(sum(rated) / len(rated), 4) if rated else None
    pool = rated + zeros
    mean_with_zeros = round(sum(pool) / len(pool), 4) if pool else None
    return {
        "census": census,
        "n_measured": len(rated),
        "n_zero": len(zeros),
        "mean_kill_rate_measured": mean_measured,
        "mean_kill_rate_with_zeros": mean_with_zeros,
        "total_applicable": sum(c["n_applicable"] for c in cells),
        "total_killed": sum(c["n_killed"] for c in cells),
    }


def fmt_rate(cell: dict[str, Any]) -> str:
    if cell["status"] == STATUS_MEASURED and cell["kill_rate"] is not None:
        return f"{cell['kill_rate']:.2f} ({cell['n_killed']}/{cell['n_applicable']})"
    return f"— ({cell['status']})"


def write_report(by_arm: dict[str, list[dict[str, Any]]], out_path: Path) -> str:
    arms = sorted(by_arm)
    task_ids: list[str] = []
    for arm in arms:
        for c in by_arm[arm]:
            if c["instance_id"] not in task_ids:
                task_ids.append(c["instance_id"])
    task_ids.sort()
    index = {(arm, c["instance_id"]): c for arm in arms for c in by_arm[arm]}

    lines = [
        "# Mutation-score overlay — agent-written tests",
        "",
        "Per (task, arm): the arm's `model_patch` is applied inside the task's own",
        "docker image, then **only the test files the agent itself wrote** are run",
        "against strategic mutations of the agent's own source changes.",
        "Kill rate = killed / applicable mutations. This is the test-quality",
        "dimension FeatureBench's hidden fail-to-pass tests cannot see.",
        "",
        "## Per-task kill rate",
        "",
        "| task | " + " | ".join(f"arm {a}" for a in arms) + " |",
        "|---|" + "---|" * len(arms),
    ]
    for tid in task_ids:
        cells = [index.get((a, tid)) for a in arms]
        rendered = [fmt_rate(c) if c else "—" for c in cells]
        lines.append(f"| `{tid}` | " + " | ".join(rendered) + " |")

    lines += ["", "## Arm summary", "",
              "| arm | cells | measured | no_agent_tests | baseline_red | patch_failed | other | "
              "mean kill rate (measured) | mean kill rate (no-tests = 0) |",
              "|---|---|---|---|---|---|---|---|---|"]
    summaries = {}
    for arm in arms:
        s = summarize(by_arm[arm])
        summaries[arm] = s
        cen = s["census"]
        other = cen["cells"] - (cen[STATUS_MEASURED] + cen[STATUS_NO_AGENT_TESTS]
                                + cen[STATUS_BASELINE_RED] + cen[STATUS_PATCH_FAILED])
        m = s["mean_kill_rate_measured"]
        z = s["mean_kill_rate_with_zeros"]
        lines.append(
            f"| **{arm}** | {cen['cells']} | {cen[STATUS_MEASURED]} | {cen[STATUS_NO_AGENT_TESTS]} | "
            f"{cen[STATUS_BASELINE_RED]} | {cen[STATUS_PATCH_FAILED]} | {other} | "
            f"{'—' if m is None else f'**{m:.4f}**'} | {'—' if z is None else f'**{z:.4f}**'} |"
        )

    lines += ["", "Two denominators, deliberately:", "",
              "- **measured** — mean over cells that produced a rate. Flatters an arm",
              "  that wrote no tests at all, because those cells simply vanish.",
              "- **no-tests = 0** — the same mean with every `no_agent_tests` cell",
              "  scored 0.0. Shipping no tests is the worst possible test quality,",
              "  not missing data. Read this column first.",
              "", "Cells that failed for harness reasons (`patch_apply_failed`,",
              "`baseline_unusable`, `no_mutations`, `timeout_abandoned`, `error`)",
              "are excluded from both",
              "means and shown in the census instead. `baseline_red` — the agent's own",
              "tests fail against the agent's own code — is also excluded from the",
              "means but is itself a quality signal worth reading.", ""]

    overlaps = [
        (arm, c["instance_id"], c["agent_tests_on_f2p_path"])
        for arm in arms for c in by_arm[arm] if c.get("agent_tests_on_f2p_path")
    ]
    if overlaps:
        lines += ["## Agent tests on a fail-to-pass path", "",
                  "These cells wrote a test file at a path FeatureBench had deleted as",
                  "part of the hidden oracle. The test is still agent-authored — the",
                  "file was gone before the agent started — but the path coincidence",
                  "means the agent inferred the oracle's own layout.", ""]
        for arm, tid, paths in overlaps:
            lines.append(f"- arm **{arm}** · `{tid}` — {', '.join(f'`{p}`' for p in paths)}")
        lines.append("")

    lines += ["## Caveats", "",
              f"- **Small N.** {len(task_ids)} task(s) × {len(arms)} arm(s), one seed, "
              "≤6 mutations per cell. Directional, not a verdict.",
              "- **LLM-chosen mutations.** Sites are proposed by a model per cell, so",
              "  the mutation panels differ between arms and between tasks. This",
              "  measures 'did these tests catch plausible breakage', not a stable",
              "  mutation-adequacy score comparable across runs.",
              "- **Agent-tests-only scope.** Only test files the patch added or",
              "  modified are run. Pre-existing repo tests and the hidden",
              "  fail-to-pass tests are deliberately excluded — they are FeatureBench's",
              "  job, not this overlay's.",
              "- **Overlap with the oracle.** An agent test may land on the same path",
              "  as a deleted fail-to-pass file. It is still agent-authored (the file",
              "  was removed before the agent ran), but the path coincidence is worth",
              "  knowing when reading a cell.",
              "- **Survived ≠ untested.** A mutation can survive because it is",
              "  semantically equivalent, not because the tests are vacuous. Read the",
              "  per-cell JSON under `results/mutation/<arm>/<id>.json` before drawing",
              "  a conclusion from a single survivor.", ""]

    text = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text


# -------------------------------------------------------------------------- main

def read_predictions(path: Path) -> dict[str, str]:
    preds: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            iid = row.get("instance_id")
            if iid:
                preds[iid] = row.get("model_patch") or ""
    return preds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--arm", default="both", help="Arm key from runs.json, or 'both' for all of them")
    parser.add_argument("--task-id", action="append", default=None, help="Restrict to these instance_ids (repeatable)")
    parser.add_argument("--force", action="store_true", help="Recompute cells that already have a results/mutation JSON")
    parser.add_argument("--dry-run", action="store_true", help="List the cells that would run, execute nothing")
    parser.add_argument("--claude-cmd", default="claude", help="Path to the claude binary (for smoke tests)")
    parser.add_argument("--docker-cmd", default="docker", help="Path to the docker binary (for smoke tests)")
    parser.add_argument("--mock-dataset", default=None, help="Read dataset rows from this JSONL instead of HuggingFace")
    parser.add_argument("--runs", default=None, help="Path to runs.json (default: results/runs.json)")
    parser.add_argument("--out", default=None, help="Path for the markdown report")
    args = parser.parse_args()

    cfg = load_config(args.config)
    eval_cfg = cfg.get("eval", {})
    mut_cfg = cfg.get("mutation", {})

    if not PROMPT_TEMPLATE.exists():
        die(f"prompt template missing: {PROMPT_TEMPLATE}")
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")

    runs = read_json(Path(args.runs)) if args.runs else read_runs()
    if not runs:
        die("results/runs.json not found or empty — run stages 03/04 first")
    arms = sorted(runs) if args.arm == "both" else [args.arm]
    unknown = [a for a in arms if a not in runs]
    if unknown:
        die(f"arm(s) not present in runs.json ({', '.join(sorted(runs))}): {', '.join(unknown)}")

    split = runs[arms[0]].get("split") or eval_cfg.get("split", "lite")
    rows = load_split_rows(eval_cfg.get("dataset", ""), split, args.mock_dataset)
    by_id = {r["instance_id"]: r for r in rows}

    out_path = Path(args.out).expanduser() if args.out else REPORT_PATH
    by_arm: dict[str, list[dict[str, Any]]] = {}

    for arm in arms:
        run = runs[arm]
        jsonl = run.get("output_jsonl")
        if not jsonl or not Path(jsonl).exists():
            die(f"arm {arm}: output_jsonl missing ({jsonl})")
        preds = read_predictions(Path(jsonl))
        task_ids = sorted(preds)
        if args.task_id:
            task_ids = [t for t in task_ids if t in set(args.task_id)]
        cells: list[dict[str, Any]] = []
        log(f"\nstage 07 arm {arm}: {len(task_ids)} cell(s) from {jsonl}")

        for i, tid in enumerate(task_ids, 1):
            cell_path = MUTATION_DIR / arm / f"{tid}.json"
            if not args.force and cell_path.exists():
                try:
                    cells.append(read_json(cell_path))
                    log(f"  [{i}/{len(task_ids)}] {tid}: cached, skipping")
                    continue
                except (OSError, json.JSONDecodeError):
                    pass
            row = by_id.get(tid)
            if row is None:
                log(f"  [{i}/{len(task_ids)}] {tid}: not in split '{split}', skipping")
                continue
            if args.dry_run:
                touched = patch_files(preds[tid])
                tests, sources = classify(touched)
                log(f"  [{i}/{len(task_ids)}] {tid}: image={row.get('image_name','')} "
                    f"tests={tests or '[]'} sources={sources or '[]'} -> {cell_path}")
                continue

            log(f"  [{i}/{len(task_ids)}] {tid}: container + patch + baseline + mutations")
            cell = run_cell(arm, row, preds[tid], args, mut_cfg, template)
            write_json(cell_path, cell)
            cells.append(cell)
            log(f"  [{i}/{len(task_ids)}] {tid}: {cell['status']} {fmt_rate(cell)} ({cell['wall_seconds']}s)")

        by_arm[arm] = cells

    if args.dry_run:
        log("\n(dry run — nothing executed, no report written)")
        return 0

    write_report(by_arm, out_path)
    log(f"\nstage 07 done -> {out_path}")
    for arm in arms:
        s = summarize(by_arm[arm])
        log(f"  arm {arm}: measured={s['n_measured']} no_agent_tests={s['n_zero']} "
            f"mean(measured)={s['mean_kill_rate_measured']} mean(no-tests=0)={s['mean_kill_rate_with_zeros']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
