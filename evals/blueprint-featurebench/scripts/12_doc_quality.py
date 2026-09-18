#!/usr/bin/env python3
"""Stage 12 — deterministic spec-quality metrics against the FeatureBench oracle.

Numbers per spec, none of them from an LLM:

- **oracle recall** — the dataset's `patch` is the mask that removed the
  feature; every `def`/`class` line it deletes is a symbol the hidden tests
  reach. Recall = share of those symbols the spec names in code context
  (backticks or fenced code — prose matches of `data` or `view` do not
  count). **Effective recall** subtracts the symbols the spec fences off, so
  a spec that lists the oracle under "Out of scope" gets no credit for it.
- **fenced ∩ oracle** — oracle symbols the spec forbids the agent to touch,
  found by a phrase-and-section heuristic (headings such as "Out of scope",
  lines such as "do not implement …"; code blocks are never fences). The
  LLM listing that reads intent rather than phrasing is stage 13.
- **grounding precision** — files and identifiers the spec names that exist
  in the masked workspace, or are oracle symbols the spec is asking for.
  What is left is hallucinated interface — or a new helper the spec chose to
  design, which this metric cannot tell apart; treat it as diagnostic.
  Test paths are skipped: the spec is expected to name test files it wants
  created.
- **smell density** — requirements smells (Femmer et al. 2017) per 100 prose
  words, by word list, for the INCOSE GtWR v4 rules a word list can detect:
  hedges, R7 vague terms, R8 escape clauses, R9 open-ended clauses, R26
  absolutes. R16 ("not") and R24 (pronouns) need the sentence read, so they
  are counted per class but kept out of the density. The word lists are
  ours, seeded from those rules; Femmer reports ~0.5 precision for this kind
  of detector. Measured on the 15-spec corpus (ρ −0.34, agreement 0.62):
  diagnostic only — reports/2609_smell_density_validation/.

`--corpus label=dir[:report.md]` scores several spec directories side by side
and joins each to its paired report's B pass_rate. The report then shows each
metric's direction against pass_rate two ways: pooled Spearman ρ over every
cell (tasks × labels, so cells are not independent) and within-task
concordance (for each task, do label pairs order the same way on the metric
as on pass_rate?). Neither is a verdict; both exist so a metric that points
the wrong way is seen before anything is optimised against it.
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from _common import RESULTS_DIR, SPECS_DIR, die, mask_reference_solution, write_json

OUT_JSON = RESULTS_DIR / "doc_quality.json"
OUT_MD = RESULTS_DIR / "doc_quality_report.md"

DEF_RE = re.compile(r"^-\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)", re.M)
DIFF_FILE_RE = re.compile(r"^diff --git a/(\S+) b/\S+", re.M)
PY_PATH_RE = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.py)\b")
BACKTICK_RE = re.compile(r"`([^`\n]{1,160})`")
CODE_BLOCK_RE = re.compile(r"```.*?```", re.S)
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
HEADING_RE = re.compile(r"^(#{1,6})\s")
FENCE_HEADING_RE = re.compile(r"out of scope|not in scope|non-goals?|do not (?:attempt|implement|fix|modify|touch|build)", re.I)
FENCE_LINE_RE = re.compile(
    r"out of scope|not in scope|do not (?:attempt|implement|fix|modify|touch|build|restore)|"
    r"must not (?:implement|modify|touch|restore)|leave\b.*\buntouched|not (?:part of|covered by) this spec",
    re.I,
)
SMELL_CLASSES: dict[str, re.Pattern[str]] = {
    "escape": re.compile(
        r"\b(?:where|when|if|as far as|as much as) (?:possible|practical|practicable|appropriate|necessary|needed)\b|"
        r"\bas (?:appropriate|required|needed)\b|\bto the extent (?:possible|practical|necessary)\b",
        re.I,
    ),
    "open_ended": re.compile(r"\b(?:including )?but not limited to\b|\betc\b\.?|\band so (?:on|forth)\b|\band the like\b", re.I),
    "hedge": re.compile(r"\b(?:should|might|ideally|preferably|possibly)\b", re.I),
    "vague": re.compile(
        r"\b(?:adequate(?:ly)?|appropriate(?:ly)?|reasonabl[ey]|sufficient(?:ly)?|significant(?:ly)?|"
        r"efficient(?:ly)?|user-friendly|easy|easily|fast|quick(?:ly)?|flexible|robust|seamless(?:ly)?|"
        r"graceful(?:ly)?|properly|correctly|suitable|several|various|numerous|large|minimal|optimal)\b",
        re.I,
    ),
    "absolute": re.compile(r"\b(?:always|never|completely|entirely|totally)\b|\b100 ?%", re.I),
    "negation": re.compile(r"\bnot\b|n't\b", re.I),
    "pronoun": re.compile(r"\b(?:it|they|them|this|these|those)\b", re.I),
}
SENTENCE_LEVEL_SMELLS = {"negation", "pronoun"}
COMMON_WORDS = {
    "true", "false", "none", "self", "cls", "the", "and", "for", "not", "with",
    "int", "str", "float", "bool", "list", "dict", "tuple", "set", "bytes", "object",
    "np", "numpy", "pytest", "python", "git", "md", "py", "todo", "new", "test", "tests",
    "desiderata", "inferred", "assumption", "given", "when", "then",
}


@dataclass
class Oracle:
    files: set[str]
    symbols: dict[str, set[str]]

    @property
    def all_symbols(self) -> set[str]:
        return set().union(*self.symbols.values()) if self.symbols else set()


@dataclass
class Workspace:
    files: set[str]
    tokens: set[str]


def oracle_from_mask(patch: str) -> Oracle:
    files: set[str] = set()
    symbols: dict[str, set[str]] = {}
    current = None
    for line in patch.splitlines(keepends=True):
        m = DIFF_FILE_RE.match(line)
        if m:
            current = m.group(1)
            files.add(current)
            continue
        m = DEF_RE.match(line)
        if m and current:
            symbols.setdefault(current, set()).add(m.group(2))
    return Oracle(files=files, symbols=symbols)


def load_rows(jsonl: Path) -> dict[str, dict[str, Any]]:
    with open(jsonl, encoding="utf-8") as f:
        return {r["instance_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def load_oracles(jsonl: Path) -> dict[str, Oracle]:
    return {k: oracle_from_mask(v.get("patch") or "") for k, v in load_rows(jsonl).items()}


def code_context(spec: str) -> str:
    """Everything the spec wrote as code: fenced blocks plus inline backticks."""
    blocks = CODE_BLOCK_RE.findall(spec)
    inline = BACKTICK_RE.findall(CODE_BLOCK_RE.sub(" ", spec))
    return "\n".join(blocks + inline)


def word_present(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


def prose_lines(spec: str) -> Iterable[tuple[str, bool]]:
    """Yield (line, is_heading) for lines outside fenced code blocks."""
    in_code = False
    for line in spec.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            yield line, bool(HEADING_RE.match(line))


def smells(spec: str) -> tuple[dict[str, int], int]:
    """Per-class smell counts and word count over prose: no code blocks, no
    headings, no inline code. Classes are matched in order and each match is
    blanked, so "as appropriate" is one escape clause, not also a vague term."""
    text = "\n".join(BACKTICK_RE.sub(" ", line) for line, is_heading in prose_lines(spec) if not is_heading)
    words = len(re.findall(r"[A-Za-z][\w'-]*", text))
    counts: dict[str, int] = {}
    for name, pattern in SMELL_CLASSES.items():
        counts[name] = len(pattern.findall(text))
        text = pattern.sub(" ", text)
    return counts, words


def fenced_symbols(spec: str, oracle_symbols: set[str]) -> list[str]:
    fenced: set[str] = set()
    fence_level = 0
    for line, is_heading in prose_lines(spec):
        if is_heading:
            level = len(HEADING_RE.match(line).group(1))
            if fence_level and level <= fence_level:
                fence_level = 0
            if FENCE_HEADING_RE.search(line):
                fence_level = level
            continue
        if fence_level or FENCE_LINE_RE.search(line):
            for tick in BACKTICK_RE.findall(line):
                fenced.update(i for i in IDENT_RE.findall(tick) if i in oracle_symbols)
    return sorted(fenced)


def named_items(spec: str) -> tuple[set[str], set[str]]:
    paths = set(PY_PATH_RE.findall(spec))
    idents: set[str] = set()
    for tick in BACKTICK_RE.findall(spec):
        if PY_PATH_RE.search(tick) or (" " in tick.strip() and "(" not in tick):
            continue
        for ident in IDENT_RE.findall(tick.split("(")[0]):
            if len(ident) > 2 and ident.lower() not in COMMON_WORDS and not keyword.iskeyword(ident):
                idents.add(ident)
    return paths, idents


def is_test_path(path: str) -> bool:
    return path.startswith("tests/") or "/tests/" in path or Path(path).name.startswith("test_")


def build_workspace(root: Path) -> Workspace:
    files: set[str] = set()
    tokens: set[str] = set()
    for p in root.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        files.add(p.relative_to(root).as_posix())
        if p.suffix in {".py", ".pyx", ".pxd", ".rst", ".cfg", ".toml", ".txt", ".c", ".h"}:
            try:
                tokens.update(IDENT_RE.findall(p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
    return Workspace(files=files, tokens=tokens)


def masked_workspace(pristine: Path, row: dict[str, Any], scratch: Path) -> Workspace:
    """Reproduce exactly what the spec writer saw: testbed + mask + F2P deleted."""
    ws = scratch / row["instance_id"]
    shutil.copytree(pristine, ws, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    info = mask_reference_solution(ws, row)
    if info.get("mask_applied") is False:
        die(f"mask failed for {row['instance_id']}: {info.get('mask_error')}")
    built = build_workspace(ws)
    shutil.rmtree(ws, ignore_errors=True)
    return built


def score_spec(task_id: str, spec: str, oracle: Oracle, ws: Workspace | None) -> dict[str, Any]:
    syms = oracle.all_symbols
    code = code_context(spec)
    hit = {s for s in syms if word_present(code, s)}
    fenced = fenced_symbols(spec, syms)
    hit_files = {f for f in oracle.files if f in spec}
    paths, idents = named_items(spec)
    smell_counts, prose_words = smells(spec)
    lexical_smells = sum(n for k, n in smell_counts.items() if k not in SENTENCE_LEVEL_SMELLS)

    grounding: float | None = None
    ungrounded: list[str] = []
    if ws is not None:
        bad_paths = {p for p in paths if not is_test_path(p) and p not in ws.files and not any(f.endswith("/" + p) for f in ws.files)}
        bad_idents = {i for i in idents if i not in ws.tokens and i not in syms}
        ungrounded = sorted(bad_paths | bad_idents)
        total = len(paths) + len(idents)
        grounding = round(1 - len(ungrounded) / total, 3) if total else None

    return {
        "task_id": task_id,
        "spec_lines": spec.count("\n") + 1,
        "n_oracle_symbols": len(syms),
        "symbol_recall": round(len(hit) / len(syms), 3) if syms else None,
        "effective_recall": round(len(hit - set(fenced)) / len(syms), 3) if syms else None,
        "file_recall": round(len(hit_files) / len(oracle.files), 3) if oracle.files else None,
        "missed_symbols": sorted(syms - hit),
        "fenced_oracle_symbols": fenced,
        "grounding_precision": grounding,
        "n_named": len(paths) + len(idents),
        "ungrounded": ungrounded,
        "prose_words": prose_words,
        "smell_counts": smell_counts,
        "smell_density": round(100 * lexical_smells / prose_words, 2) if prose_words else None,
    }


def pass_rates_from_report(report_md: Path) -> dict[str, float]:
    rates: dict[str, float] = {}
    for line in report_md.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| `([^`]+)` \| [^|]+ \| [^|]+ \| [^|]+ \| ([\d.]+) \|", line)
        if m:
            rates[m.group(1)] = float(m.group(2))
    return rates


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None

    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def within_task_concordance(cells: list[dict[str, Any]], key: Callable[[dict[str, Any]], Any], sign: int = 1) -> tuple[float | None, int]:
    """Over label pairs inside each task: share whose metric order matches
    the pass_rate order in the expected direction (`sign` −1 for a metric
    that should fall as pass_rate rises). Ties on either side are skipped."""
    by_task: dict[str, list[tuple[float, float]]] = {}
    for c in cells:
        v = key(c)
        if v is not None and c.get("pass_rate") is not None:
            by_task.setdefault(c["task_id"], []).append((float(v), c["pass_rate"]))
    agree = total = 0
    for pts in by_task.values():
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                dm, dp = pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]
                if dm and dp:
                    total += 1
                    agree += (dm * sign > 0) == (dp > 0)
    return (round(agree / total, 2) if total else None), total


def short_id(task_id: str) -> str:
    """`astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` → `test_vo`; anything else unchanged."""
    parts = task_id.split(".")
    return parts[2] if len(parts) >= 3 else task_id


def fmt(v: Any) -> str:
    return "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def mean(vals: Iterable[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


Direction = tuple[Callable[[dict[str, Any]], Any], int]

DIRECTION_KEYS: dict[str, Direction] = {
    "symbol_recall": (lambda r: r["symbol_recall"], 1),
    "effective_recall": (lambda r: r["effective_recall"], 1),
    "file_recall": (lambda r: r["file_recall"], 1),
    "fenced∩oracle": (lambda r: len(r["fenced_oracle_symbols"]), -1),
    "grounding_precision": (lambda r: r["grounding_precision"], 1),
    "smell_density": (lambda r: r["smell_density"], -1),
    "spec_lines": (lambda r: r["spec_lines"], 0),
}


def render_direction(cells: list[dict[str, Any]], keys: dict[str, Direction]) -> list[str]:
    n_tasks = len({c["task_id"] for c in cells})
    n_labels = len({c["label"] for c in cells})
    lines = ["", f"## Direction against B pass_rate ({n_tasks} tasks × {n_labels} labels)", ""]
    lines += ["| metric | expected sign | pooled Spearman ρ | within-task agreement with expected sign (label pairs) |", "|---|---|---|---|"]
    for name, (key, sign) in keys.items():
        pts = [(float(key(c)), c["pass_rate"]) for c in cells if key(c) is not None]
        rho = spearman([p[0] for p in pts], [p[1] for p in pts])
        conc, n_pairs = within_task_concordance(cells, key, sign or 1)
        lines.append(f"| `{name}` | {'+' if sign > 0 else '−' if sign < 0 else 'none'} | {fmt(rho)} (n={len(pts)}) | {fmt(conc)} ({n_pairs} pairs) |")
    lines += [
        "",
        "Pooled ρ mixes task difficulty with spec quality (cells share tasks, so they are not "
        "independent); agreement compares labels inside one task only, as the share of pairs "
        "ordered the way the expected sign predicts (0.50 = coin flip; a metric with no expected "
        "sign is read as +). A metric that points the wrong way on either view is **diagnostic "
        "only** and must not be a target.",
    ]
    return lines


def render(groups: dict[str, list[dict[str, Any]]], joined: bool) -> str:
    lines = ["# Doc quality — deterministic spec metrics (stage 12)", ""]
    lines.append(
        "Oracle = `def`/`class` symbols the dataset mask removed. Recall = share the spec names in "
        "code context; effective recall excludes symbols the spec fences off. Fenced = oracle symbols "
        "under an out-of-scope heading or in a do-not-touch sentence (heuristic; stage 13 has the LLM "
        "listing). Grounding = share of named files/identifiers that exist in the masked workspace "
        "or are oracle symbols. Smells = hedges, vague terms, escape and open-ended clauses, absolutes per "
        "100 prose words (word lists; diagnostic only)."
    )
    lines.append("")
    hdr = "| label | task | lines | oracle syms | symbol recall | effective recall | file recall | fenced∩oracle | grounding | smells/100w |"
    if joined:
        hdr += " B pass_rate |"
    lines += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    for label, rows in groups.items():
        for r in rows:
            cells = [
                label, f"`{short_id(r['task_id'])}`", str(r["spec_lines"]), str(r["n_oracle_symbols"]),
                fmt(r["symbol_recall"]), fmt(r["effective_recall"]), fmt(r["file_recall"]),
                f"{len(r['fenced_oracle_symbols'])} {r['fenced_oracle_symbols'] or ''}".strip(),
                fmt(r["grounding_precision"]), fmt(r["smell_density"]),
            ]
            if joined:
                cells.append(fmt(r.get("pass_rate")))
            lines.append("| " + " | ".join(cells) + " |")

    lines += ["", "## Per-label means", ""]
    hdr = "| label | n | symbol recall | effective recall | file recall | fenced∩oracle (sum) | grounding | smells/100w |" + (" B pass_rate |" if joined else "")
    lines += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    for label, rows in groups.items():
        cells = [
            label, str(len(rows)),
            fmt(mean(r["symbol_recall"] for r in rows)), fmt(mean(r["effective_recall"] for r in rows)),
            fmt(mean(r["file_recall"] for r in rows)),
            str(sum(len(r["fenced_oracle_symbols"]) for r in rows)),
            fmt(mean(r["grounding_precision"] for r in rows)), fmt(mean(r["smell_density"] for r in rows)),
        ]
        if joined:
            cells.append(fmt(mean(r.get("pass_rate") for r in rows)))
        lines.append("| " + " | ".join(cells) + " |")

    if joined:
        lines += render_direction([r for rows in groups.values() for r in rows if r.get("pass_rate") is not None], DIRECTION_KEYS)

    lines += ["", "## Misses and ungrounded names", ""]
    for label, rows in groups.items():
        for r in rows:
            if r["missed_symbols"] or r["ungrounded"]:
                lines.append(f"- **{label} / `{short_id(r['task_id'])}`** — missed: {r['missed_symbols'] or 'none'}; ungrounded: {r['ungrounded'][:15] or 'none'}")
    return "\n".join(lines) + "\n"


def parse_corpus(items: list[str]) -> dict[str, tuple[Path, Path | None]]:
    out: dict[str, tuple[Path, Path | None]] = {}
    for item in items:
        label, _, rest = item.partition("=")
        specs, _, report = rest.partition(":")
        if not label or not specs:
            die(f"bad --corpus item {item!r}; expected label=specs_dir[:report.md]")
        out[label] = (Path(specs), Path(report) if report else None)
    return out


def default_dataset_jsonl() -> Path | None:
    found = sorted((RESULTS_DIR / "dataset_arm_b" / "data").glob("*.jsonl"))
    if len(found) > 1:
        print(f"warning: several dataset files, using {found[0]}; pass --dataset-jsonl to choose")
    return found[0] if found else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset-jsonl", default=None, help="Arm B dataset JSONL carrying `patch` (default: results/dataset_arm_b/data/*.jsonl)")
    parser.add_argument("--pristine-testbed", default=None, help="Extracted /testbed shared by every task in the panel; masked per task for grounding. Omit to skip grounding.")
    parser.add_argument("--corpus", action="append", default=[], help="label=specs_dir[:report.md]; repeatable. Default: results/specs")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    jsonl = Path(args.dataset_jsonl) if args.dataset_jsonl else default_dataset_jsonl()
    if not jsonl or not jsonl.exists():
        die("dataset JSONL not found — run stage 02 or pass --dataset-jsonl")
    rows = load_rows(jsonl)
    oracles = {k: oracle_from_mask(v.get("patch") or "") for k, v in rows.items()}

    corpus = parse_corpus(args.corpus) or {"results": (SPECS_DIR, None)}
    task_ids = sorted({p.stem for d, _ in corpus.values() for p in d.glob("*.md") if p.stem in rows and not p.stem.endswith(".ledger")})

    workspaces: dict[str, Workspace] = {}
    if args.pristine_testbed:
        pristine = Path(args.pristine_testbed)
        with tempfile.TemporaryDirectory(prefix="fb-masked-") as tmp:
            for tid in task_ids:
                print(f"masking workspace for {tid} …", flush=True)
                workspaces[tid] = masked_workspace(pristine, rows[tid], Path(tmp))

    groups: dict[str, list[dict[str, Any]]] = {}
    joined = False
    for label, (specs_dir, report) in corpus.items():
        rates = pass_rates_from_report(report) if report and report.exists() else {}
        joined = joined or bool(rates)
        for tid in task_ids:
            spec_path = specs_dir / f"{tid}.md"
            if not spec_path.exists():
                continue
            record = score_spec(tid, spec_path.read_text(encoding="utf-8"), oracles[tid], workspaces.get(tid))
            record.update(label=label, pass_rate=rates.get(tid))
            groups.setdefault(label, []).append(record)

    write_json(Path(args.out_json), {"dataset_jsonl": str(jsonl), "groups": groups})
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render(groups, joined), encoding="utf-8")
    print(f"wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
