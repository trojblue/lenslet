#!/bin/bash
# Ralph Wiggum - Long-running AI agent loop
# Usage:
#   ./ralph.sh [max_iterations]
#   ./ralph.sh --mode plan --max-tasks 6 [max_iterations]
#   ./ralph.sh --tool claude --mode prd 12

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./ralph.sh [options] [max_iterations]

Options:
  --tool codex|claude        Runtime tool (default from config or codex)
  --mode prd|plan            Execution mode (default from config or prd)
  --max-tasks N              Task cap per iteration (default: prd=1, plan=6)
  --plan-file PATH           Override plan file path for plan mode
  --work-dir PATH            Override working directory (default: repo root)
  --prompt-file PATH         Override codex prompt file
  --claude-prompt-file PATH  Override claude prompt file
  --help                     Show this help

Config file (optional): ralph.config.json in this directory.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR")"
CONFIG_FILE="$SCRIPT_DIR/ralph.config.json"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not found in PATH." >&2
  exit 2
fi

resolve_path() {
  local p="$1"
  if [[ -z "$p" ]]; then
    echo ""
  elif [[ "$p" = /* ]]; then
    echo "$p"
  else
    echo "$SCRIPT_DIR/$p"
  fi
}

sanitize_branch_name() {
  echo "$1" | sed 's|^ralph/||; s|/|-|g'
}

current_git_branch() {
  git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown-branch"
}

detect_latest_plan_file() {
  find "$REPO_ROOT/docs" "$REPO_ROOT/docs_for_llm" -maxdepth 1 -type f -name '*.md' -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr \
    | head -n 1 \
    | cut -d' ' -f2-
}

write_progress_header() {
  local progress_file="$1"
  local plan_file="$2"
  local prd_file="$3"
  {
    echo "# Ralph Progress Log"
    echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Mode: $MODE"
    echo "Tool: $TOOL"
    echo "Repo: $REPO_ROOT"
    if [[ -n "$plan_file" ]]; then
      echo "Plan: $plan_file"
    fi
    if [[ -n "$prd_file" ]]; then
      echo "PRD: $prd_file"
    fi
    echo "---"
  } > "$progress_file"
}

TOOL="codex"
MODE="prd"
MAX_ITERATIONS=10
MAX_TASKS_PER_ITERATION=""
PLAN_FILE_RAW=""
PRD_FILE_RAW="prd.json"
PROGRESS_FILE_RAW="progress.txt"
WORK_DIR_RAW=""
PROMPT_FILE_RAW=""
CLAUDE_PROMPT_FILE_RAW=""

if [[ -f "$CONFIG_FILE" ]]; then
  CFG_TOOL="$(jq -r '.tool // empty' "$CONFIG_FILE")"
  CFG_MODE="$(jq -r '.mode // empty' "$CONFIG_FILE")"
  CFG_MAX_ITERATIONS="$(jq -r '.maxIterations // empty' "$CONFIG_FILE")"
  CFG_MAX_TASKS="$(jq -r '.maxTasksPerIteration // empty' "$CONFIG_FILE")"
  CFG_PLAN_FILE="$(jq -r '.planFile // empty' "$CONFIG_FILE")"
  CFG_PRD_FILE="$(jq -r '.prdFile // empty' "$CONFIG_FILE")"
  CFG_PROGRESS_FILE="$(jq -r '.progressFile // empty' "$CONFIG_FILE")"
  CFG_WORK_DIR="$(jq -r '.workDir // empty' "$CONFIG_FILE")"
  CFG_PROMPT_FILE="$(jq -r '.promptFile // empty' "$CONFIG_FILE")"
  CFG_CLAUDE_PROMPT_FILE="$(jq -r '.claudePromptFile // empty' "$CONFIG_FILE")"

  [[ -n "$CFG_TOOL" ]] && TOOL="$CFG_TOOL"
  [[ -n "$CFG_MODE" ]] && MODE="$CFG_MODE"
  [[ -n "$CFG_MAX_ITERATIONS" ]] && MAX_ITERATIONS="$CFG_MAX_ITERATIONS"
  [[ -n "$CFG_MAX_TASKS" ]] && MAX_TASKS_PER_ITERATION="$CFG_MAX_TASKS"
  [[ -n "$CFG_PLAN_FILE" ]] && PLAN_FILE_RAW="$CFG_PLAN_FILE"
  [[ -n "$CFG_PRD_FILE" ]] && PRD_FILE_RAW="$CFG_PRD_FILE"
  [[ -n "$CFG_PROGRESS_FILE" ]] && PROGRESS_FILE_RAW="$CFG_PROGRESS_FILE"
  [[ -n "$CFG_WORK_DIR" ]] && WORK_DIR_RAW="$CFG_WORK_DIR"
  [[ -n "$CFG_PROMPT_FILE" ]] && PROMPT_FILE_RAW="$CFG_PROMPT_FILE"
  [[ -n "$CFG_CLAUDE_PROMPT_FILE" ]] && CLAUDE_PROMPT_FILE_RAW="$CFG_CLAUDE_PROMPT_FILE"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tool)
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --mode=*)
      MODE="${1#*=}"
      shift
      ;;
    --max-tasks)
      MAX_TASKS_PER_ITERATION="$2"
      shift 2
      ;;
    --max-tasks=*)
      MAX_TASKS_PER_ITERATION="${1#*=}"
      shift
      ;;
    --plan-file)
      PLAN_FILE_RAW="$2"
      shift 2
      ;;
    --plan-file=*)
      PLAN_FILE_RAW="${1#*=}"
      shift
      ;;
    --work-dir)
      WORK_DIR_RAW="$2"
      shift 2
      ;;
    --work-dir=*)
      WORK_DIR_RAW="${1#*=}"
      shift
      ;;
    --prompt-file)
      PROMPT_FILE_RAW="$2"
      shift 2
      ;;
    --prompt-file=*)
      PROMPT_FILE_RAW="${1#*=}"
      shift
      ;;
    --claude-prompt-file)
      CLAUDE_PROMPT_FILE_RAW="$2"
      shift 2
      ;;
    --claude-prompt-file=*)
      CLAUDE_PROMPT_FILE_RAW="${1#*=}"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
        shift
      else
        echo "Error: unknown argument '$1'" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

if [[ "$TOOL" != "codex" && "$TOOL" != "claude" ]]; then
  echo "Error: invalid tool '$TOOL'. Must be 'codex' or 'claude'." >&2
  exit 1
fi

if [[ "$MODE" != "prd" && "$MODE" != "plan" ]]; then
  echo "Error: invalid mode '$MODE'. Must be 'prd' or 'plan'." >&2
  exit 1
fi

if ! [[ "$MAX_ITERATIONS" =~ ^[0-9]+$ ]] || [[ "$MAX_ITERATIONS" -lt 1 ]]; then
  echo "Error: max_iterations must be a positive integer." >&2
  exit 1
fi

if [[ -z "$MAX_TASKS_PER_ITERATION" ]]; then
  if [[ "$MODE" == "plan" ]]; then
    MAX_TASKS_PER_ITERATION=6
  else
    MAX_TASKS_PER_ITERATION=1
  fi
fi

if ! [[ "$MAX_TASKS_PER_ITERATION" =~ ^[0-9]+$ ]] || [[ "$MAX_TASKS_PER_ITERATION" -lt 1 ]]; then
  echo "Error: --max-tasks must be a positive integer." >&2
  exit 1
fi

PRD_FILE="$(resolve_path "$PRD_FILE_RAW")"
PROGRESS_FILE="$(resolve_path "$PROGRESS_FILE_RAW")"

if [[ -n "$WORK_DIR_RAW" ]]; then
  WORK_DIR="$(resolve_path "$WORK_DIR_RAW")"
else
  WORK_DIR="$REPO_ROOT"
fi

if [[ "$MODE" == "plan" ]]; then
  if [[ -z "$PLAN_FILE_RAW" ]]; then
    PLAN_FILE_RAW="$(detect_latest_plan_file)"
  fi
  PLAN_FILE="$(resolve_path "$PLAN_FILE_RAW")"
  if [[ -z "$PLAN_FILE" || ! -f "$PLAN_FILE" ]]; then
    echo "Error: plan mode selected but no plan file found." >&2
    echo "Set planFile in ralph.config.json or pass --plan-file <path>." >&2
    exit 2
  fi
else
  PLAN_FILE=""
fi

if [[ "$MODE" == "prd" && ! -f "$PRD_FILE" ]]; then
  echo "Error: prd mode selected but PRD file not found: $PRD_FILE" >&2
  echo "Create prd.json or run with --mode plan." >&2
  exit 2
fi

REPORT_PRD_FILE=""
if [[ "$MODE" == "prd" ]]; then
  REPORT_PRD_FILE="$PRD_FILE"
fi

DEFAULT_CODEX_PROMPT="$SCRIPT_DIR/prompt.md"
DEFAULT_CLAUDE_PROMPT="$SCRIPT_DIR/CLAUDE.md"
if [[ "$MODE" == "plan" ]]; then
  DEFAULT_CODEX_PROMPT="$SCRIPT_DIR/prompt-plan.md"
  DEFAULT_CLAUDE_PROMPT="$SCRIPT_DIR/CLAUDE-plan.md"
fi

if [[ -z "$PROMPT_FILE_RAW" ]]; then
  CODEX_PROMPT_FILE="$DEFAULT_CODEX_PROMPT"
else
  CODEX_PROMPT_FILE="$(resolve_path "$PROMPT_FILE_RAW")"
fi

if [[ -z "$CLAUDE_PROMPT_FILE_RAW" ]]; then
  CLAUDE_PROMPT_FILE="$DEFAULT_CLAUDE_PROMPT"
else
  CLAUDE_PROMPT_FILE="$(resolve_path "$CLAUDE_PROMPT_FILE_RAW")"
fi

if [[ "$TOOL" == "codex" && ! -f "$CODEX_PROMPT_FILE" ]]; then
  echo "Error: codex prompt file not found: $CODEX_PROMPT_FILE" >&2
  exit 2
fi

if [[ "$TOOL" == "claude" && ! -f "$CLAUDE_PROMPT_FILE" ]]; then
  echo "Error: claude prompt file not found: $CLAUDE_PROMPT_FILE" >&2
  exit 2
fi

TRACKING_BRANCH="$(current_git_branch)"
if [[ "$MODE" == "prd" && -f "$PRD_FILE" ]]; then
  PRD_BRANCH="$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || true)"
  if [[ -n "$PRD_BRANCH" ]]; then
    TRACKING_BRANCH="$PRD_BRANCH"
  fi
fi

if [[ -f "$LAST_BRANCH_FILE" && -f "$PROGRESS_FILE" ]]; then
  LAST_BRANCH="$(cat "$LAST_BRANCH_FILE" 2>/dev/null || true)"
  if [[ -n "$LAST_BRANCH" && "$LAST_BRANCH" != "$TRACKING_BRANCH" ]]; then
    DATE="$(date +%Y-%m-%d)"
    FOLDER_NAME="$(sanitize_branch_name "$LAST_BRANCH")"
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"

    echo "Archiving previous run: $LAST_BRANCH"
    mkdir -p "$ARCHIVE_FOLDER"
    [[ -f "$PRD_FILE" ]] && cp "$PRD_FILE" "$ARCHIVE_FOLDER/"
    [[ -f "$PROGRESS_FILE" ]] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    if [[ -n "$PLAN_FILE" && -f "$PLAN_FILE" ]]; then
      cp "$PLAN_FILE" "$ARCHIVE_FOLDER/$(basename "$PLAN_FILE").snapshot"
    fi
    echo "   Archived to: $ARCHIVE_FOLDER"

    write_progress_header "$PROGRESS_FILE" "$PLAN_FILE" "$REPORT_PRD_FILE"
  fi
fi

echo "$TRACKING_BRANCH" > "$LAST_BRANCH_FILE"

if [[ ! -f "$PROGRESS_FILE" ]]; then
  write_progress_header "$PROGRESS_FILE" "$PLAN_FILE" "$REPORT_PRD_FILE"
fi

echo "Starting Ralph"
echo "  Tool: $TOOL"
echo "  Mode: $MODE"
echo "  Max iterations: $MAX_ITERATIONS"
echo "  Max tasks per iteration: $MAX_TASKS_PER_ITERATION"
echo "  Work dir: $WORK_DIR"
if [[ -n "$PLAN_FILE" ]]; then
  echo "  Plan file: $PLAN_FILE"
fi
if [[ "$MODE" == "prd" ]]; then
  echo "  PRD file: $PRD_FILE"
fi

for i in $(seq 1 "$MAX_ITERATIONS"); do
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  Ralph Iteration $i of $MAX_ITERATIONS ($TOOL / $MODE)"
  echo "═══════════════════════════════════════════════════════"

  ITERATION_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if [[ "$TOOL" == "codex" ]]; then
    OUTPUT=$(
      {
        cat "$CODEX_PROMPT_FILE"
        echo ""
        echo "Runtime context:"
        echo "- mode: $MODE"
        echo "- tool: $TOOL"
        echo "- repo_root: $REPO_ROOT"
        echo "- work_dir: $WORK_DIR"
        echo "- prd_file: $PRD_FILE"
        echo "- plan_file: ${PLAN_FILE:-}"
        echo "- progress_file: $PROGRESS_FILE"
        echo "- max_tasks_per_iteration: $MAX_TASKS_PER_ITERATION"
        echo "- iteration: $i/$MAX_ITERATIONS"
        echo "- timestamp_utc: $ITERATION_TS"
      } | codex exec --dangerously-bypass-approvals-and-sandbox --color never -C "$WORK_DIR" - 2>&1 | tee /dev/stderr
    ) || true
  else
    OUTPUT=$(
      (
        cd "$WORK_DIR"
        {
          cat "$CLAUDE_PROMPT_FILE"
          echo ""
          echo "Runtime context:"
          echo "- mode: $MODE"
          echo "- tool: $TOOL"
          echo "- repo_root: $REPO_ROOT"
          echo "- work_dir: $WORK_DIR"
          echo "- prd_file: $PRD_FILE"
          echo "- plan_file: ${PLAN_FILE:-}"
          echo "- progress_file: $PROGRESS_FILE"
          echo "- max_tasks_per_iteration: $MAX_TASKS_PER_ITERATION"
          echo "- iteration: $i/$MAX_ITERATIONS"
          echo "- timestamp_utc: $ITERATION_TS"
        } | claude --dangerously-skip-permissions --print
      ) 2>&1 | tee /dev/stderr
    ) || true
  fi

  LAST_PROMISE="$(printf '%s\n' "$OUTPUT" | tr -d '\r' | sed -n 's/^[[:space:]]*<promise>\(COMPLETE\|CONTINUE\)<\/promise>[[:space:]]*$/<promise>\1<\/promise>/p' | tail -n 1 || true)"

  if [[ "$LAST_PROMISE" == "<promise>COMPLETE</promise>" ]]; then
    echo ""
    echo "Ralph completed all tasks!"
    echo "Completed at iteration $i of $MAX_ITERATIONS"
    exit 0
  fi

  if [[ "$LAST_PROMISE" != "<promise>CONTINUE</promise>" ]]; then
    echo "Warning: iteration did not emit a standalone terminal promise token; continuing by default." >&2
  fi

  echo "Iteration $i complete. Continuing..."
  sleep 2
done

echo ""
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all tasks."
echo "Check $PROGRESS_FILE for status."
exit 1
