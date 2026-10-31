#!/bin/bash
# Parse adapter configuration as data; never execute its contents.
set -Eeuo pipefail

: "${ADAPTER_DIR:?ADAPTER_DIR must be set and non-empty}"

CONFIG_FILE="$ADAPTER_DIR/config"
RELEASE_STREAM=
BINARY_PACKAGES=
BINARY_PACKAGES_AMD64=
BINARY_PACKAGES_ARM64=
declare -A SEEN_KEYS=()

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Missing config: $CONFIG_FILE" >&2
    exit 1
fi

while IFS= read -r LINE || [[ -n "$LINE" ]]; do
    if [[ "$LINE" =~ ^[[:space:]]*$ || "$LINE" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    if [[ "$LINE" != *=* ]]; then
        echo "Invalid config line: $LINE" >&2
        exit 1
    fi
    KEY=${LINE%%=*}
    VALUE=${LINE#*=}
    if [[ "$KEY" != RELEASE_STREAM && "$KEY" != BINARY_PACKAGES \
        && "$KEY" != BINARY_PACKAGES_AMD64 && "$KEY" != BINARY_PACKAGES_ARM64 ]]; then
        echo "Unknown config key: $KEY" >&2
        exit 1
    fi
    if [[ -v SEEN_KEYS[$KEY] ]]; then
        echo "Duplicate config key: $KEY" >&2
        exit 1
    fi
    SEEN_KEYS[$KEY]=1

    if [[ "$VALUE" == \"*\" || "$VALUE" == \'*\' ]]; then
        VALUE=${VALUE:1:${#VALUE}-2}
    fi

    case "$KEY" in
        RELEASE_STREAM)
            RELEASE_STREAM="$VALUE"
            ;;
        BINARY_PACKAGES) BINARY_PACKAGES="$VALUE" ;;
        BINARY_PACKAGES_AMD64) BINARY_PACKAGES_AMD64="$VALUE" ;;
        BINARY_PACKAGES_ARM64) BINARY_PACKAGES_ARM64="$VALUE" ;;
    esac
done < "$CONFIG_FILE"

if [[ ! "$RELEASE_STREAM" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
    echo 'Invalid or missing RELEASE_STREAM' >&2
    exit 1
fi

validate_package_list() {
    local LIST="$1"
    local PACKAGE
    local -a NAMES
    local -A SEEN_NAMES=()

    read -r -a NAMES <<< "$LIST"
    if (( ${#NAMES[@]} == 0 )); then
        echo 'Missing binary package list' >&2
        exit 1
    fi
    for PACKAGE in "${NAMES[@]}"; do
        if [[ ! "$PACKAGE" =~ ^[a-z0-9][a-z0-9+.-]+$ || -v SEEN_NAMES[$PACKAGE] ]]; then
            echo "Invalid or duplicate binary package: $PACKAGE" >&2
            exit 1
        fi
        SEEN_NAMES[$PACKAGE]=1
    done
}

if [[ -v SEEN_KEYS[BINARY_PACKAGES_AMD64] || -v SEEN_KEYS[BINARY_PACKAGES_ARM64] ]]; then
    if [[ -v SEEN_KEYS[BINARY_PACKAGES] ]]; then
        echo 'Declare either BINARY_PACKAGES or both architecture-specific lists' >&2
        exit 1
    fi
    validate_package_list "$BINARY_PACKAGES_AMD64"
    validate_package_list "$BINARY_PACKAGES_ARM64"

    # A common package may appear in both lists. Scan its history only once.
    BINARY_PACKAGES=
    declare -A UNION_NAMES=()
    for PACKAGE in $BINARY_PACKAGES_AMD64 $BINARY_PACKAGES_ARM64; do
        if [[ ! -v UNION_NAMES[$PACKAGE] ]]; then
            BINARY_PACKAGES+="${BINARY_PACKAGES:+ }$PACKAGE"
            UNION_NAMES[$PACKAGE]=1
        fi
    done
else
    validate_package_list "$BINARY_PACKAGES"
fi

printf '%s\n' "$RELEASE_STREAM" "$BINARY_PACKAGES" \
    "$BINARY_PACKAGES_AMD64" "$BINARY_PACKAGES_ARM64"
