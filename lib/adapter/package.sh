#!/bin/bash
# Shared publisher operations; adapters retain staging and validation policy.
set -Eeuo pipefail

installed_size() {
    du --summarize --block-size=1024 --exclude=DEBIAN "$1" | cut -f1
}

build_deb() {
    dpkg-deb --build --root-owner-group -Zgzip "$1" "$2"
}

download_file() {
    local URL=$1 DESTINATION=$2
    shift 2
    curl -fLsS --retry 3 "$@" "$URL" -o "$DESTINATION"
}

verify_download() {
    local URL=$1 DESTINATION=$2 SHA256=$3 POLICY=$4
    shift 4
    case "$POLICY" in
        refresh|reuse|repair) ;;
        *) echo "Invalid download policy: $POLICY" >&2; return 1 ;;
    esac
    if [[ ! "$SHA256" =~ ^[0-9a-fA-F]{64}$ ]]; then
        echo "Invalid SHA256 for $DESTINATION: $SHA256" >&2
        return 1
    fi
    if [[ -f "$DESTINATION" && "$POLICY" != refresh ]]; then
        if printf '%s  %s\n' "$SHA256" "$DESTINATION" | sha256sum --check; then
            return
        elif [[ "$POLICY" == reuse ]]; then
            return 1
        fi
    fi
    download_file "$URL" "$DESTINATION.part" "$@"
    printf '%s  %s\n' "$SHA256" "$DESTINATION.part" | sha256sum --check
    mv -- "$DESTINATION.part" "$DESTINATION"
}

check_deb_field() {
    local ARCHIVE=$1 FIELD=$2 EXPECTED=$3 ACTUAL
    ACTUAL=$(dpkg-deb --field "$ARCHIVE" "$FIELD")
    if [[ "$ACTUAL" != "$EXPECTED" ]]; then
        echo "$ARCHIVE: unexpected $FIELD; expected '$EXPECTED', got '$ACTUAL'" >&2
        return 1
    fi
}

render_template() {
    local TEMPLATE=$1 OUTPUT=$2 NAME VALUE
    local -a REPLACEMENTS=()
    shift 2
    while (( $# )); do
        NAME=$1
        VALUE=$(printf '%s' "$2" | sed 's/[\\&|]/\\&/g')
        REPLACEMENTS+=(-e "s|@$NAME@|$VALUE|g")
        shift 2
    done
    sed "${REPLACEMENTS[@]}" "$TEMPLATE" > "$OUTPUT"
}

render_control() {
    local TEMPLATE=$1 PACKAGE_DIR=$2
    shift 2
    mkdir -p "$PACKAGE_DIR/DEBIAN"
    render_template "$TEMPLATE" "$PACKAGE_DIR/DEBIAN/control" \
        MAINTAINER "$MAINTAINER" PACKAGE_VERSION "$PACKAGE_VERSION" \
        INSTALLED_SIZE "$(installed_size "$PACKAGE_DIR")" \
        BUILD_INPUTS_SHA256 "$BUILD_INPUTS_SHA256" PUBLISHER_STREAM "$PUBLISHER_STREAM" \
        "$@"
}
