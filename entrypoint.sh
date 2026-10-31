#!/bin/bash
set -Eeuo pipefail

# Host entry points run from the project root; hooks receive this context.
export FRAMEWORK_DIR="${FRAMEWORK_DIR:-$PWD}"

# shellcheck source=lib/repository.sh
source "$FRAMEWORK_DIR/lib/repository.sh"

validate_repository_config
: "${CHECK_INTERVAL:?CHECK_INTERVAL must be set and non-empty}"

case "$CHECK_INTERVAL" in
    ''|*[!0-9]*)
        echo 'CHECK_INTERVAL must be integer seconds' >&2
        exit 1
        ;;
esac

# Normalize leading zeros before Bash arithmetic.
CHECK_INTERVAL=$((10#$CHECK_INTERVAL))
if (( CHECK_INTERVAL < 3600 )); then
    echo 'CHECK_INTERVAL must be at least 3600 seconds' >&2
    exit 1
fi

while :; do
    if bash "$FRAMEWORK_DIR/update.sh"; then
        echo 'Update cycle complete'
    else
        echo 'Update cycle failed; retry next interval' >&2
    fi

    sleep "$CHECK_INTERVAL" &
    wait $!
done
