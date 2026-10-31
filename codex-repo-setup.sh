#!/bin/bash
set -Eeuo pipefail
umask 077

# Host entry points run from the project root; hooks receive this context.
export FRAMEWORK_DIR="${FRAMEWORK_DIR:-$PWD}"
cd "$FRAMEWORK_DIR"

# Setup reads the one operator-owned config file; missing files are an error.
set -a
source "$FRAMEWORK_DIR/.env"
set +a

: "${REPO_USER:?REPO_USER must be set and non-empty}"
: "${REPACK_GNUPG_DIR:?REPACK_GNUPG_DIR must be set and non-empty}"
: "${REBUILD_GNUPG_DIR:?REBUILD_GNUPG_DIR must be set and non-empty}"
: "${REPACK_REPO_DIR:?REPACK_REPO_DIR must be set and non-empty}"
: "${REBUILD_REPO_DIR:?REBUILD_REPO_DIR must be set and non-empty}"
: "${MAINTAINER:?MAINTAINER must be set and non-empty}"
: "${REPO_NAME:?REPO_NAME must be set and non-empty}"
: "${GPG_KEY_NAME:?GPG_KEY_NAME must be set and non-empty}"
: "${GPG_KEY_TYPE:?GPG_KEY_TYPE must be set and non-empty}"
: "${GPG_KEY_VALIDITY:?GPG_KEY_VALIDITY must be set and non-empty}"

if [[ "$(realpath -m -- "$REPACK_GNUPG_DIR")" == "$(realpath -m -- "$REBUILD_GNUPG_DIR")" ]]; then
    echo 'REPACK_GNUPG_DIR and REBUILD_GNUPG_DIR must be different directories' >&2
    exit 1
fi
if [[ "$(realpath -m -- "$REPACK_REPO_DIR")" == "$(realpath -m -- "$REBUILD_REPO_DIR")" ]]; then
    echo 'REPACK_REPO_DIR and REBUILD_REPO_DIR must be different directories' >&2
    exit 1
fi

# Build without Compose: setup has not written the UID/GID or key fingerprints yet.
docker build --tag private-apt-publisher:local "$FRAMEWORK_DIR"

if ! id "$REPO_USER" >/dev/null 2>&1; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$REPO_USER"
fi

REPO_UID=$(id -u "$REPO_USER")
REPO_GID=$(id -g "$REPO_USER")
sudo install -d -o "$REPO_UID" -g "$REPO_GID" -m 755 "$REPACK_REPO_DIR" "$REBUILD_REPO_DIR"

run_signing_gpg() {
    local SIGNING_DIR="$1"
    shift

    # GPG and its agent run only inside this temporary container. Docker stops
    # the agent when the command exits; its sockets never reach host storage.
    docker run --rm --init --network none \
        --user "$REPO_UID:$REPO_GID" \
        --cap-drop ALL --security-opt no-new-privileges:true \
        --mount "type=bind,src=$SIGNING_DIR,dst=/gnupg" \
        --tmpfs "/run/user/$REPO_UID:rw,noexec,nosuid,nodev,mode=0700,uid=$REPO_UID,gid=$REPO_GID" \
        --entrypoint /bin/bash private-apt-publisher:local -c '
            set -Eeuo pipefail
            source "$FRAMEWORK_DIR/lib/gnupg.sh"
            prepare_gnupg_socket_directory
            exec gpg "$@"
        ' bash "$@"
}

prepare_signing_key() {
    local REPOSITORY="$1" SIGNING_DIR="$2" SELECTED_KEY="$3"
    local KEYS
    local -a FINGERPRINTS

    sudo install -d -o "$REPO_UID" -g "$REPO_GID" -m 700 "$SIGNING_DIR"
    KEYS=$(run_signing_gpg "$SIGNING_DIR" --batch --list-secret-keys --with-colons)
    if ! awk -F: '$1 == "sec" { FOUND = 1 } END { exit !FOUND }' <<< "$KEYS"; then
        run_signing_gpg "$SIGNING_DIR" --batch \
            --pinentry-mode loopback --passphrase "" \
            --quick-generate-key "$GPG_KEY_NAME ($REPOSITORY)" "$GPG_KEY_TYPE" sign "$GPG_KEY_VALIDITY"
    fi
    local -a SELECTION=()
    if [[ -n "$SELECTED_KEY" ]]; then
        SELECTION=("$SELECTED_KEY")
    fi
    KEYS=$(run_signing_gpg "$SIGNING_DIR" --batch \
        --list-secret-keys --with-colons "${SELECTION[@]}")
    mapfile -t FINGERPRINTS < <(awk -F: '
        $1 == "sec" { IS_PRIMARY = 1; next }
        IS_PRIMARY && $1 == "fpr" { print $10; IS_PRIMARY = 0 }
    ' <<< "$KEYS")
    if (( ${#FINGERPRINTS[@]} != 1 )); then
        echo "$REPOSITORY: expected one primary secret key in $SIGNING_DIR; set its GPG_KEY explicitly" >&2
        return 1
    fi
    FINGERPRINT=${FINGERPRINTS[0]}
    run_signing_gpg "$SIGNING_DIR" --batch \
        --armor --export "$FINGERPRINT" > "$REPOSITORY-pubkey.asc"
    chmod 644 "$REPOSITORY-pubkey.asc"
    printf '%s signing-key fingerprint: %s\n' "$REPOSITORY" "$FINGERPRINT"
}

prepare_signing_key repack "$REPACK_GNUPG_DIR" "${REPACK_GPG_KEY:-}"
REPACK_GPG_KEY="$FINGERPRINT"
prepare_signing_key rebuild "$REBUILD_GNUPG_DIR" "${REBUILD_GPG_KEY:-}"
REBUILD_GPG_KEY="$FINGERPRINT"
if [[ "$REPACK_GPG_KEY" == "$REBUILD_GPG_KEY" ]]; then
    echo 'Repack and rebuild must use independently generated signing keys' >&2
    exit 1
fi

# Preserve the operator's settings and replace only the three setup outputs.
# mktemp creates a private file; rename it after the complete update succeeds.
ENV_FILE=$(mktemp "$FRAMEWORK_DIR/.env-XXXXXX")
trap 'rm -f -- "$ENV_FILE"' EXIT
awk '
    /^[[:space:]]*(export[[:space:]]+)?(REPO_UID|REPO_GID|GPG_KEY|REPACK_GPG_KEY|REBUILD_GPG_KEY)[[:space:]]*=/ { next }
    { print }
' "$FRAMEWORK_DIR/.env" > "$ENV_FILE"
printf 'REPO_UID=%s\nREPO_GID=%s\nREPACK_GPG_KEY=%s\nREBUILD_GPG_KEY=%s\n' \
    "$REPO_UID" "$REPO_GID" "$REPACK_GPG_KEY" "$REBUILD_GPG_KEY" >> "$ENV_FILE"
mv -- "$ENV_FILE" "$FRAMEWORK_DIR/.env"
printf 'Setup complete. Public keys: repack-pubkey.asc and rebuild-pubkey.asc\n'
printf 'Start the publisher with: docker compose up -d --build\n'
