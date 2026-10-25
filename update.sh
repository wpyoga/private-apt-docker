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
: "${GPG_KEY:?Missing GPG_KEY}"

read -r -a architectures <<< "${ARCHES//$'\n'/ }"
if (( ${#architectures[@]} == 0 )); then
    echo 'ARCHES must not be empty' >&2
    exit 1
fi
for arch in "${architectures[@]}"; do
    case "$arch" in
        amd64|arm64) ;;
        *) echo "Unsupported architecture: $arch" >&2; exit 1 ;;
    esac
done
ARCHES="${architectures[*]}"
PACKAGES_DIR=$(cd -- "$PACKAGES_DIR" && pwd)

mkdir -p "$REPO_DIR/.state"
exec 9>"$REPO_DIR/.state/update.lock"
if ! flock -n 9; then
    echo 'Update already running'
    exit 0
fi
initialize_repository
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
status=0

declare -A seen_streams=()
shopt -s nullglob
for directory in "$PACKAGES_DIR"/*/; do
    if ! configuration=$(bash "$script_dir/lib/config.sh" "$directory"); then
        status=1
        continue
    fi
    stream=${configuration%%$'\n'*}
    if [[ -v seen_streams[$stream] ]]; then
        echo "Duplicate release_stream: $stream" >&2
        status=1
        continue
    fi
    seen_streams[$stream]=1
    # A fresh Bash process keeps each stream's failures isolated.
    if bash "$script_dir/lib/update-package.sh" "$directory" "$work/streams/$stream"; then
        echo "[$stream] Update complete"
    else
        echo "[$stream] Update failed; continuing with remaining streams" >&2
        status=1
    fi
done
if ! bash "$script_dir/lib/publish.sh" "$work/publication"; then
    echo 'Repository publication failed; retry next cycle' >&2
    status=1
fi
exit "$status"
