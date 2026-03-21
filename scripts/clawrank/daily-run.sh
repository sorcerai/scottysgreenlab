#!/usr/bin/env bash
# ClawRank daily runner for scottysgreenlab
# Cron entries:
#   0 6 * * * /path/to/daily-run.sh research
#   0 2 * * 1 /path/to/daily-run.sh auto
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/artifacts/clawrank/logs"
mkdir -p "$LOG_DIR"
MODE="${1:-auto}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/run-${MODE}-${TIMESTAMP}.log"
cd "$PROJECT_ROOT"
python3 scripts/clawrank/run.py \
    --mode "$MODE" \
    --auto-approve \
    --backend gemini \
    2>&1 | tee "$LOG_FILE"
find "$LOG_DIR" -name "run-*.log" -mtime +30 -delete 2>/dev/null || true
