#!/usr/bin/env bash
#
# setup-worktrees.sh — stand up the parallel two-version environment for an
# over-explanation A/B run.
#
# Implements eval-methodology.md §2 ("Setup: parallel-version environment"):
#   - one git worktree per plugin version, pinned to an exact commit via a tag
#   - one isolated $CLAUDE_CONFIG_DIR per version (auth + plugin cache live there)
#
# Naming follows issue #10's A0/A1 convention (A0 = baseline arm, A1 = treatment
# arm), which maps onto §2's vA/vB worktrees and ~/.claude-bpA/bpB config dirs.
#
# This script is idempotent-ish: re-running tags/worktrees that already exist is
# skipped with a notice rather than failing the whole run.
#
# Genuinely manual steps (Claude Code login per config dir) cannot be scripted
# safely; they are surfaced as explicit echo prompts at the end.

set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Usage: setup-worktrees.sh <A0_COMMIT_SHA> <A1_COMMIT_SHA>

Stand up the parallel-version eval environment (eval-methodology.md §2):
  - git tag  eval-A0 / eval-A1  at the two commits
  - git worktree add ../runway-A0 (baseline) and ../runway-A1 (treatment)
  - scaffold ~/.claude-A0 / ~/.claude-A1 per-version $CLAUDE_CONFIG_DIR dirs,
    each with a marketplace + installed-plugin + settings stub pointing at its
    own worktree

Arguments:
  A0_COMMIT_SHA   commit pinning the BASELINE plugin version (arm A0)
  A1_COMMIT_SHA   commit pinning the TREATMENT plugin version (arm A1)

Environment overrides (optional):
  PLUGIN_NAME         marketplace/plugin name to enable   (default: blueprint)
  MARKETPLACE_NAME    known-marketplace key                (default: runway-eval)
  WORKTREE_PREFIX     sibling dir prefix for worktrees     (default: runway)

Example:
  scripts/setup-worktrees.sh 8faf2f8 a2d5fa8
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 2 ]]; then
  echo "error: expected exactly 2 arguments (A0 and A1 commit SHAs)" >&2
  echo >&2
  usage >&2
  exit 2
fi

A0_SHA="$1"
A1_SHA="$2"

PLUGIN_NAME="${PLUGIN_NAME:-blueprint}"
MARKETPLACE_NAME="${MARKETPLACE_NAME:-runway-eval}"
WORKTREE_PREFIX="${WORKTREE_PREFIX:-runway}"

# ---------------------------------------------------------------------------
# Locate the git repo and its parent (worktrees are created as siblings).
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel)"
PARENT_DIR="$(dirname "$REPO_ROOT")"
cd "$REPO_ROOT"

echo "==> repo root:   $REPO_ROOT"
echo "==> worktrees go under: $PARENT_DIR"
echo

# Validate that both SHAs actually resolve to commits before mutating anything.
for sha in "$A0_SHA" "$A1_SHA"; do
  if ! git rev-parse --quiet --verify "${sha}^{commit}" >/dev/null; then
    echo "error: '$sha' is not a commit in $REPO_ROOT" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# §2 "Git worktrees pinned to versions"
#   git tag vA <sha>; git worktree add ../runway-vA vA
# We use stable, self-describing tag names (eval-A0 / eval-A1) so a later
# scoring pass can confirm exactly which commit each arm ran.
# ---------------------------------------------------------------------------
tag_commit() {
  local tag="$1" sha="$2"
  if git rev-parse --quiet --verify "refs/tags/${tag}" >/dev/null; then
    local existing
    existing="$(git rev-parse "refs/tags/${tag}")"
    if [[ "$existing" == "$(git rev-parse "${sha}^{commit}")" ]]; then
      echo "    tag ${tag} already points at ${sha} — keeping"
    else
      echo "error: tag ${tag} already exists at ${existing} but you asked for ${sha}." >&2
      echo "       Delete it first:  git tag -d ${tag}" >&2
      exit 1
    fi
  else
    git tag "$tag" "$sha"
    echo "    tagged ${tag} -> ${sha}"
  fi
}

add_worktree() {
  local dir="$1" tag="$2"
  if [[ -e "$dir" ]]; then
    echo "    worktree dir already exists: $dir — keeping (verify it is pinned to $tag)"
    return 0
  fi
  # Detached checkout at the tag: the eval arm is a frozen snapshot, not a branch
  # we intend to commit onto.
  git worktree add --detach "$dir" "$tag"
  echo "    worktree $dir @ $tag"
}

