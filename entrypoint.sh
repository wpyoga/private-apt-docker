#!/bin/bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${CHECK_INTERVAL:=21600}"

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
    if bash "$script_dir/update.sh"; then
        echo 'Update cycle complete'
    else
        echo 'Update cycle failed; retry next interval' >&2
    fi
    sleep "$CHECK_INTERVAL" &
    wait $!
done
