/**
 * run-experiment.workflow.js — the PRIMARY orchestration path for a full
 * over-explanation panel (issue #10), as a deterministic Workflow.
 *
 * Launch it from Claude Code with:
 *   Workflow({ scriptPath: "eval/blueprint/over-explanation/orchestration/run-experiment.workflow.js",
 *              args: { manifest: "preregistration/manifest.demo.json",
 *                      corpus: "corpus/demo", resultsRoot: "results",
 *                      family: "openai", model: "gpt-4.1" } })
 *
 * Prerequisite (live runs): scripts/setup-worktrees.sh has created a worktree +
 * an authed ~/.claude-<ARM_ID> config dir per arm (eval-methodology.md §2). The
 * bash/cron fallback equivalent is scripts/run-experiment.sh.
 *
 * Phases:
 *   Validate  — load + validate the manifest; the instrument-trust gate must be
 *               run and pass BEFORE any arm number is read (fix #1).
 *   Generate  — one cell per (arm, brief, seed) via scripts/run-arm.sh.
 *   Assemble  — analysis/assemble.py runs the cross-family extractor -> results.json.
 *   Analyze   — overexpl restatement|guardrails|stats|decision -> the verdict.
 *
 * NON-BLIND demo data certifies nothing (corpus/demo/PROVENANCE.md). A real run
 * needs the blind corpus and a genuinely non-Anthropic extractor.
 */

export const meta = {
  name: 'overexpl-run-experiment',
  description: 'Drive a full over-explanation panel: validate + instrument gate, generate cells per arm/brief/seed, assemble via the cross-family extractor, analyze to a verdict.',
  phases: [
    { title: 'Validate', detail: 'manifest + instrument-trust gate' },
    { title: 'Generate', detail: 'one cell per arm x brief x seed via run-arm.sh' },
    { title: 'Assemble', detail: 'cross-family extractor -> results.json' },
    { title: 'Analyze', detail: 'restatement + guardrails + stats + decision' },
  ],
}

const ROOT = 'eval/blueprint/over-explanation'
const A = args || {}
const MANIFEST = A.manifest || 'preregistration/manifest.demo.json'
const CORPUS = A.corpus || 'corpus/demo'
const RESULTS = A.resultsRoot || 'results'
const FAMILY = A.family || 'openai'
const MODEL = A.model || 'gpt-4.1'

// ---- Validate: read the manifest panel + run the instrument-trust gate ----
phase('Validate')
const PANEL_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['arms', 'briefs', 'seeds', 'validationProblems', 'instrumentTrusted'],
  properties: {
    arms: { type: 'array', items: { type: 'string' } },
    briefs: { type: 'array', items: { type: 'string' } },
    seeds: { type: 'array', items: { type: 'integer' } },
    validationProblems: { type: 'array', items: { type: 'string' } },
    instrumentTrusted: { type: 'boolean' },
  },
}
const panel = await agent(
  [
    'In ' + ROOT + ', validate the pre-registration and run the instrument-trust gate.',
    '1. `uv run python -c` to load_manifest("' + MANIFEST + '"), call validate(), and read arms/briefs/seeds.',
    '2. The instrument-trust gate (atomization / length-confound / defensive-filler invariance) MUST pass before any arm number is read. If decoys + a fixtures file exist, run `uv run overexpl instrument <docs.json> <decoys.json>`; otherwise report instrumentTrusted=false with a note that decoys are not yet authored.',
    'Return arms, briefs, seeds, validationProblems (empty if clean), instrumentTrusted.',
  ].join('\n'),
  { label: 'validate', phase: 'Validate', schema: PANEL_SCHEMA }
)
log('arms=' + panel.arms.length + ' briefs=' + panel.briefs.length + ' seeds=' + panel.seeds.length +
    ' validation=' + (panel.validationProblems.length ? panel.validationProblems.join('; ') : 'clean') +
    ' instrumentTrusted=' + panel.instrumentTrusted)
if (!panel.instrumentTrusted) {
  log('STOP: instrument-trust gate not passed — do not read arm numbers until it does. Author + certify decoys first.')
  return { stopped: 'instrument_gate_not_passed', panel }
}

// ---- Generate: one cell per (arm, brief, seed) ----
phase('Generate')
const cells = []
for (const arm of panel.arms)
  for (const brief of panel.briefs)
    for (const seed of panel.seeds)
      cells.push({ arm, brief, seed })
log('generating ' + cells.length + ' cells')

const CELL_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['arm', 'brief', 'seed', 'ok', 'note'],
  properties: {
    arm: { type: 'string' }, brief: { type: 'string' }, seed: { type: 'integer' },
    ok: { type: 'boolean' }, note: { type: 'string' },
  },
}
const generated = await parallel(cells.map(c => () => agent(
  [
    'In ' + ROOT + ', run exactly one eval cell and report the outcome.',
    'Command: RESULTS_ROOT="' + RESULTS + '" scripts/run-arm.sh ' + c.arm + ' ' + CORPUS + '/' + c.brief + ' ' + c.seed,
    'This drives a pinned plugin arm headless against the brief and captures its artifacts. It can take minutes; on a non-zero exit (timeout/rate-limit) report ok=false with the tail of run.log as note. Do not retry more than once.',
    'Return {arm, brief, seed, ok, note}.',
  ].join('\n'),
  { label: 'cell:' + c.arm + '/' + c.brief + '/s' + c.seed, phase: 'Generate', schema: CELL_SCHEMA, effort: 'low' }
)))
const okCells = generated.filter(Boolean).filter(g => g.ok)
log('generated ' + okCells.length + '/' + cells.length + ' cells ok')

// ---- Assemble: cross-family extractor -> results.json ----
phase('Assemble')
const assembled = await agent(
  [
    'In ' + ROOT + ', assemble the transport from the run cells using the cross-family extractor.',
    'Command: uv run python analysis/assemble.py --results-root ' + RESULTS + ' --corpus ' + CORPUS +
      ' --family ' + FAMILY + ' --model ' + MODEL + ' --out ' + RESULTS + '/results.json',
    'Report how many records were written and any extraction errors. (Requires the relevant API key in the environment.)',
  ].join('\n'),
  { label: 'assemble', phase: 'Assemble' }
)

// ---- Analyze: restatement + guardrails + stats + decision ----
phase('Analyze')
const analysis = await agent(
  [
    'In ' + ROOT + ', run the analysis over ' + RESULTS + '/results.json and report the verdict.',
    'Run each and capture output: `uv run overexpl restatement ' + RESULTS + '`, `uv run overexpl guardrails ' + RESULTS + '` (non-zero = a guardrail block), `uv run overexpl stats ' + RESULTS + '` (non-zero = length-falsification STOP).',
    'Then summarize: the mean restatement delta, which guardrails (if any) blocked, whether the STOP fired, and the resulting ship/kill reading. If this used the NON-BLIND demo corpus, state explicitly that the verdict certifies nothing (corpus/demo/PROVENANCE.md).',
  ].join('\n'),
  { label: 'analyze', phase: 'Analyze' }
)

return {
  panel,
  cells: { total: cells.length, ok: okCells.length },
  generated: generated.filter(Boolean),
  assemble: assembled,
  analysis,
}
