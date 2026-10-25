#!/bin/bash
# Parse adapter configuration as data; never execute its contents.
set -Eeuo pipefail

config=$1/config
release_stream=
binary_packages=
declare -A seen=()
[[ -f "$config" ]] || { echo "Missing config: $config" >&2; exit 1; }
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *=* ]] || { echo "Invalid config line: $line" >&2; exit 1; }
    key=${line%%=*}
    value=${line#*=}
    [[ "$key" == release_stream || "$key" == binary_packages ]] || {
        echo "Unknown config key: $key" >&2; exit 1;
    }
    [[ ! -v seen[$key] ]] || { echo "Duplicate config key: $key" >&2; exit 1; }
    seen[$key]=1
    if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then
        value=${value:1:${#value}-2}
    fi
    printf -v "$key" '%s' "$value"
done < "$config"
[[ "$release_stream" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || {
    echo 'Invalid or missing release_stream' >&2; exit 1;
}
read -r -a packages <<< "$binary_packages"
(( ${#packages[@]} > 0 )) || { echo 'Missing binary_packages' >&2; exit 1; }
declare -A names=()
for package in "${packages[@]}"; do
    [[ "$package" =~ ^[a-z0-9][a-z0-9+.-]+$ && ! -v names[$package] ]] || {
        echo "Invalid or duplicate binary package: $package" >&2; exit 1;
    }
    names[$package]=1
done
printf '%s\n' "$release_stream" "${packages[*]}"
