#!/bin/bash
set -Eeuo pipefail
umask 022

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/repository.sh
source "$script_dir/lib/repository.sh"

export REPO_DIR=${REPO_DIR:-/repo}
export CODENAME=${CODENAME:-trixie}
export GNUPGHOME=${GNUPGHOME:-/gnupg}
export ARCHES=${ARCHES:-amd64 arm64}
export PACKAGES_DIR=${PACKAGES_DIR:-$script_dir/packages}
: "${PACKAGES:=codex}"
: "${GPG_KEY:?Missing GPG_KEY}"

publish_package() {
    local adapter=$1 workspace=$2
    local package version arch extra output listing
    local actual_name actual_version actual_arch
    local automatic_revisions=false
    package=$(cat "$PACKAGES_DIR/$adapter/package-name")
    mkdir -p "$workspace"

    echo "[$adapter] Querying updates"
    "$PACKAGES_DIR/$adapter/query" "$workspace"
    python3 "$script_dir/lib/validate-targets.py" "$workspace/targets.tsv" "$ARCHES"
    if [[ -f "$PACKAGES_DIR/$adapter/revision-policy" ]]; then
        if [[ "$(cat "$PACKAGES_DIR/$adapter/revision-policy")" != automatic ]]; then
            echo "[$adapter] Unknown revision policy" >&2
            return 1
        fi
        automatic_revisions=true
        python3 "$script_dir/lib/revisions.py" resolve "$PACKAGES_DIR/$adapter" "$workspace/targets.tsv"
        python3 "$script_dir/lib/validate-targets.py" "$workspace/targets.tsv" "$ARCHES"
    fi

    while IFS=$'\t' read -r version arch extra; do
        listing=$(reprepro -b "$REPO_DIR" list "$CODENAME" "$package")
        if awk -v arch="$arch" -v package="$package" -v version="$version" '
            $1 ~ ("\\|" arch ":$") && $2 == package && $3 == version { found = 1 }
            END { exit !found }
        ' <<< "$listing"; then
            if "$automatic_revisions"; then
                python3 "$script_dir/lib/revisions.py" published "$PACKAGES_DIR/$adapter" "$version" "$arch"
            fi
            echo "[$adapter] Already published: $package $version ($arch)"
            continue
        fi

        output="$workspace/${package}_${version}_${arch}.deb"
        "$PACKAGES_DIR/$adapter/build" "$workspace" "$version" "$arch" "$output"
        actual_name=$(dpkg-deb -f "$output" Package)
        actual_version=$(dpkg-deb -f "$output" Version)
        actual_arch=$(dpkg-deb -f "$output" Architecture)
        if [[ "$actual_name" != "$package" || "$actual_version" != "$version" || "$actual_arch" != "$arch" ]]; then
            echo "[$adapter] Built package metadata does not match $package $version ($arch)" >&2
            return 1
        fi

        reprepro -b "$REPO_DIR" includedeb "$CODENAME" "$output"
        if "$automatic_revisions"; then
            python3 "$script_dir/lib/revisions.py" published "$PACKAGES_DIR/$adapter" "$version" "$arch"
        fi
        echo "[$adapter] Published: $package $version ($arch)"
    done < "$workspace/targets.tsv"
}

main() {
    local adapter package arch hook status=0
    local -a adapters architectures
    local -A seen_packages=() seen_adapters=()
    read -r -a adapters <<< "${PACKAGES//$'\n'/ }"
    read -r -a architectures <<< "${ARCHES//$'\n'/ }"
    if (( ${#adapters[@]} == 0 || ${#architectures[@]} == 0 )); then
        echo 'PACKAGES and ARCHES must not be empty' >&2
        return 1
    fi
    for arch in "${architectures[@]}"; do
        if [[ ! "$arch" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
            echo "Invalid architecture: $arch" >&2
            return 1
        fi
    done
    ARCHES="${architectures[*]}"
    for adapter in "${adapters[@]}"; do
        if [[ ! "$adapter" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
            echo "Invalid adapter: $adapter" >&2
            return 1
        fi
        for hook in query build; do
            if [[ ! -x "$PACKAGES_DIR/$adapter/$hook" ]]; then
                echo "Missing executable hook: $adapter/$hook" >&2
                return 1
            fi
        done
        package=$(cat "$PACKAGES_DIR/$adapter/package-name")
        if [[ ! "$package" =~ ^[a-z0-9][a-z0-9+.-]+$ ]]; then
            echo "Invalid package name: $package" >&2
            return 1
        fi
        if [[ -v seen_packages[$package] || -v seen_adapters[$adapter] ]]; then
            echo "Duplicate adapter or Debian package: $adapter ($package)" >&2
            return 1
        fi
        seen_packages[$package]=1
        seen_adapters[$adapter]=1
    done

    mkdir -p "$REPO_DIR/.state"
    exec 9>"$REPO_DIR/.state/update.lock"
    if ! flock -n 9; then
        echo 'Update already running'
        return 0
    fi
    initialize_repository
    work=$(mktemp -d)
    trap 'rm -rf -- "$work"' EXIT

    for adapter in "${adapters[@]}"; do
        # A fresh Bash process preserves errexit inside hooks and functions.
        if bash "$script_dir/update.sh" --package "$adapter" "$work/$adapter"; then
            echo "[$adapter] Update complete"
        else
            echo "[$adapter] Update failed; continuing with remaining packages" >&2
            status=1
        fi
    done
    if ! reprepro -b "$REPO_DIR" export "$CODENAME"; then
        status=1
    fi
    return "$status"
}

case "${1:-}" in
    --package)
        publish_package "$2" "$3"
        ;;
    '')
        main
        ;;
    *)
        echo "Usage: $0" >&2
        exit 2
        ;;
esac
