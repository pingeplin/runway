#!/bin/bash
# Review gate hook: after /spec or /plan completes, inject a review
# instruction back into the model's context via additionalContext.
#
# This ensures the review step is harness-enforced — the model cannot skip it.
# Inspired by Anthropic's harness design research: self-evaluation doesn't work,
# so the harness (not the prompt) must enforce quality gates.

INPUT=$(cat)
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty')

case "$SKILL" in
  spec)
    # Find the most recently modified spec file
    SPECS_DIR="${CLAUDE_PROJECT_DIR:-.}/specs"
    if [ -d "$SPECS_DIR" ]; then
      LATEST=$(ls -t "$SPECS_DIR"/*.md 2>/dev/null | head -1)
      if [ -n "$LATEST" ]; then
        FILE_REF="The spec was written to: $LATEST"
      else
        FILE_REF="Check the specs/ directory for the output."
      fi
    else
      FILE_REF="Check the specs/ directory for the output."
    fi

    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "REVIEW GATE: /spec just completed. $FILE_REF\n\nBefore presenting this spec to the user, you MUST review it by reading and applying references/review-spec.md (all phases). Present the review findings alongside the spec. This is a harness-enforced quality gate — do not skip it."
  }
}
EOF
    ;;

  plan)
    # Find the most recently modified plan file
    PLANS_DIR="${CLAUDE_PROJECT_DIR:-.}/plans"
    if [ -d "$PLANS_DIR" ]; then
      LATEST=$(ls -t "$PLANS_DIR"/*_graph.md 2>/dev/null | head -1)
      if [ -n "$LATEST" ]; then
        FILE_REF="The plan was written to: $LATEST"
      else
        FILE_REF="Check the plans/ directory for the output."
      fi
    else
      FILE_REF="Check the plans/ directory for the output."
    fi

    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "REVIEW GATE: /plan just completed. $FILE_REF\n\nBefore presenting this plan to the user, you MUST review it by reading and applying references/review-plan.md (all phases). Present the review findings alongside the plan. This is a harness-enforced quality gate — do not skip it."
  }
}
EOF
    ;;

  *)
    # Not a reviewable skill — no-op
    exit 0
    ;;
esac
