#!/bin/bash
# Run in the test container. Retain workspaces and downloads on failure.
set -Eeuo pipefail
umask 022

: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must be set and non-empty}"
: "${ARCHES:?ARCHES must be set and non-empty}"
export REPO_DIR=/test/repo GNUPGHOME=/test/gnupg
export MAINTAINER='Publisher Test <publisher@example.invalid>'
export REPO_NAME='Isolated publisher test'
export REPO_DESCRIPTION='Live GIMP adapter test'
export CODENAME=trixie REPO_ARCHITECTURES='amd64 arm64'
mkdir -p "$REPO_DIR/.state" "$REPO_DIR/pool" "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
exec 9>"$REPO_DIR/.state/update.lock"
flock -n 9

if ! gpg --batch --list-secret-keys publisher@example.invalid >/dev/null 2>&1; then
    gpg --batch --pinentry-mode loopback --passphrase '' \
        --quick-generate-key 'Publisher Test <publisher@example.invalid>' ed25519 sign 0
fi
GPG_KEY=$(gpg --batch --with-colons --list-secret-keys publisher@example.invalid \
    | awk -F: '$1 == "fpr" { print $10; exit }')
export GPG_KEY

STATUS=0
for STREAM in gimp-3.2 gimp-help-3.2; do
    export ADAPTER_DIR="$FRAMEWORK_DIR/packages/$STREAM"
    CONFIGURATION=$(bash "$FRAMEWORK_DIR/lib/config.sh")
    mapfile -t CONFIGURATION_LINES <<< "$CONFIGURATION"
    export PUBLISHER_STREAM="${CONFIGURATION_LINES[0]}"
    export BINARY_PACKAGES="${CONFIGURATION_LINES[1]}"
    export WORKSPACE="/test/workspaces/$STREAM"
    if bash "$FRAMEWORK_DIR/lib/update-package.sh"; then
        echo "[$STREAM] Update complete"
    else
        echo "[$STREAM] Update failed; continuing with remaining streams" >&2
        STATUS=1
    fi
done

if ! bash "$FRAMEWORK_DIR/lib/publish.sh" /test/publication; then
    STATUS=1
fi
gpg --batch --verify "$REPO_DIR/dists/$CODENAME/InRelease"

if (( STATUS == 0 )); then
    # Exercise the actual cycle runner too, reusing the completed test repository.
    find "$REPO_DIR/pool" -name '*.deb' -print0 | sort -z \
        | xargs -0 sha256sum > /test/before-resume.sha256
    PACKAGES_DIR=$(mktemp -d /test/repeat-adapters-XXXXXX)
    export PACKAGES_DIR
    for STREAM in gimp-3.2 gimp-help-3.2; do
        mkdir -p "$PACKAGES_DIR/$STREAM"
        cp -R --preserve=mode,timestamps \
            "$FRAMEWORK_DIR/packages/$STREAM/." "$PACKAGES_DIR/$STREAM/"
    done
    flock -u 9
    bash "$FRAMEWORK_DIR/update.sh"
    sha256sum --check /test/before-resume.sha256
    rm -r -- "$PACKAGES_DIR"
fi

for FILE in memory.peak memory.events pids.peak; do
    if [[ -r "/sys/fs/cgroup/$FILE" ]]; then
        cat "/sys/fs/cgroup/$FILE" > "/test/$FILE"
    fi
done
exit "$STATUS"
