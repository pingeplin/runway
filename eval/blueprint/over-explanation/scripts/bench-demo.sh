#!/usr/bin/env bash
#
# bench-demo.sh — offline BLUEPRINT-BENCH end-to-end demo (BENCHMARK.md §6).
#
# Emits a real score.json through the real machinery: the whole-document
# leakage detector, fail-closed transcript parsing, the manifest's frozen
# bench thresholds, the `overexpl score` CLI packer, and the §2 precedence.
#
#   scripts/bench-demo.sh                        # clean -> UNDERPOWERED (exit 1):
#                                                #   strata derive from the manifest
#                                                #   and the demo panel's buildable
#                                                #   large_realistic stratum is n=1,
#                                                #   structurally underpowered by design
#   scripts/bench-demo.sh --break leakage        # unfenced oracle paste -> exit 1
#   scripts/bench-demo.sh --break workaround     # O4 lint trip           -> exit 1
#   scripts/bench-demo.sh --break missing-result # U4 completion fail     -> exit 1
#   scripts/bench-demo.sh --break incomplete     # not scorable           -> exit 4
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec uv run python demo/run_benchmark_demo.py "$@"
