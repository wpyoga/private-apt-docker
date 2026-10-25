#!/bin/bash
set -Eeuo pipefail

: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must be set and non-empty}"
: "${ADAPTER_DIR:?ADAPTER_DIR must be set and non-empty}"
: "${WORKSPACE:?WORKSPACE must be set and non-empty}"
: "${PUBLISHER_STREAM:?PUBLISHER_STREAM must be set and non-empty}"
: "${BINARY_PACKAGES:?BINARY_PACKAGES must be set and non-empty}"
: "${ARCHES:?ARCHES must be set and non-empty}"

STREAM="$PUBLISHER_STREAM"

for HOOK in query build; do
    if [[ ! -x "$ADAPTER_DIR/$HOOK" ]]; then
        echo "[$STREAM] Missing executable hook: $HOOK" >&2
        exit 1
    fi
done
mkdir -p "$WORKSPACE"
echo "[$STREAM] Querying upstream"
"$ADAPTER_DIR/query"
python3 "$FRAMEWORK_DIR/lib/validate-targets.py" "$WORKSPACE/targets.tsv" "$ARCHES"
python3 "$FRAMEWORK_DIR/lib/check-activity.py" "$ADAPTER_DIR" "$WORKSPACE"
for ARCHITECTURE in $ARCHES; do
    if ! awk -F '\t' -v ARCHITECTURE="$ARCHITECTURE" '
        $2 == ARCHITECTURE { FOUND = 1 }
        END { exit !FOUND }
    ' "$WORKSPACE/targets.tsv"; then
        echo "WARNING: [$STREAM] No current upstream package for $ARCHITECTURE; keeping existing packages" >&2
    fi
done

BUILD_INPUTS_SHA256=$(python3 "$FRAMEWORK_DIR/lib/checksum.py" "$ADAPTER_DIR")
export BUILD_INPUTS_SHA256
python3 "$FRAMEWORK_DIR/lib/package-files.py" resolve \
    "$ADAPTER_DIR" "$WORKSPACE/targets.tsv" "$BUILD_INPUTS_SHA256"

while IFS=$'\t' read -r VERSION ARCHITECTURE EXISTING; do
    if [[ -n "$EXISTING" ]]; then
        echo "[$STREAM] Already stored: $BINARY_PACKAGES $VERSION ($ARCHITECTURE)"
        continue
    fi
    OUTPUT_DIR="$WORKSPACE/output-$ARCHITECTURE"
    mkdir -p "$OUTPUT_DIR"
    echo "[$STREAM] Building $BINARY_PACKAGES $VERSION ($ARCHITECTURE)"
    "$ADAPTER_DIR/build" "$VERSION" "$ARCHITECTURE" "$OUTPUT_DIR"
    python3 "$FRAMEWORK_DIR/lib/package-files.py" store \
        "$ADAPTER_DIR" "$VERSION" "$ARCHITECTURE" "$BUILD_INPUTS_SHA256" "$OUTPUT_DIR"
    echo "[$STREAM] Stored: $BINARY_PACKAGES $VERSION ($ARCHITECTURE)"
done < "$WORKSPACE/builds.tsv"
