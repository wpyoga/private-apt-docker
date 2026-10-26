#!/bin/bash
# Optional real amd64 package installation test. All installs stay in containers.
set -Eeuo pipefail
shopt -s nullglob

export FRAMEWORK_DIR="$PWD"
if [[ ! -d "$FRAMEWORK_DIR/tests/gimp" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi
DEB_DIR=${1:?Supply the directory containing the eight real amd64 GIMP adapter outputs}
DEBS=("$DEB_DIR/"*.deb)
if (( ${#DEBS[@]} != 8 )); then
    echo "Expected eight GIMP packages in $DEB_DIR" >&2
    exit 1
fi
mkdir -p "$FRAMEWORK_DIR/build"
CONTEXT=$(mktemp -d "$FRAMEWORK_DIR/build/gimp-install-XXXXXX")
mkdir -p "$CONTEXT/debs"
cp "$FRAMEWORK_DIR/tests/gimp/"* "$CONTEXT/"
cp "${DEBS[@]}" "$CONTEXT/debs/"
if [[ -n "${2:-}" ]]; then
    HELP_DEBS=("$2/"gimp-help-*.deb)
    if (( ${#HELP_DEBS[@]} == 0 )); then
        echo "No GIMP help packages in $2" >&2
        exit 1
    fi
    cp "${HELP_DEBS[@]}" "$CONTEXT/debs/"
fi
printf 'Preserved installation test context: %s\n' "$CONTEXT"
TAG=${CONTEXT##*/}
docker build --progress=plain --no-cache --target clean \
    -t "private-apt-gimp-test:clean-$TAG" "$CONTEXT"
docker build --progress=plain --target reinstall \
    -t "private-apt-gimp-test:reinstall-$TAG" "$CONTEXT"
