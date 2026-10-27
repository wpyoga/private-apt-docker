#!/bin/bash
# Optional real amd64 package installation test. All installs stay in containers.
set -Eeuo pipefail
shopt -s nullglob

export FRAMEWORK_DIR="$PWD"
if [[ ! -f "$FRAMEWORK_DIR/tests/lib/common.sh" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
if (( EUID == 0 )); then
    echo 'Run this test coordinator as your host user; Docker performs package installation inside image layers.' >&2
    exit 1
fi
TARGET=${2:-all}
if [[ "$TARGET" != all && "$TARGET" != clean && "$TARGET" != reinstall ]]; then
    echo "Unknown installation test target: $TARGET" >&2
    exit 1
fi
DEB_DIR=${1:?Supply the directory containing the complete real amd64 GIMP adapter outputs}
DEBS=("$DEB_DIR/"*.deb)
EXPECTED_PACKAGES=$(sed -n 's/^BINARY_PACKAGES="\(.*\)"$/\1/p' packages/gimp-3.2/config)
read -r -a PACKAGE_NAMES <<< "$EXPECTED_PACKAGES"
if (( ${#DEBS[@]} != ${#PACKAGE_NAMES[@]} )); then
    echo "Expected ${#PACKAGE_NAMES[@]} GIMP family packages in $DEB_DIR" >&2
    exit 1
fi
mkdir -p "$FRAMEWORK_DIR/build"
if [[ -n "${GIMP_TEST_CONTEXT:-}" ]]; then
    CONTEXT="$GIMP_TEST_CONTEXT"
    if [[ ! -d "$CONTEXT/debs" || $(stat -c '%u' "$CONTEXT") != "$EUID" ]]; then
        echo "Test context must exist and be owned by your host user: $CONTEXT" >&2
        exit 1
    fi
else
    CONTEXT=$(mktemp -d "$FRAMEWORK_DIR/build/gimp-install-XXXXXX")
fi
mkdir -p "$CONTEXT/debs"
for FILE in Dockerfile smoke.py smoke.sh audit.py sdk-test.c; do
    cp "$FRAMEWORK_DIR/tests/gimp-3.2/$FILE" "$CONTEXT/"
done
# All language archives are checked during packaging. English exercises actual
# help installation here without copying every translation into each test image.
for PACKAGE_FILE in "${DEBS[@]}"; do
    PACKAGE_NAME=$(dpkg-deb --field "$PACKAGE_FILE" Package)
    case "$PACKAGE_NAME" in
        gimp-help-common|gimp-help-en) cp --reflink=auto "$PACKAGE_FILE" "$CONTEXT/debs/" ;;
        gimp-help-*) ;;
        *) cp --reflink=auto "$PACKAGE_FILE" "$CONTEXT/debs/" ;;
    esac
done
printf 'Preserved installation test context: %s\n' "$CONTEXT"
TAG=${CONTEXT##*/}
if [[ "$TARGET" == all || "$TARGET" == clean ]]; then
    run_logged "$CONTEXT/clean.log" 30m docker build --progress=plain --target clean \
        -t "private-apt-gimp-test:clean-$TAG" "$CONTEXT"
fi
if [[ "$TARGET" == all || "$TARGET" == reinstall ]]; then
    run_logged "$CONTEXT/reinstall.log" 30m docker build --progress=plain --target reinstall \
        -t "private-apt-gimp-test:reinstall-$TAG" "$CONTEXT"
fi
