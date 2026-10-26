#!/bin/bash
# Optional real amd64 package installation test. All installs stay in containers.
set -Eeuo pipefail
shopt -s nullglob

export FRAMEWORK_DIR="$PWD"
if [[ ! -d "$FRAMEWORK_DIR/tests/gimp" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi
DEB_DIR=${1:?Supply the directory containing the five real amd64 GIMP adapter outputs}
DEBS=("$DEB_DIR/"*.deb)
if (( ${#DEBS[@]} != 5 )); then
    echo "Expected five GIMP packages in $DEB_DIR" >&2
    exit 1
fi
mkdir -p "$FRAMEWORK_DIR/build"
CONTEXT=$(mktemp -d "$FRAMEWORK_DIR/build/gimp-install-XXXXXX")
mkdir -p "$CONTEXT/debs"
cp "$FRAMEWORK_DIR/tests/gimp/"* "$CONTEXT/"
cp "${DEBS[@]}" "$CONTEXT/debs/"
printf 'Preserved installation test context: %s\n' "$CONTEXT"
TAG=${CONTEXT##*/}
docker build --progress=plain --no-cache --target clean \
    -t "private-apt-gimp-test:clean-$TAG" "$CONTEXT"
docker build --progress=plain --target reinstall \
    -t "private-apt-gimp-test:reinstall-$TAG" "$CONTEXT"
