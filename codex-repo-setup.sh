#!/bin/bash
set -Eeuo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

: "${REPO_USER:=codexrepo}"
: "${REPO_DATA_DIR:=/srv/apt/codex}"
BASEDIR=$(realpath -m -- "$REPO_DATA_DIR")
: "${GPG_KEY_NAME:=Private APT Repository <repo@localhost>}"
: "${GPG_KEY_TYPE:=ed25519}"
: "${GPG_KEY_VALIDITY:=20y}"

if ! id "$REPO_USER" >/dev/null 2>&1; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$REPO_USER"
fi
repo_uid=$(id -u "$REPO_USER")
repo_gid=$(id -g "$REPO_USER")
sudo install -d -o "$repo_uid" -g "$repo_gid" -m 755 "$BASEDIR" "$BASEDIR/repo"
sudo install -d -o "$repo_uid" -g "$repo_gid" -m 700 "$BASEDIR/gnupg"

list_keys() {
    sudo -u "$REPO_USER" gpg --batch --homedir "$BASEDIR/gnupg" \
        --list-secret-keys --with-colons "${@}"
}

keys=$(list_keys)
if ! awk -F: '$1 == "sec" { found = 1 } END { exit !found }' <<< "$keys"; then
    sudo -u "$REPO_USER" gpg --batch --homedir "$BASEDIR/gnupg" \
        --pinentry-mode loopback --passphrase "" \
        --quick-generate-key "$GPG_KEY_NAME" "$GPG_KEY_TYPE" sign "$GPG_KEY_VALIDITY"
    keys=$(list_keys)
fi
if [[ -n "${GPG_KEY:-}" ]]; then
    keys=$(list_keys "$GPG_KEY")
fi
# Select primary fingerprints only; signing subkeys have their own fpr records.
mapfile -t fingerprints < <(awk -F: '
    $1 == "sec" { primary = 1; next }
    primary && $1 == "fpr" { print $10; primary = 0 }
' <<< "$keys")
if (( ${#fingerprints[@]} != 1 )); then
    echo 'Expected one primary secret key; set GPG_KEY explicitly to select an existing key' >&2
    exit 1
fi
fingerprint=${fingerprints[0]}
python3 "$script_dir/lib/write-env.py" .env "$repo_uid" "$repo_gid" "$fingerprint"
sudo -u "$REPO_USER" gpg --batch --homedir "$BASEDIR/gnupg" \
    --armor --export "$fingerprint" > repo-pubkey.asc
chmod 644 repo-pubkey.asc

printf 'Setup complete. Public key: %s/repo-pubkey.asc\n' "$script_dir"
printf 'Signing-key fingerprint: %s\n' "$fingerprint"
printf 'Start the publisher with: docker compose up -d --build\n'
