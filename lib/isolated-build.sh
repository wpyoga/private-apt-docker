#!/bin/bash
# The host worker owns Docker; the publisher only submits build requests.
set -Eeuo pipefail

: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must be set and non-empty}"
: "${WORKSPACE:?WORKSPACE must be set and non-empty}"
: "${BUILD_QUEUE_DIR:?Run rebuilds through rebuild.sh to enable isolated dependency builds}"

VERSION="${1:?Supply the package version}"
ARCHITECTURE="${2:?Supply the architecture}"
OUTPUT_DIR="${3:?Supply the output directory}"
if [[ ! -f "$BUILD_QUEUE_DIR/worker.ready" ]]; then
    echo "No host build worker is ready at $BUILD_QUEUE_DIR; use rebuild.sh" >&2
    exit 1
fi
JOB=$(mktemp -d "$BUILD_QUEUE_DIR/job-XXXXXX")
python3 "$FRAMEWORK_DIR/lib/build-context.py" "$JOB" "$ARCHITECTURE"
printf '%s\n' "$VERSION" > "$JOB/version"
printf '%s\n' "$OUTPUT_DIR" > "$JOB/output"
printf '%s\n' "$(id -u):$(id -g)" > "$JOB/user"
touch "$JOB/ready"

echo "[$PUBLISHER_STREAM] Waiting for isolated $ARCHITECTURE build; log: $JOB/build.log"
DEADLINE=$((SECONDS + 7200))
while [[ ! -f "$JOB/result" ]]; do
    if (( SECONDS >= DEADLINE )); then
        echo "[$PUBLISHER_STREAM] Isolated build timed out; retained request: $JOB" >&2
        touch "$JOB/cancelled"
        exit 1
    fi
    sleep 1
done
STATUS=$(cat "$JOB/result")
if [[ "$STATUS" != 0 ]]; then
    echo "[$PUBLISHER_STREAM] Isolated build failed; retained log: $JOB/build.log" >&2
    exit 1
fi
python3 "$FRAMEWORK_DIR/lib/build-context.py" record "$JOB" "$ARCHITECTURE" "$OUTPUT_DIR"
cp -- "$JOB/installed-packages" "$WORKSPACE/installed-build-packages-$ARCHITECTURE.tsv"
# Logs and manifests remain in the cycle workspace. The queue can be reused.
cp -- "$JOB/build.log" "$WORKSPACE/isolated-build-$ARCHITECTURE.log"
rm -rf -- "$JOB"
