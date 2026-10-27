#!/bin/bash
# Shared test coordination, separate from the production publisher library.
set -Eeuo pipefail

: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must be set and non-empty}"

require_project_root() {
    if [[ ! -f "$FRAMEWORK_DIR/update.sh" || ! -d "$FRAMEWORK_DIR/packages" ]]; then
        echo 'Run tests from the project root.' >&2
        return 1
    fi
}

run_logged() {
    local LOG_FILE="$1"
    local TIME_LIMIT="$2"
    shift 2
    local STATUS

    mkdir -p "$(dirname -- "$LOG_FILE")"
    printf 'Running check; log: %s\n' "$LOG_FILE"
    if timeout --kill-after=30s "$TIME_LIMIT" "$@" > "$LOG_FILE" 2>&1; then
        printf 'Check passed; log: %s\n' "$LOG_FILE"
    else
        STATUS=$?
        printf 'Check failed (exit %s); log: %s\n' "$STATUS" "$LOG_FILE" >&2
        return "$STATUS"
    fi
}
