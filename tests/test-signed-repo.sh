#!/bin/bash
# Verify a real signature and install selection without changing the host's APT state.
set -Eeuo pipefail
umask 022

export FRAMEWORK_DIR="$PWD"
if [[ ! -f "$FRAMEWORK_DIR/update.sh" || ! -d "$FRAMEWORK_DIR/packages" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi
mkdir -p "$FRAMEWORK_DIR/build"
WORK_DIR=$(mktemp -d "$FRAMEWORK_DIR/build/signed-test-XXXXXX")
mkdir -p "$WORK_DIR/tmp"
export TMPDIR="$WORK_DIR/tmp"

export GNUPGHOME="$WORK_DIR/keyring"
export REPO_DIR="$WORK_DIR/repo"
export PACKAGES_DIR="$WORK_DIR/streams"
export CODENAME=trixie
export ARCHES='amd64 arm64'

CLIENT_DIR="$WORK_DIR/client"
APT_OPTIONS=()

cleanup() {
    gpgconf --homedir "$GNUPGHOME" --kill gpg-agent >/dev/null 2>&1 || true
    rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

create_signing_key() {
    mkdir -m 700 "$GNUPGHOME"
    gpg --batch --pinentry-mode loopback --passphrase '' \
        --quick-generate-key 'Repository test <test@localhost>' ed25519 sign 1d

    GPG_KEY=$(
        gpg --batch --with-colons --list-secret-keys |
            awk -F: '$1 == "fpr" { print $10; exit }'
    )
    export GPG_KEY
}

create_stream() {
    local STREAM="$1"
    local VERSION="$2"
    local STREAM_DIR="$PACKAGES_DIR/$STREAM"

    mkdir -p "$STREAM_DIR"
    cp "$FRAMEWORK_DIR/tests/fixtures/stream/query" "$STREAM_DIR/query"
    cp "$FRAMEWORK_DIR/tests/fixtures/stream/build" "$STREAM_DIR/build"
    chmod 755 "$STREAM_DIR/query" "$STREAM_DIR/build"

    printf 'RELEASE_STREAM=%s\nBINARY_PACKAGES=gimp\n' "$STREAM" > "$STREAM_DIR/config"
    printf '%s\n' "$VERSION" > "$STREAM_DIR/upstream-version"
}

prepare_apt_client() {
    mkdir -p "$CLIENT_DIR/lists/partial"
    mkdir -p "$CLIENT_DIR/cache/archives/partial"
    mkdir -p "$CLIENT_DIR/log"
    touch "$CLIENT_DIR/status"

    gpg --batch --export "$GPG_KEY" > "$CLIENT_DIR/key.gpg"
    printf 'deb [signed-by=%s/key.gpg] file:%s trixie main\n' \
        "$CLIENT_DIR" "$REPO_DIR" > "$CLIENT_DIR/sources.list"

    # These options redirect all APT reads and writes to the test directory.
    APT_OPTIONS=(
        -o "Dir::Etc::sourcelist=$CLIENT_DIR/sources.list"
        -o 'Dir::Etc::sourceparts=-'
        -o 'Dir::Etc::parts=-'
        -o 'Dir::Etc::main=/dev/null'
        -o "Dir::State=$CLIENT_DIR"
        -o "Dir::State::status=$CLIENT_DIR/status"
        -o "Dir::State::lists=$CLIENT_DIR/lists"
        -o "Dir::Cache=$CLIENT_DIR/cache"
        -o "Dir::Log=$CLIENT_DIR/log"
        -o 'APT::Architecture=amd64'
        -o "APT::Sandbox::User=$(id -un)"
    )
}

verify_available_versions() {
    local AVAILABLE VERSION

    apt-get "${APT_OPTIONS[@]}" update
    AVAILABLE=$(apt-cache "${APT_OPTIONS[@]}" show gimp)

    for VERSION in 3.2.1-1 3.4.0-1; do
        grep -Fx "Version: $VERSION" <<< "$AVAILABLE"
        apt-get "${APT_OPTIONS[@]}" --simulate install "gimp=$VERSION"
    done
}

create_signing_key
create_stream gimp-3.2 3.2.1
create_stream gimp-3.4 3.4.0
bash "$FRAMEWORK_DIR/update.sh"
prepare_apt_client
verify_available_versions

echo 'Signed repository test passed: both streams are visible and selectable.'
