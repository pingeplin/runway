#!/usr/bin/env bash
# Run every offline smoke suite with the right interpreter/deps per suite.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --python 3.12 --with datasets bash scripts/smoke_test.sh
uv run --python 3.12 --with datasets bash scripts/smoke_arm_c.sh
uv run --python 3.12 --with datasets bash scripts/smoke_taxonomy.sh
uv run --python 3.12 --with datasets --with pytest bash scripts/smoke_mutation.sh

echo
echo "ALL SMOKE SUITES PASSED"
