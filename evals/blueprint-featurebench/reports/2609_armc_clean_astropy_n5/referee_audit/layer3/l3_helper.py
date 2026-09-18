"""In-container helper for the layer-3 grader. Stdlib only.

  sites  <mask.patch> <max>          enumerate deterministic AST mutants inside the mask region
  apply  <mutants.json> <id>         write mutant <id> over its file (original kept as .l3orig)
  revert <mutants.json> <id>         restore that file
  identity <file>                    rewrite <file> as ast.unparse of itself (original kept)
  unidentity <file>                  restore it
  agent_tests <changed.json>         node ids of test functions whose span touches changed lines
"""

import ast
import copy
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path("/testbed")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

CMP_SWAP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt,
            ast.Gt: ast.LtE, ast.LtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
            ast.In: ast.NotIn, ast.NotIn: ast.In}
BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}


def removed_lines(mask: str) -> dict[str, set[int]]:
    """Reference-side line numbers the mask deletes, per non-test source file."""
    out: dict[str, set[int]] = {}
    current, a = None, 0
    for line in mask.splitlines():
        if line.startswith("--- "):
            path = line[4:].strip()
            current = path[2:] if path.startswith("a/") else None
            if current and ("/tests/" in current or not current.endswith(".py")):
                current = None
            continue
        if line.startswith("+++ "):
            continue
        m = HUNK.match(line)
        if m:
            a = int(m.group(1))
            continue
        if current is None:
            continue
        if line.startswith("-"):
            out.setdefault(current, set()).add(a)
            a += 1
        elif line.startswith("+"):
            pass
        else:
            a += 1
    return out


def candidates(tree: ast.AST, lines: set[int]):
    """Yield (path, op_name) for every mutable node on a masked line, in walk order."""
    for idx, node in enumerate(ast.walk(tree)):
        ln = getattr(node, "lineno", None)
        if ln is None or ln not in lines:
            continue
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in CMP_SWAP:
                    yield idx, f"cmp{k}:{type(op).__name__}->{CMP_SWAP[type(op)].__name__}"
        elif isinstance(node, ast.BoolOp):
            yield idx, f"bool:{type(node.op).__name__}"
        elif isinstance(node, ast.BinOp) and type(node.op) in BIN_SWAP:
            yield idx, f"bin:{type(node.op).__name__}->{BIN_SWAP[type(node.op)].__name__}"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield idx, "not:drop"
        elif isinstance(node, ast.Constant) and type(node.value) is bool:
            yield idx, f"const:{node.value}->{not node.value}"
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            yield idx, f"const:{node.value}->{node.value + 1}"
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            yield idx, "return:None"


def mutate(tree: ast.AST, idx: int, op: str) -> ast.AST:
    tree = copy.deepcopy(tree)
    nodes = list(ast.walk(tree))
    node = nodes[idx]
    if op.startswith("cmp"):
        k = int(op[3:op.index(":")])
        node.ops[k] = CMP_SWAP[type(node.ops[k])]()
    elif op.startswith("bool"):
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif op.startswith("bin"):
        node.op = BIN_SWAP[type(node.op)]()
    elif op == "not:drop":
        for parent in nodes:
            for field, value in ast.iter_fields(parent):
                if value is node:
                    setattr(parent, field, node.operand)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if item is node:
                            value[i] = node.operand
    elif op.startswith("const"):
        node.value = (not node.value) if type(node.value) is bool else node.value + 1
    elif op == "return:None":
        node.value = ast.Constant(value=None)
    return ast.fix_missing_locations(tree)


def cmd_sites(mask_path: str, cap: str) -> None:
    mask = Path(mask_path).read_text()
    trees, raw = {}, []
    for rel, lines in sorted(removed_lines(mask).items()):
        path = ROOT / rel
        if not path.exists():
            continue
        try:
            trees[rel] = ast.parse(path.read_text())
        except SyntaxError:
            continue
        nodes = list(ast.walk(trees[rel]))
        for idx, op in candidates(trees[rel], lines):
            raw.append({"file": rel, "node": idx, "op": op,
                        "line": nodes[idx].lineno, "col": nodes[idx].col_offset})
    raw.sort(key=lambda m: (m["file"], m["line"], m["col"], m["op"]))
    cap_n = int(cap)
    sampled = raw if len(raw) <= cap_n else [raw[int(i * len(raw) / cap_n)] for i in range(cap_n)]
    found, invalid = [], 0
    for m in sampled:
        try:
            compile(ast.unparse(mutate(trees[m["file"]], m["node"], m["op"])), m["file"], "exec")
        except Exception:
            invalid += 1
            continue
        found.append(m)
    for i, m in enumerate(found):
        m["id"] = i
    print(json.dumps({"n_masked_files": len(trees), "n_candidates": len(raw),
                      "n_invalid": invalid, "mutants": found}))


def backup(path: Path) -> None:
    orig = path.with_suffix(path.suffix + ".l3orig")
    if not orig.exists():
        shutil.copy2(path, orig)


def restore(path: Path) -> None:
    orig = path.with_suffix(path.suffix + ".l3orig")
    if orig.exists():
        shutil.move(orig, path)


def cmd_apply(mutants_path: str, mid: str) -> None:
    m = json.loads(Path(mutants_path).read_text())["mutants"][int(mid)]
    path = ROOT / m["file"]
    backup(path)
    tree = ast.parse(path.with_suffix(path.suffix + ".l3orig").read_text())
    path.write_text(ast.unparse(mutate(tree, m["node"], m["op"])))
    for pyc in path.parent.glob(f"__pycache__/{path.stem}.*.pyc"):
        pyc.unlink()


def cmd_revert(mutants_path: str, mid: str) -> None:
    m = json.loads(Path(mutants_path).read_text())["mutants"][int(mid)]
    restore(ROOT / m["file"])


def cmd_identity(rel: str) -> None:
    path = ROOT / rel
    backup(path)
    path.write_text(ast.unparse(ast.parse(path.with_suffix(path.suffix + ".l3orig").read_text())))


def cmd_unidentity(rel: str) -> None:
    restore(ROOT / rel)


def cmd_agent_tests(changed_path: str) -> None:
    changed = json.loads(Path(changed_path).read_text())
    ids = []
    for rel, lines in changed.items():
        path = ROOT / rel
        if not path.exists():
            continue
        lines = set(lines)
        tree = ast.parse(path.read_text())

        def span(n):
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            return set(range(start, n.end_lineno + 1))

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                if span(node) & lines:
                    ids.append(f"{rel}::{node.name}")
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test"):
                        if span(sub) & lines:
                            ids.append(f"{rel}::{node.name}::{sub.name}")
    print(json.dumps(ids))


if __name__ == "__main__":
    {"sites": cmd_sites, "apply": cmd_apply, "revert": cmd_revert, "identity": cmd_identity,
     "unidentity": cmd_unidentity, "agent_tests": cmd_agent_tests}[sys.argv[1]](*sys.argv[2:])
