#!/bin/bash
# Verify a real signature and install selection without changing the host's APT state.
set -Eeuo pipefail
umask 022

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$project_dir/build"
work=$(mktemp -d "$project_dir/build/signed-test-XXXXXX")
mkdir -p "$work/tmp"
export TMPDIR="$work/tmp"

export GNUPGHOME="$work/keyring"
export REPO_DIR="$work/repo"
export PACKAGES_DIR="$work/streams"
export CODENAME=trixie
export ARCHES='amd64 arm64'

client_dir="$work/client"
apt_options=()

cleanup() {
    gpgconf --homedir "$GNUPGHOME" --kill gpg-agent >/dev/null 2>&1 || true
    rm -rf -- "$work"
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
    local stream=$1
    local version=$2
    local stream_dir="$PACKAGES_DIR/$stream"

    mkdir -p "$stream_dir"
    cp "$project_dir/tests/fixtures/stream/query" "$stream_dir/query"
    cp "$project_dir/tests/fixtures/stream/build" "$stream_dir/build"
    chmod 755 "$stream_dir/query" "$stream_dir/build"

    printf '%s\n' gimp > "$stream_dir/package-name"
    printf '%s\n' "$version" > "$stream_dir/upstream-version"
}

prepare_apt_client() {
    mkdir -p "$client_dir/lists/partial"
    mkdir -p "$client_dir/cache/archives/partial"
    mkdir -p "$client_dir/log"
    touch "$client_dir/status"

    gpg --batch --export "$GPG_KEY" > "$client_dir/key.gpg"
    printf 'deb [signed-by=%s/key.gpg] file:%s trixie main\n' \
        "$client_dir" "$REPO_DIR" > "$client_dir/sources.list"

    # These options redirect all APT reads and writes to the test directory.
    apt_options=(
        -o "Dir::Etc::sourcelist=$client_dir/sources.list"
        -o 'Dir::Etc::sourceparts=-'
        -o 'Dir::Etc::parts=-'
        -o 'Dir::Etc::main=/dev/null'
        -o "Dir::State=$client_dir"
        -o "Dir::State::status=$client_dir/status"
        -o "Dir::State::lists=$client_dir/lists"
        -o "Dir::Cache=$client_dir/cache"
        -o "Dir::Log=$client_dir/log"
        -o 'APT::Architecture=amd64'
        -o "APT::Sandbox::User=$(id -un)"
    )
}

verify_available_versions() {
    local available version

    apt-get "${apt_options[@]}" update
    available=$(apt-cache "${apt_options[@]}" show gimp)

    for version in 3.2.1-1 3.4.0-1; do
        grep -Fx "Version: $version" <<< "$available"
        apt-get "${apt_options[@]}" --simulate install "gimp=$version"
    done
}

create_signing_key
create_stream gimp-3.2 3.2.1
create_stream gimp-3.4 3.4.0
bash "$project_dir/update.sh"
prepare_apt_client
verify_available_versions

echo 'Signed repository test passed: both streams are visible and selectable.'
