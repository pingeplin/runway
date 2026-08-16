#!/usr/bin/env bash
# Stage 00 — install FeatureBench, pre-pull the split's docker images, and
# sanity-check the local toolchain before any billable work starts.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLIT="${SPLIT:-lite}"
FB_REPO="git+https://github.com/LiberCoders/FeatureBench.git"

fail=0
note() { printf '\n== %s\n' "$1"; }
bad() { printf 'FAIL: %s\n' "$1" >&2; fail=1; }

note "featurebench"
if command -v fb >/dev/null 2>&1; then
  echo "ok: fb present ($(command -v fb))"
else
  echo "fb not found — installing from GitHub (not on PyPI)"
  # uv is preferred when available; both land `fb` on PATH.
  if command -v uv >/dev/null 2>&1; then
    uv tool install "$FB_REPO"
  else
    python3 -m pip install "$FB_REPO"
  fi
  command -v fb >/dev/null 2>&1 || bad "fb still not on PATH after install"
fi

note "python deps"
python3 -c 'import datasets' 2>/dev/null \
  && echo "ok: datasets importable" \
  || bad "python3 cannot import datasets — pip install datasets"

note "docker"
if docker info >/dev/null 2>&1; then
  echo "ok: docker daemon reachable"
else
  bad "docker info failed — start the daemon (stages 01/03/04 all need it)"
fi

note "claude CLI"
if command -v claude >/dev/null 2>&1; then
  echo "ok: claude $(claude --version 2>&1 | head -1)"
else
  bad "claude not on PATH — stage 01 cannot run"
fi

note "ANTHROPIC_API_KEY"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ok: ANTHROPIC_API_KEY set (${#ANTHROPIC_API_KEY} chars)"
else
  bad "ANTHROPIC_API_KEY unset — needed by stage 01 and by fb_config.toml"
fi

note "config files"
for f in config.toml fb_config.toml; do
  if [ -f "$EVAL_ROOT/$f" ]; then
    echo "ok: $f"
  else
    bad "$EVAL_ROOT/$f missing — copy ${f%.toml}.example.toml"
  fi
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "setup incomplete — fix the FAIL lines above, then re-run." >&2
  exit 1
fi

# `fb pull --mode` accepts lite | fast | full | /path/to/images.txt.
note "pre-pulling $SPLIT images (this is slow the first time)"
fb pull --mode "$SPLIT" --n-concurrent 4

echo
echo "stage 00 ok — next: scripts/01_make_specs.py"
