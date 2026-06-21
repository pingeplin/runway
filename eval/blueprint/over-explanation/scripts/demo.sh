#!/usr/bin/env bash
#
# demo.sh — run the over-explanation harness end-to-end on the NON-BLIND demo
# corpus. This drives the real analysis pipeline (restatement -> guardrails ->
# buildability -> statistics -> instrument gate -> decision) to a verdict, using
# synthetic per-arm artifacts derived from corpus/demo/.
#
# It proves the framework composes. It proves NOTHING about the real treatment:
# the corpus is Claude-authored and same-family (see corpus/demo/PROVENANCE.md).
#
# Usage:
#   scripts/demo.sh                      # clean run -> SHIP_TREATMENT
#   scripts/demo.sh --break substance    # drop a MUST claim -> DO_NOT_SHIP
#   scripts/demo.sh --break length       # length artifact -> DO_NOT_SHIP
#   scripts/demo.sh --break grammaticality
#   scripts/demo.sh --break instrument

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec uv run python demo/run_demo.py "$@"
