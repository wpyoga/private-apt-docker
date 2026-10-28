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

BUILD_INPUTS_SHA256=$(python3 "$FRAMEWORK_DIR/lib/checksum.py")
export BUILD_INPUTS_SHA256
python3 "$FRAMEWORK_DIR/lib/resolve-builds.py"
python3 "$FRAMEWORK_DIR/lib/check-activity.py"

for ARCHITECTURE in $ARCHES; do
    if ! awk -F '\t' -v ARCHITECTURE="$ARCHITECTURE" '
        $2 == ARCHITECTURE { FOUND = 1 }
        END { exit !FOUND }
    ' "$WORKSPACE/targets.tsv"; then
        echo "WARNING: [$STREAM] No current upstream package for $ARCHITECTURE; keeping existing packages" >&2
    fi
done

while IFS=$'\t' read -r VERSION ARCHITECTURE EXISTING; do
    PACKAGE_LIST_VARIABLE="BINARY_PACKAGES_${ARCHITECTURE^^}"
    SELECTED_PACKAGES="${!PACKAGE_LIST_VARIABLE:-$BINARY_PACKAGES}"
    if [[ -n "$EXISTING" ]]; then
        echo "[$STREAM] Already stored: $SELECTED_PACKAGES $VERSION ($ARCHITECTURE)"
        continue
    fi

    OUTPUT_DIR="$WORKSPACE/output-$ARCHITECTURE"
    mkdir -p "$OUTPUT_DIR"
    echo "[$STREAM] Building $SELECTED_PACKAGES $VERSION ($ARCHITECTURE)"
    if ! BINARY_PACKAGES="$SELECTED_PACKAGES" \
        "$ADAPTER_DIR/build" "$VERSION" "$ARCHITECTURE" "$OUTPUT_DIR"; then
        echo "ERROR: [$STREAM] Build failed for $VERSION ($ARCHITECTURE)" >&2
        exit 1
    fi
    BINARY_PACKAGES="$SELECTED_PACKAGES" \
        bash "$FRAMEWORK_DIR/lib/store-packages.sh" "$VERSION" "$ARCHITECTURE" "$OUTPUT_DIR"
    echo "[$STREAM] Stored: $SELECTED_PACKAGES $VERSION ($ARCHITECTURE)"
done < "$WORKSPACE/builds.tsv"
