#!/bin/bash
# Optional real amd64 package installation test. All installs stay in containers.
set -Eeuo pipefail
shopt -s nullglob

export FRAMEWORK_DIR="$PWD"
if [[ ! -d "$FRAMEWORK_DIR/tests/gimp" ]]; then
    echo 'Run tests from the project root.' >&2
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
CONTEXT=$(mktemp -d "$FRAMEWORK_DIR/build/gimp-install-XXXXXX")
mkdir -p "$CONTEXT/debs"
cp "$FRAMEWORK_DIR/tests/gimp/"* "$CONTEXT/"
# All language archives are checked during packaging. English exercises actual
# help installation here without copying every translation into each test image.
for PACKAGE_FILE in "${DEBS[@]}"; do
    PACKAGE_NAME=$(dpkg-deb --field "$PACKAGE_FILE" Package)
    case "$PACKAGE_NAME" in
        gimp-help-common|gimp-help-en) cp "$PACKAGE_FILE" "$CONTEXT/debs/" ;;
        gimp-help-*) ;;
        *) cp "$PACKAGE_FILE" "$CONTEXT/debs/" ;;
    esac
done
printf 'Preserved installation test context: %s\n' "$CONTEXT"
TAG=${CONTEXT##*/}
docker build --progress=plain --no-cache --target clean \
    -t "private-apt-gimp-test:clean-$TAG" "$CONTEXT"
docker build --progress=plain --target reinstall \
    -t "private-apt-gimp-test:reinstall-$TAG" "$CONTEXT"
