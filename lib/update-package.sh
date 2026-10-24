#!/bin/bash
set -Eeuo pipefail

stream=$1
workspace=$2
lib_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
adapter="$PACKAGES_DIR/$stream"

if [[ ! "$stream" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
    echo "Invalid stream directory: $stream" >&2
    exit 1
fi
for hook in query build; do
    if [[ ! -x "$adapter/$hook" ]]; then
        echo "[$stream] Missing executable hook: $hook" >&2
        exit 1
    fi
done
package=$(cat "$adapter/package-name")
if [[ ! "$package" =~ ^[a-z0-9][a-z0-9+.-]+$ ]]; then
    echo "[$stream] Invalid Debian package name: $package" >&2
    exit 1
fi

mkdir -p "$workspace"
echo "[$stream] Querying upstream"
"$adapter/query" "$workspace"
python3 "$lib_dir/validate-targets.py" "$workspace/targets.tsv" "$ARCHES"
python3 "$lib_dir/check-activity.py" "$adapter" "$workspace"
for arch in $ARCHES; do
    if ! awk -F '\t' -v arch="$arch" '
        $2 == arch { found = 1 }
        END { exit !found }
    ' "$workspace/targets.tsv"; then
        echo "WARNING: [$stream] No current upstream package for $arch; keeping existing packages" >&2
    fi
done

export PUBLISHER_STREAM="$stream"
BUILD_INPUTS_SHA256=$(python3 "$lib_dir/checksum.py" "$adapter")
export BUILD_INPUTS_SHA256
python3 "$lib_dir/package-files.py" resolve "$adapter" "$workspace/targets.tsv" "$BUILD_INPUTS_SHA256"

while IFS=$'\t' read -r version arch existing; do
    if [[ -n "$existing" ]]; then
        echo "[$stream] Already stored: $package $version ($arch)"
        continue
    fi
    output="$workspace/${package}_${version}_${arch}.deb"
    echo "[$stream] Building $package $version ($arch)"
    "$adapter/build" "$workspace" "$version" "$arch" "$output"
    python3 "$lib_dir/package-files.py" store "$adapter" "$version" "$arch" "$BUILD_INPUTS_SHA256" "$output"
    echo "[$stream] Stored: $package $version ($arch)"
done < "$workspace/builds.tsv"
