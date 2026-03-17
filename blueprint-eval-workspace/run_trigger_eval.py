#!/usr/bin/env python3
"""Trigger eval using claude -p CLI — simulates real session with all skills visible."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def load_skill_descriptions(plugin_path: Path) -> dict[str, str]:
    """Load name + description from all skills and commands."""
    skills = {}

    for skill_dir in sorted((plugin_path / "skills").iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        content = skill_file.read_text()
        name = desc = None
        in_fm = False
        for line in content.split("\n"):
            if line.strip() == "---":
                if in_fm:
                    break
                in_fm = True
                continue
            if in_fm:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
        if name and desc:
            skills[f"blueprint:{name}"] = desc

    commands_dir = plugin_path / "commands"
    if commands_dir.exists():
        for cmd_file in sorted(commands_dir.glob("*.md")):
            content = cmd_file.read_text()
            name = desc = None
            in_fm = False
            for line in content.split("\n"):
                if line.strip() == "---":
                    if in_fm:
                        break
                    in_fm = True
                    continue
                if in_fm:
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
            if name and desc:
                skills[f"blueprint:{name}"] = desc

    return skills


def build_prompt(skills: dict[str, str], query: str) -> str:
    """Build prompt that simulates Claude Code's skill triggering decision."""
    skill_list = "\n".join(f"- {name}: {desc}" for name, desc in skills.items())
    return f"""You are simulating Claude Code's skill triggering system. You have these available skills:

{skill_list}

A user sends this message:
"{query}"

TASK: Decide if any skill should be invoked for this query.

Rules:
- Only invoke a skill if the user's request clearly matches its purpose
- If the user could benefit from a skill's specialized workflow, invoke it
- If the request is simple enough to handle directly (like running a shell command), don't invoke a skill
- If multiple skills could match, pick the BEST one

Respond with EXACTLY one line in this format:
INVOKE: <skill-name>
or
NO_SKILL

Examples:
INVOKE: blueprint:spec
INVOKE: blueprint:run
NO_SKILL

Your answer:"""


def test_query(
    skills: dict[str, str],
    query: str,
    target_skill: str,
    timeout: int,
    model: str | None,
) -> dict:
    """Test a single query via claude -p."""
    prompt = build_prompt(skills, query)
    cmd = ["claude", "-p", prompt, "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
        output = result.stdout.strip()

        triggered_skill = None
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("INVOKE:"):
                triggered_skill = line.split(":", 1)[1].strip()
                # Handle "INVOKE: blueprint:spec" format
                if ":" not in triggered_skill:
                    triggered_skill = f"blueprint:{triggered_skill}"
                break
            if line == "NO_SKILL":
                break

        return {
            "query": query,
            "target_skill": target_skill,
            "triggered_skill": triggered_skill,
            "raw_output": output[:200],
        }
    except subprocess.TimeoutExpired:
        return {
            "query": query,
            "target_skill": target_skill,
            "triggered_skill": None,
            "raw_output": "TIMEOUT",
        }
    except Exception as e:
        return {
            "query": query,
            "target_skill": target_skill,
            "triggered_skill": None,
            "raw_output": f"ERROR: {e}",
        }


def run_eval(
    plugin_path: Path,
    eval_file: Path,
    model: str | None = None,
    workers: int = 8,
    runs_per_query: int = 1,
    timeout: int = 30,
) -> dict:
    """Run the full eval suite."""
    skills = load_skill_descriptions(plugin_path)

    print(f"Loaded {len(skills)} skills:", file=sys.stderr)
    for name in skills:
        print(f"  - {name}", file=sys.stderr)

    evals = json.loads(eval_file.read_text())

    queries = []
    if isinstance(evals, dict) and "skills" in evals:
        for skill_group in evals["skills"]:
            skill_name = skill_group["skill_name"]
            for item in skill_group["evals"]:
                queries.append({
                    "query": item["query"],
                    "target_skill": skill_name,
                    "should_trigger": item["should_trigger"],
                })
    elif isinstance(evals, list):
        for item in evals:
            queries.append(item)

    results = []
    total_queries = len(queries) * runs_per_query
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_info = {}
        for q in queries:
            for _ in range(runs_per_query):
                future = executor.submit(
                    test_query,
                    skills,
                    q["query"],
                    q.get("target_skill", "unknown"),
                    timeout,
                    model,
                )
                future_to_info[future] = q

        query_runs: dict[str, list[dict]] = {}
        for future in as_completed(future_to_info):
            q = future_to_info[future]
            key = q["query"]
            completed += 1
            try:
                r = future.result()
                query_runs.setdefault(key, []).append(r)
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
            if completed % 10 == 0:
                print(f"  [{completed}/{total_queries}]", file=sys.stderr)

    for q in queries:
        key = q["query"]
        runs = query_runs.get(key, [])
        target = q.get("target_skill", "unknown")
        should = q["should_trigger"]

        triggered_skills = [r["triggered_skill"] for r in runs if r["triggered_skill"]]
        correct_count = sum(1 for s in triggered_skills if s == target)
        correct_rate = correct_count / len(runs) if runs else 0

        if should:
            did_pass = correct_rate >= 0.5
        else:
            wrong_triggers = sum(1 for s in triggered_skills if s == target)
            did_pass = wrong_triggers == 0

        results.append({
            "query": key,
            "target_skill": target,
            "should_trigger": should,
            "triggered_skills": triggered_skills,
            "correct_rate": correct_rate,
            "runs": len(runs),
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    by_skill = {}
    for r in results:
        by_skill.setdefault(r["target_skill"], []).append(r)

    skill_summaries = {}
    for skill, srs in sorted(by_skill.items()):
        s_passed = sum(1 for r in srs if r["pass"])
        s_total = len(srs)
        st_hits = sum(1 for r in srs if r["should_trigger"] and r["pass"])
        st_total = sum(1 for r in srs if r["should_trigger"])
        fps = sum(1 for r in srs if not r["should_trigger"] and not r["pass"])
        skill_summaries[skill] = {
            "passed": s_passed,
            "total": s_total,
            "accuracy": round(s_passed / s_total * 100, 1) if s_total else 0,
            "should_trigger_hits": f"{st_hits}/{st_total}",
            "false_positives": fps,
        }

    output = {
        "model": model or "default",
        "runs_per_query": runs_per_query,
        "results": results,
        "summary": {"total": total, "passed": passed, "accuracy": round(passed / total * 100, 1)},
        "by_skill": skill_summaries,
    }

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Overall: {passed}/{total} ({output['summary']['accuracy']}%)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    for skill, s in skill_summaries.items():
        print(
            f"  {skill:25s} {s['passed']}/{s['total']} ({s['accuracy']}%) "
            f"triggers={s['should_trigger_hits']} fp={s['false_positives']}",
            file=sys.stderr,
        )
    print(f"{'='*60}", file=sys.stderr)
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        triggered = r["triggered_skills"][0] if r["triggered_skills"] else "none"
        expected = r["target_skill"] if r["should_trigger"] else f"NOT {r['target_skill']}"
        print(
            f"  [{status}] expected={expected:30s} got={triggered:25s} {r['query'][:55]}",
            file=sys.stderr,
        )

    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-path", required=True)
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--runs-per-query", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    output = run_eval(
        plugin_path=Path(args.plugin_path),
        eval_file=Path(args.eval_set),
        model=args.model,
        workers=args.workers,
        runs_per_query=args.runs_per_query,
        timeout=args.timeout,
    )

    json_out = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(json_out)
        print(f"\nWritten to {args.output}", file=sys.stderr)
    else:
        print(json_out)
