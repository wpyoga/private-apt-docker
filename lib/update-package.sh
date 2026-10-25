#!/bin/bash
set -Eeuo pipefail

adapter=$1
workspace=$2
lib_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
configuration=$(bash "$lib_dir/config.sh" "$adapter")
stream=${configuration%%$'\n'*}
export BINARY_PACKAGES=${configuration#*$'\n'}
export PUBLISHER_STREAM="$stream"

for hook in query build; do
    if [[ ! -x "$adapter/$hook" ]]; then
        echo "[$stream] Missing executable hook: $hook" >&2
        exit 1
    fi
done
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

BUILD_INPUTS_SHA256=$(python3 "$lib_dir/checksum.py" "$adapter")
export BUILD_INPUTS_SHA256
python3 "$lib_dir/package-files.py" resolve "$adapter" "$workspace/targets.tsv" "$BUILD_INPUTS_SHA256"

while IFS=$'\t' read -r version arch existing; do
    if [[ -n "$existing" ]]; then
        echo "[$stream] Already stored: $BINARY_PACKAGES $version ($arch)"
        continue
    fi
    output="$workspace/output-$arch"
    mkdir -p "$output"
    echo "[$stream] Building $BINARY_PACKAGES $version ($arch)"
    "$adapter/build" "$workspace" "$version" "$arch" "$output"
    python3 "$lib_dir/package-files.py" store "$adapter" "$version" "$arch" "$BUILD_INPUTS_SHA256" "$output"
    echo "[$stream] Stored: $BINARY_PACKAGES $version ($arch)"
done < "$workspace/builds.tsv"
