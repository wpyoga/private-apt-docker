#!/bin/bash
set -Eeuo pipefail
umask 022

: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must point to the framework root}"
export FRAMEWORK_DIR
# shellcheck source=lib/repository.sh
source "$FRAMEWORK_DIR/lib/repository.sh"

validate_repository_config

mkdir -p "$REPO_DIR/.state"
exec 9>"$REPO_DIR/.state/update.lock"
if ! flock -n 9; then
    echo 'Update already running'
    exit 0
fi
initialize_repository
WORK_DIR=$(mktemp -d)
trap 'rm -rf -- "$WORK_DIR"' EXIT
STATUS=0

declare -A SEEN_STREAMS=()
shopt -s nullglob
for ADAPTER_DIR in "$PACKAGES_DIR"/*/; do
    ADAPTER_DIR=${ADAPTER_DIR%/}
    export ADAPTER_DIR
    if ! CONFIGURATION=$(bash "$FRAMEWORK_DIR/lib/config.sh" "$ADAPTER_DIR"); then
        STATUS=1
        continue
    fi
    STREAM=${CONFIGURATION%%$'\n'*}
    if [[ -v SEEN_STREAMS[$STREAM] ]]; then
        echo "Duplicate RELEASE_STREAM: $STREAM" >&2
        STATUS=1
        continue
    fi
    SEEN_STREAMS[$STREAM]=1
    export PUBLISHER_STREAM="$STREAM"
    export BINARY_PACKAGES=${CONFIGURATION#*$'\n'}
    export WORKSPACE="$WORK_DIR/streams/$STREAM"

    # A fresh Bash process keeps each stream's failures isolated.
    if bash "$FRAMEWORK_DIR/lib/update-package.sh"; then
        echo "[$STREAM] Update complete"
    else
        echo "[$STREAM] Update failed; continuing with remaining streams" >&2
        STATUS=1
    fi
done
if ! bash "$FRAMEWORK_DIR/lib/publish.sh" "$WORK_DIR/publication"; then
    echo 'Repository publication failed; retry next cycle' >&2
    STATUS=1
fi
exit "$STATUS"
