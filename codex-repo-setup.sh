#!/bin/bash
set -Eeuo pipefail
umask 077

: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must point to the framework root}"
export FRAMEWORK_DIR
cd "$FRAMEWORK_DIR"

# Setup reads the one operator-owned config file; missing files are an error.
set -a
source "$FRAMEWORK_DIR/.env"
set +a

: "${REPO_USER:?REPO_USER must be set and non-empty}"
: "${REPO_DATA_DIR:?REPO_DATA_DIR must be set and non-empty}"
: "${MAINTAINER:?MAINTAINER must be set and non-empty}"
: "${REPO_NAME:?REPO_NAME must be set and non-empty}"
BASE_DIR=$(realpath -m -- "$REPO_DATA_DIR")
: "${GPG_KEY_NAME:?GPG_KEY_NAME must be set and non-empty}"
: "${GPG_KEY_TYPE:?GPG_KEY_TYPE must be set and non-empty}"
: "${GPG_KEY_VALIDITY:?GPG_KEY_VALIDITY must be set and non-empty}"

if ! id "$REPO_USER" >/dev/null 2>&1; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$REPO_USER"
fi
REPO_UID=$(id -u "$REPO_USER")
REPO_GID=$(id -g "$REPO_USER")
sudo install -d -o "$REPO_UID" -g "$REPO_GID" -m 755 "$BASE_DIR" "$BASE_DIR/repo"
sudo install -d -o "$REPO_UID" -g "$REPO_GID" -m 700 "$BASE_DIR/gnupg"

list_keys() {
    sudo -u "$REPO_USER" gpg --batch --homedir "$BASE_DIR/gnupg" \
        --list-secret-keys --with-colons "$@"
}

KEYS=$(list_keys)
if ! awk -F: '$1 == "sec" { FOUND = 1 } END { exit !FOUND }' <<< "$KEYS"; then
    sudo -u "$REPO_USER" gpg --batch --homedir "$BASE_DIR/gnupg" \
        --pinentry-mode loopback --passphrase "" \
        --quick-generate-key "$GPG_KEY_NAME" "$GPG_KEY_TYPE" sign "$GPG_KEY_VALIDITY"
    KEYS=$(list_keys)
fi
if [[ -n "${GPG_KEY:-}" ]]; then
    KEYS=$(list_keys "$GPG_KEY")
fi
# Select primary fingerprints only; signing subkeys have their own fpr records.
mapfile -t FINGERPRINTS < <(awk -F: '
    $1 == "sec" { IS_PRIMARY = 1; next }
    IS_PRIMARY && $1 == "fpr" { print $10; IS_PRIMARY = 0 }
' <<< "$KEYS")
if (( ${#FINGERPRINTS[@]} != 1 )); then
    echo 'Expected one primary secret key; set GPG_KEY explicitly to select an existing key' >&2
    exit 1
fi
FINGERPRINT=${FINGERPRINTS[0]}
python3 "$FRAMEWORK_DIR/lib/write-env.py" .env "$REPO_UID" "$REPO_GID" "$FINGERPRINT"
sudo -u "$REPO_USER" gpg --batch --homedir "$BASE_DIR/gnupg" \
    --armor --export "$FINGERPRINT" > repo-pubkey.asc
chmod 644 repo-pubkey.asc

printf 'Setup complete. Public key: %s/repo-pubkey.asc\n' "$FRAMEWORK_DIR"
printf 'Signing-key fingerprint: %s\n' "$FINGERPRINT"
printf 'Start the publisher with: docker compose up -d --build\n'
