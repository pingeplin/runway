# eval/

Evaluation infrastructure for this marketplace's plugins — **kept separate from
plugin content on purpose.** A plugin must never bundle its own grader: an
evaluator that ships inside the thing it evaluates can't be trusted (a changed
skill would, in effect, define its own passing bar). Everything here runs
**externally and on demand** — typically by pinning two plugin commits
(baseline vs. changed) and comparing them — and is **not** loaded by any skill,
command, or agent at runtime.

## Layout — one subdirectory per plugin

`eval/` mirrors `plugins/`: each plugin's evaluation harnesses live under
`eval/<plugin-name>/`.

```
eval/
  blueprint/
    eval-methodology.md          # reusable plugin-version comparison methodology
    over-explanation/            # (planned, see issue #10) over-explanation benchmark harness
  thinking-craft/                # (none yet)
```

Cross-plugin or marketplace-wide tooling, if it ever exists, goes at the top
level of `eval/` alongside this README.
