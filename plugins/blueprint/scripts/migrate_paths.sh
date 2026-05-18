#!/usr/bin/env bash
# Migrate blueprint workflow artifacts from root-level specs/ and plans/
# into the namespaced blueprint/ directory.
#
#   specs/  ->  blueprint/specs/
#   plans/  ->  blueprint/plans/
#
# Design docs in docs/designs/ are NOT moved (they belong to humans, not the
# tool), but any back-links from design docs to specs/plans are rewritten so
# they keep resolving after the move.
#
# Usage:
#   migrate_paths.sh                # dry-run, prints what would happen
#   migrate_paths.sh --apply        # perform the migration with git mv
#   migrate_paths.sh --root <path>  # target a different repo root
#   migrate_paths.sh -h | --help    # this message

set -euo pipefail

APPLY=false
ROOT="$(pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true; shift ;;
    --root) ROOT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: $ROOT is not a git repository. git mv requires a git repo." >&2
  exit 1
fi

NEEDS_SPECS=false
NEEDS_PLANS=false
[[ -d "specs" ]] && NEEDS_SPECS=true
[[ -d "plans" ]] && NEEDS_PLANS=true

if ! $NEEDS_SPECS && ! $NEEDS_PLANS; then
  echo "Nothing to migrate — no specs/ or plans/ at the repo root."
  exit 0
fi

if $NEEDS_SPECS && [[ -d "blueprint/specs" ]]; then
  echo "Error: blueprint/specs/ already exists. Resolve manually before migrating." >&2
  exit 1
fi
if $NEEDS_PLANS && [[ -d "blueprint/plans" ]]; then
  echo "Error: blueprint/plans/ already exists. Resolve manually before migrating." >&2
  exit 1
fi

if $APPLY && [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree has uncommitted changes." >&2
  echo "Commit or stash before --apply so the migration is its own commit." >&2
  exit 1
fi

DESIGN_DOCS=()
if [[ -d "docs/designs" ]]; then
  while IFS= read -r f; do
    if grep -qE '\.\./\.\./(specs|plans)/' "$f" 2>/dev/null; then
      DESIGN_DOCS+=("$f")
    fi
  done < <(find docs/designs -type f -name '*.md')
fi

PREFIX="[dry-run]"
$APPLY && PREFIX="[apply]"

echo "$PREFIX Plan for $ROOT:"
if $NEEDS_SPECS; then
  N=$(find specs -type f | wc -l | tr -d ' ')
  echo "  - git mv specs blueprint/specs   ($N file(s))"
fi
if $NEEDS_PLANS; then
  N=$(find plans -type f | wc -l | tr -d ' ')
  echo "  - git mv plans blueprint/plans   ($N file(s))"
fi
if [[ ${#DESIGN_DOCS[@]} -gt 0 ]]; then
  echo "  - rewrite back-links in ${#DESIGN_DOCS[@]} design doc(s):"
  for f in "${DESIGN_DOCS[@]}"; do echo "      $f"; done
fi

if ! $APPLY; then
  echo
  echo "Dry run only. Re-run with --apply to perform the migration."
  exit 0
fi

mkdir -p blueprint
$NEEDS_SPECS && git mv specs blueprint/specs
$NEEDS_PLANS && git mv plans blueprint/plans

for f in "${DESIGN_DOCS[@]}"; do
  sed -i.bak \
    -e 's|\.\./\.\./specs/|../../blueprint/specs/|g' \
    -e 's|\.\./\.\./plans/|../../blueprint/plans/|g' \
    "$f"
  rm -f "${f}.bak"
  git add "$f"
done

echo
echo "Migration complete. Review with:  git status"
echo "Suggested commit message:"
echo "  chore(blueprint): migrate artifacts to blueprint/{specs,plans}/"
