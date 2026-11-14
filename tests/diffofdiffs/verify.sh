#!/bin/bash
# All offline, live source-build and installation checks in one host command.
set -Eeuo pipefail
export FRAMEWORK_DIR="$PWD"
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
if (( EUID == 0 )); then
    echo 'Run verification as the host user; Docker installs packages in image layers.' >&2
    exit 1
fi
mkdir -p "$FRAMEWORK_DIR/build/diffofdiffs/logs"
LOG_DIR="$FRAMEWORK_DIR/build/diffofdiffs/logs"
STATUS=0
run_logged "$LOG_DIR/offline.log" 10m bash tests/run.sh diffofdiffs || STATUS=1
if (( STATUS == 0 )); then
    run_logged "$LOG_DIR/live-build.log" 30m python3 -m tests.diffofdiffs.live_build || STATUS=1
fi
run_logged "$LOG_DIR/shell-syntax.log" 1m bash -c \
    'for SCRIPT in "$@"; do bash -n "$SCRIPT" || exit; done' syntax \
    packages/rebuild/diffofdiffs/query packages/rebuild/diffofdiffs/build tests/diffofdiffs/verify.sh || STATUS=1
run_logged "$LOG_DIR/python-syntax.log" 1m python3 -m py_compile \
    packages/rebuild/diffofdiffs/source.py tests/diffofdiffs/test_diffofdiffs.py \
    tests/diffofdiffs/live_build.py tests/diffofdiffs/smoke.py \
    tests/diffofdiffs/check-upstream.py || STATUS=1
run_logged "$LOG_DIR/diff.log" 1m git diff --check || STATUS=1
printf 'diffofdiffs verification finished (exit %s); logs: %s\n' "$STATUS" "$LOG_DIR"
exit "$STATUS"
