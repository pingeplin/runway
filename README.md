# runway

A Claude Code plugin marketplace.

## Installation

```
/plugin marketplace add <your-org>/runway
```

## Plugins

| Plugin | Description |
|--------|-------------|
| [blueprint](./plugins/blueprint/README.md) | Full-cycle TDD workflow: `design → spec → plan → run → refactor → commit`. Each stage produces a durable artifact and dispatches a fresh-context evaluator. |

### blueprint

Install:

```
/plugin install blueprint@runway
```

See [`plugins/blueprint/README.md`](./plugins/blueprint/README.md) for the artifact definitions (design vs spec vs plan), the pipeline, and the full skill list.

## License

[MIT](./LICENSE)