echo "==> §2 tagging the two pinned commits"
tag_commit "eval-A0" "$A0_SHA"
tag_commit "eval-A1" "$A1_SHA"
echo

WT_A0="${PARENT_DIR}/${WORKTREE_PREFIX}-A0"
WT_A1="${PARENT_DIR}/${WORKTREE_PREFIX}-A1"

echo "==> §2 adding the per-version worktrees"
add_worktree "$WT_A0" "eval-A0"
add_worktree "$WT_A1" "eval-A1"
echo

# ---------------------------------------------------------------------------
# §2 "Two isolated config dirs"
#   Claude Code stores auth + plugin caches in $CLAUDE_CONFIG_DIR. To run two
#   plugin versions side-by-side, give each arm its own config dir whose
#   marketplace points at that arm's worktree.
#
# We scaffold the three files §2 lists by hand:
#   plugins/known_marketplaces.json  -> marketplace path = this arm's worktree
#   plugins/installed_plugins.json   -> the plugin entry
#   settings.json                    -> enabledPlugins: { "<plugin>@<mkt>": true }
#
# These are *stubs* matching the documented shape; exact schema can drift across
# Claude Code releases, so the script also prints a verify command (§2) so you
# can confirm the right version is actually loaded from the cache dir name.
# ---------------------------------------------------------------------------
scaffold_config_dir() {
  local cfg_dir="$1" worktree="$2" arm="$3"

  mkdir -p "${cfg_dir}/plugins"

  # marketplace -> worktree path for this arm
  cat >"${cfg_dir}/plugins/known_marketplaces.json" <<JSON
{
  "${MARKETPLACE_NAME}": {
    "source": {
      "source": "local",
      "path": "${worktree}/eval/blueprint"
    }
  }
}
JSON

  # installed plugin entry
  cat >"${cfg_dir}/plugins/installed_plugins.json" <<JSON
{
  "${PLUGIN_NAME}@${MARKETPLACE_NAME}": {
    "marketplace": "${MARKETPLACE_NAME}"
  }
}
JSON

  # settings enabling the plugin for this config dir
  cat >"${cfg_dir}/settings.json" <<JSON
{
  "enabledPlugins": {
    "${PLUGIN_NAME}@${MARKETPLACE_NAME}": true
  }
}
JSON

  echo "    scaffolded ${cfg_dir} (arm ${arm} -> ${worktree})"
}

CFG_A0="${HOME}/.claude-A0"
CFG_A1="${HOME}/.claude-A1"

echo "==> §2 scaffolding the two isolated \$CLAUDE_CONFIG_DIR dirs"
scaffold_config_dir "$CFG_A0" "$WT_A0" "A0"
scaffold_config_dir "$CFG_A1" "$WT_A1" "A1"
echo

# ---------------------------------------------------------------------------
# Manual steps that CANNOT be scripted (§2 "Practical gotcha": auth is
# per-config-dir; a fresh $CLAUDE_CONFIG_DIR hits the login screen).
# ---------------------------------------------------------------------------
cat <<EOF
==> setup complete. MANUAL STEPS REMAIN (eval-methodology.md §2):

  1. AUTH each config dir separately — auth is per-\$CLAUDE_CONFIG_DIR and a
     fresh dir hits the login screen. Run once per arm and complete the login:

         CLAUDE_CONFIG_DIR=${CFG_A0} claude   # log in, then /exit
         CLAUDE_CONFIG_DIR=${CFG_A1} claude   # log in, then /exit

     (§2 shortcut: if you only need ONE extra version, you may instead unset
      CLAUDE_CONFIG_DIR for one arm so it reuses the already-authed ~/.claude.)

  2. VERIFY the right version is actually loaded — the cache dir name reveals
     the version (§2):

         ls ${CFG_A0}/plugins/cache/${MARKETPLACE_NAME}/${PLUGIN_NAME}/
         ls ${CFG_A1}/plugins/cache/${MARKETPLACE_NAME}/${PLUGIN_NAME}/

  Then drive each arm with:  scripts/run-arm.sh A0 <brief-dir> <seed>
EOF
