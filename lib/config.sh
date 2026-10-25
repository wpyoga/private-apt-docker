#!/bin/bash
# Parse adapter configuration as data; never execute its contents.
set -Eeuo pipefail

: "${ADAPTER_DIR:?ADAPTER_DIR must be set and non-empty}"

CONFIG_FILE="$ADAPTER_DIR/config"
RELEASE_STREAM=
BINARY_PACKAGES=
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
    if [[ "$KEY" != RELEASE_STREAM && "$KEY" != BINARY_PACKAGES ]]; then
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
        BINARY_PACKAGES)
            BINARY_PACKAGES="$VALUE"
            ;;
    esac
done < "$CONFIG_FILE"

if [[ ! "$RELEASE_STREAM" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
    echo 'Invalid or missing RELEASE_STREAM' >&2
    exit 1
fi

read -r -a PACKAGES <<< "$BINARY_PACKAGES"
if (( ${#PACKAGES[@]} == 0 )); then
    echo 'Missing BINARY_PACKAGES' >&2
    exit 1
fi

declare -A SEEN_NAMES=()
for PACKAGE in "${PACKAGES[@]}"; do
    if [[ ! "$PACKAGE" =~ ^[a-z0-9][a-z0-9+.-]+$ || -v SEEN_NAMES[$PACKAGE] ]]; then
        echo "Invalid or duplicate binary package: $PACKAGE" >&2
        exit 1
    fi
    SEEN_NAMES[$PACKAGE]=1
done

printf '%s\n' "$RELEASE_STREAM" "${PACKAGES[*]}"
