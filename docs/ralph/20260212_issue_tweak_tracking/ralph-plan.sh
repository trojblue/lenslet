#!/bin/bash
# Ralph-style long-running Codex loop for markdown plan execution.
# Usage: ./ralph-plan.sh [max_iterations] [plan_file]

set -euo pipefail

MAX_ITERATIONS=${1:-20}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || (cd "$SCRIPT_DIR/../../.." && pwd))"

PLAN_FILE_DEFAULT="$REPO_ROOT/docs/20260212_issue_tweak_tracking.md"
PLAN_FILE="${2:-$PLAN_FILE_DEFAULT}"
PROMPT_FILE="$SCRIPT_DIR/ralph-plan-prompt.md"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

if ! command -v codex >/dev/null 2>&1; then
  echo "Error: codex command not found in PATH." >&2
  exit 2
fi

if [ ! -f "$PLAN_FILE" ]; then
  echo "Error: plan file not found: $PLAN_FILE" >&2
  exit 2
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "Error: prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

CURRENT_BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown-branch")

# Archive previous run when branch changes.
if [ -f "$LAST_BRANCH_FILE" ] && [ -f "$PROGRESS_FILE" ]; then
  LAST_BRANCH=$(cat "$LAST_BRANCH_FILE" 2>/dev/null || echo "")
  if [ -n "$LAST_BRANCH" ] && [ "$LAST_BRANCH" != "$CURRENT_BRANCH" ]; then
    DATE=$(date +%Y-%m-%d)
    FOLDER_NAME=$(echo "$LAST_BRANCH" | sed 's|/|-|g')
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"

    echo "Archiving previous run: $LAST_BRANCH"
    mkdir -p "$ARCHIVE_FOLDER"
    [ -f "$PROGRESS_FILE" ] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    [ -f "$PLAN_FILE" ] && cp "$PLAN_FILE" "$ARCHIVE_FOLDER/$(basename "$PLAN_FILE").snapshot"
    echo "Archived to: $ARCHIVE_FOLDER"

    {
      echo "# Ralph Progress Log"
      echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "Branch: $CURRENT_BRANCH"
      echo "Repo: $REPO_ROOT"
      echo "Plan: $PLAN_FILE"
      echo "---"
    } > "$PROGRESS_FILE"
  fi
fi

echo "$CURRENT_BRANCH" > "$LAST_BRANCH_FILE"

if [ ! -f "$PROGRESS_FILE" ]; then
  {
    echo "# Ralph Progress Log"
    echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Branch: $CURRENT_BRANCH"
    echo "Repo: $REPO_ROOT"
    echo "Plan: $PLAN_FILE"
    echo "---"
    echo "## Codebase Patterns"
    echo "- Keep backend/frontend contracts explicit across search, health, and export APIs."
    echo "- Prefer composable primitives over route/component-local branching."
    echo "- Preserve existing behavior unless the plan explicitly approves a contract change."
    echo ""
  } > "$PROGRESS_FILE"
fi

# Continue cumulative numbering across invocations by reading the highest
# recorded iteration header from progress.txt (e.g. "## Iteration 20 - ...").
LAST_ITERATION_NUM=$(awk '
  match($0, /^## Iteration[[:space:]]+([0-9]+)/, m) {
    n = m[1] + 0
    if (n > max) max = n
  }
  END { print max + 0 }
' "$PROGRESS_FILE" 2>/dev/null || echo 0)
START_ITERATION_NUM=$((LAST_ITERATION_NUM + 1))
END_ITERATION_NUM=$((START_ITERATION_NUM + MAX_ITERATIONS - 1))

echo "Starting Ralph plan loop"
echo "Max iterations: $MAX_ITERATIONS"
echo "Repo root: $REPO_ROOT"
echo "Plan file: $PLAN_FILE"
echo "Cumulative iteration range: $START_ITERATION_NUM-$END_ITERATION_NUM"

for i in $(seq 1 "$MAX_ITERATIONS"); do
  ITERATION_NUM=$((START_ITERATION_NUM + i - 1))
  echo ""
  echo "======================================================="
  echo "  Ralph Plan Iteration $ITERATION_NUM (run $i of $MAX_ITERATIONS)"
  echo "======================================================="

  ITERATION_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  OUTPUT=$(
    {
      cat "$PROMPT_FILE"
      echo ""
      echo "Runtime context:"
      echo "- repo_root: $REPO_ROOT"
      echo "- plan_file: $PLAN_FILE"
      echo "- progress_file: $PROGRESS_FILE"
      echo "- iteration: $ITERATION_NUM/$END_ITERATION_NUM"
      echo "- run_iteration: $i/$MAX_ITERATIONS"
      echo "- timestamp_utc: $ITERATION_TS"
    } | codex exec --dangerously-bypass-approvals-and-sandbox --color never -C "$REPO_ROOT" - 2>&1 | tee /dev/stderr
  ) || true

  LAST_PROMISE=$(echo "$OUTPUT" | grep -Eo '<promise>(COMPLETE|CONTINUE)</promise>' | tail -n 1 || true)

  if [ "$LAST_PROMISE" = "<promise>COMPLETE</promise>" ]; then
    echo ""
    echo "Ralph plan loop completed all planned work."
    echo "Completed at cumulative iteration $ITERATION_NUM (run $i of $MAX_ITERATIONS)"
    exit 0
  fi

  if [ "$LAST_PROMISE" = "<promise>CONTINUE</promise>" ]; then
    echo "Iteration $i complete. Continuing..."
    sleep 2
    continue
  fi

  echo "Warning: iteration did not emit a terminal promise token; continuing by default." >&2
  echo "Iteration $i complete. Continuing..."
  sleep 2
done

echo ""
echo "Ralph reached max iterations for this run ($MAX_ITERATIONS) without completion."
echo "Last cumulative iteration attempted: $END_ITERATION_NUM"
echo "Check $PROGRESS_FILE and $PLAN_FILE for current handover state."
exit 1
