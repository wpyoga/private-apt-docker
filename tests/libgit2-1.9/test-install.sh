#!/bin/bash
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
OUTPUT_DIR="${1:?Supply the complete amd64 package output directory}"
if (( EUID == 0 )); then
    echo 'Run this test coordinator as the host user; Docker installs packages in image layers.' >&2
    exit 1
fi

CONTEXT=$(mktemp -d "$FRAMEWORK_DIR/build/libgit2-install-XXXXXX")
mkdir "$CONTEXT/packages"
PACKAGES=(libgit2-1.9 libgit2-dev libgit2-experimental1.9 libgit2-experimental-dev)
for PACKAGE in "${PACKAGES[@]}"; do
    shopt -s nullglob
    FILES=("$OUTPUT_DIR/${PACKAGE}_"*_amd64.deb)
    if (( ${#FILES[@]} != 1 )); then
        echo "$OUTPUT_DIR: expected one amd64 package for $PACKAGE" >&2
        exit 1
    fi
    cp -- "${FILES[0]}" "$CONTEXT/packages/"
done
cp "$FRAMEWORK_DIR/tests/libgit2-1.9/Dockerfile" "$CONTEXT/"
cp "$FRAMEWORK_DIR/tests/libgit2-1.9/smoke.c" "$CONTEXT/"
run_logged "$CONTEXT/install.log" 15m \
    docker build --network=default -t private-apt-libgit2-install-test:local "$CONTEXT"
