# runway

A Claude Code plugin marketplace.

## Installation

```
/plugin marketplace add <your-org>/runway
```

## Plugins

| Plugin | Description |
|--------|-------------|
| [blueprint](./plugins/blueprint/README.md) | Intent producer + invariant referee: `/design ⟲ ──→ /spec ⟲ ──→ ⟦ implement ⟲ /verify ⟧ ──→ /commit`. Each stage runs a bounded produce → judge → revise loop with a fresh-context judge; the human reviews once at loop exit. |

### blueprint

Install:

```
/plugin install blueprint@runway
```

See [`plugins/blueprint/README.md`](./plugins/blueprint/README.md) for the artifact definitions (design vs spec), the pipeline and its loop, and the full skill list.

## License

[MIT](./LICENSE)
