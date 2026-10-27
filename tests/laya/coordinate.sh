#!/bin/bash
set -Eeuo pipefail

# Run as the host user from the project root; never source operator settings.
export FRAMEWORK_DIR="$PWD"
if [[ ! -f "$FRAMEWORK_DIR/ARCHITECTURE.md" ]]; then
    echo 'Run tests/laya/coordinate.sh from the project root.' >&2
    exit 1
fi

export ADAPTER_DIR="$FRAMEWORK_DIR/packages/laya"
export WORKSPACE="$FRAMEWORK_DIR/build/laya-verification"
mkdir -p "$WORKSPACE/downloads" "$WORKSPACE/logs"
LOG_DIR=$(mktemp -d "$WORKSPACE/logs/run-XXXXXX")

MODE=${1:-all}
case "$MODE" in
    prepare|verify|all) ;;
    *) echo "Unknown coordinator mode: $MODE" >&2; exit 1 ;;
esac

if [[ "$MODE" == prepare || "$MODE" == all ]]; then
    timeout 5m bash -Eeuo pipefail -c '
        curl -fLsS --retry 3 --max-time 60 https://pypi.org/pypi/laya/json \
            -o "$WORKSPACE/downloads/laya.json"
        curl -fLsS --retry 3 --max-time 60 https://pypi.org/pypi/click/8.4.2/json \
            -o "$WORKSPACE/downloads/click.json"
        for PROJECT in laya click; do
            ASSET=$(jq -ce '\''[.urls[] | select(.filename | endswith("-py3-none-any.whl"))] | if length == 1 then .[0] else error("Expected one universal wheel") end'\'' \
                "$WORKSPACE/downloads/$PROJECT.json")
            NAME=$(jq -r .filename <<< "$ASSET")
            DIGEST=$(jq -r .digests.sha256 <<< "$ASSET")
            URL=$(jq -r .url <<< "$ASSET")
            if ! printf "%s  %s\n" "$DIGEST" "$WORKSPACE/downloads/$NAME" | sha256sum -c -; then
                curl -fLsS --retry 3 --max-time 60 "$URL" -o "$WORKSPACE/downloads/$NAME"
            fi
            printf "%s  %s\n" "$DIGEST" "$WORKSPACE/downloads/$NAME" | sha256sum -c -
            python3 -m zipfile -l "$WORKSPACE/downloads/$NAME"
        done
    ' > "$LOG_DIR/prepare.log" 2>&1
    echo "Downloads verified; inspect $LOG_DIR/prepare.log"
fi

if [[ "$MODE" == verify || "$MODE" == all ]]; then
    timeout 10m bash tests/run.sh laya > "$LOG_DIR/offline.log" 2>&1
    for SCRIPT in packages/laya/query packages/laya/build tests/laya/coordinate.sh; do
        timeout 2m bash -n "$SCRIPT"
    done > "$LOG_DIR/syntax.log" 2>&1
    git diff --check -- packages/laya tests/laya docs/laya.md README.md ARCHITECTURE.md \
        > "$LOG_DIR/diff.log" 2>&1

    export ARCHES='amd64 arm64'
    export PUBLISHER_STREAM=laya
    export MAINTAINER='Local Verification <verification@localhost>'
    timeout 5m "$ADAPTER_DIR/query" > "$LOG_DIR/query.log" 2>&1
    export BUILD_INPUTS_SHA256
    BUILD_INPUTS_SHA256=$(python3 lib/checksum.py)
    VERSION=$(head -n 1 "$WORKSPACE/targets.tsv" | cut -f1)
    OUTPUT_DIR="$WORKSPACE/output"
    mkdir -p "$OUTPUT_DIR"
    timeout 5m "$ADAPTER_DIR/build" "$VERSION-1" amd64 "$OUTPUT_DIR" \
        > "$LOG_DIR/build.log" 2>&1
    for PACKAGE in "$OUTPUT_DIR"/*.deb; do
        dpkg-deb --info "$PACKAGE"
    done > "$LOG_DIR/packages.log" 2>&1
    echo "Verification complete; packages in $OUTPUT_DIR; logs in $LOG_DIR"
fi
