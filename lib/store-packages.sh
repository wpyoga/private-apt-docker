#!/bin/bash
# Validate all build outputs, then store complete files without overwriting packages.
set -Eeuo pipefail

: "${REPO_DIR:?REPO_DIR must be set and non-empty}"
: "${PUBLISHER_STREAM:?PUBLISHER_STREAM must be set and non-empty}"
: "${BINARY_PACKAGES:?BINARY_PACKAGES must be set and non-empty}"
: "${BUILD_INPUTS_SHA256:?BUILD_INPUTS_SHA256 must be set and non-empty}"

VERSION="$1"
ARCHITECTURE="$2"
OUTPUT_DIR="$3"

check_package() {
    local PACKAGE_FILE="$1"
    local PACKAGE_NAME="$2"
    local PACKAGE_ARCHITECTURE="$3"
    local FORMAT EXPECTED_METADATA ACTUAL_METADATA

    FORMAT='${Package}\n${Version}\n${Architecture}\n${X-Publisher-Stream}\n${X-Build-Inputs-SHA256}\n'
    EXPECTED_METADATA=$(printf '%s\n' \
        "$PACKAGE_NAME" "$VERSION" "$PACKAGE_ARCHITECTURE" "$PUBLISHER_STREAM" "$BUILD_INPUTS_SHA256")
    ACTUAL_METADATA=$(dpkg-deb --show --showformat="$FORMAT" "$PACKAGE_FILE")

    if [[ "$ACTUAL_METADATA" != "$EXPECTED_METADATA" ]]; then
        echo "Incorrect package metadata: $PACKAGE_FILE" >&2
        exit 1
    fi
}

read -r -a PACKAGE_NAMES <<< "$BINARY_PACKAGES"
shopt -s nullglob dotglob
OUTPUT_FILES=("$OUTPUT_DIR"/*)
if (( ${#OUTPUT_FILES[@]} != ${#PACKAGE_NAMES[@]} )); then
    echo 'Build output must contain exactly the declared binary packages' >&2
    exit 1
fi

# Check the whole output set before storing any files.
EXISTING_LIST=$(mktemp)
TEMPORARY_FILE=
cleanup() {
    rm -f -- "$EXISTING_LIST"
    if [[ -n "$TEMPORARY_FILE" ]]; then
        rm -f -- "$TEMPORARY_FILE"
    fi
}
trap cleanup EXIT

PENDING_FILES=()
for PACKAGE_NAME in "${PACKAGE_NAMES[@]}"; do
    PACKAGE_ARCHITECTURE="$ARCHITECTURE"
    FILENAME="${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}.deb"
    PACKAGE_FILE="$OUTPUT_DIR/$FILENAME"
    if [[ ! -f "$PACKAGE_FILE" ]]; then
        PACKAGE_ARCHITECTURE=all
        FILENAME="${PACKAGE_NAME}_${VERSION}_all.deb"
        PACKAGE_FILE="$OUTPUT_DIR/$FILENAME"
    fi
    if [[ ! -f "$PACKAGE_FILE" ]]; then
        echo "Missing built package: $PACKAGE_FILE" >&2
        exit 1
    fi
    check_package "$PACKAGE_FILE" "$PACKAGE_NAME" "$PACKAGE_ARCHITECTURE"

    # Older repository managers may omit the version's epoch from filenames.
    LEGACY_FILENAME="${PACKAGE_NAME}_${VERSION#*:}_${PACKAGE_ARCHITECTURE}.deb"
    find "$REPO_DIR/pool" -type f \
        \( -name "$FILENAME" -o -name "$LEGACY_FILENAME" \) -print0 > "$EXISTING_LIST"
    mapfile -d '' -t EXISTING_FILES < "$EXISTING_LIST"

    for EXISTING_FILE in "${EXISTING_FILES[@]}"; do
        check_package "$EXISTING_FILE" "$PACKAGE_NAME" "$PACKAGE_ARCHITECTURE"
    done
    if (( ${#EXISTING_FILES[@]} == 0 )); then
        PENDING_FILES+=("$PACKAGE_FILE")
    fi
done

DESTINATION_DIR="$REPO_DIR/pool/main/$PUBLISHER_STREAM"
mkdir -p "$DESTINATION_DIR"
for PACKAGE_FILE in "${PENDING_FILES[@]}"; do
    TEMPORARY_FILE=$(mktemp "$DESTINATION_DIR/.package-XXXXXX")
    install -m 644 -- "$PACKAGE_FILE" "$TEMPORARY_FILE"
    sync -d "$TEMPORARY_FILE"

    # A hard link publishes the complete file and refuses to replace an existing one.
    ln -- "$TEMPORARY_FILE" "$DESTINATION_DIR/${PACKAGE_FILE##*/}"
    rm -- "$TEMPORARY_FILE"
    TEMPORARY_FILE=
done
