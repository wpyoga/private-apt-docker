#!/bin/bash
# GitHub mechanics only; adapters choose tags and exact asset names.
set -Eeuo pipefail

fetch_github_release() {
    local REPOSITORY=$1 RELEASE_FILE=$2
    curl -fLsS --retry 3 \
        -H 'Accept: application/vnd.github+json' \
        -H 'User-Agent: private-apt-publisher' \
        "https://api.github.com/repos/$REPOSITORY/releases/latest" -o "$RELEASE_FILE"
    if ! jq -e '.draft == false and .prerelease == false' "$RELEASE_FILE" >/dev/null; then
        echo "Expected a stable release: $REPOSITORY" >&2
        return 1
    fi
    if ! jq -e '.assets | type == "array" and all(.[]; type == "object")' "$RELEASE_FILE" >/dev/null; then
        echo "Invalid assets list: $REPOSITORY" >&2
        return 1
    fi
}

record_github_release_date() {
    local RELEASE_FILE=$1 DESTINATION=$2 RELEASE_DATE
    RELEASE_DATE=$(jq -r '.published_at // empty' "$RELEASE_FILE")
    if [[ -n "$RELEASE_DATE" ]]; then
        printf '%s\n' "$RELEASE_DATE" > "$DESTINATION"
    fi
}

select_github_asset() {
    local RELEASE_FILE=$1 ASSET_NAME=$2 COUNT ASSET
    COUNT=$(jq --arg NAME "$ASSET_NAME" '[.assets[] | select(.name == $NAME)] | length' "$RELEASE_FILE")
    if (( COUNT > 1 )); then
        echo "Duplicate release asset: $ASSET_NAME" >&2
        return 1
    fi
    if (( COUNT == 0 )); then
        return 0
    fi
    ASSET=$(jq -c --arg NAME "$ASSET_NAME" '.assets[] | select(.name == $NAME)' "$RELEASE_FILE")
    if ! jq -e '.digest | strings | length == 71 and test("^sha256:[0-9a-fA-F]{64}$")' <<< "$ASSET" >/dev/null; then
        echo "Missing or invalid SHA256 digest: $ASSET_NAME" >&2
        return 1
    fi
    if ! jq -e '.browser_download_url | strings | startswith("https://") and (test("\\s") | not)' <<< "$ASSET" >/dev/null; then
        echo "Invalid asset URL: $ASSET_NAME" >&2
        return 1
    fi
    printf '%s\n' "$ASSET"
}
