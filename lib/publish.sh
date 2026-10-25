#!/bin/bash
set -Eeuo pipefail

: "${REPO_DIR:?REPO_DIR must be set and non-empty}"
: "${GPG_KEY:?GPG_KEY must be set and non-empty}"
: "${GNUPGHOME:?GNUPGHOME must be set and non-empty}"

STAGING_DIR="$1"
mkdir -p "$STAGING_DIR"
STAGING_DIR=$(cd -- "$STAGING_DIR" && pwd)
cd -- "$REPO_DIR"

for ARCHITECTURE in $REPO_ARCHITECTURES; do
    INDEX_DIR="$STAGING_DIR/main/binary-$ARCHITECTURE"
    mkdir -p "$INDEX_DIR"
    dpkg-scanpackages --multiversion --arch "$ARCHITECTURE" pool > "$INDEX_DIR/Packages"
    gzip -n -9 -c "$INDEX_DIR/Packages" > "$INDEX_DIR/Packages.gz"
done

apt-ftparchive \
    -o "APT::FTPArchive::Release::Origin=$REPO_ORIGIN" \
    -o "APT::FTPArchive::Release::Label=$REPO_LABEL" \
    -o "APT::FTPArchive::Release::Suite=$REPO_SUITE" \
    -o "APT::FTPArchive::Release::Codename=$CODENAME" \
    -o "APT::FTPArchive::Release::Architectures=$REPO_ARCHITECTURES" \
    -o 'APT::FTPArchive::Release::Components=main' \
    -o "APT::FTPArchive::Release::Description=$REPO_DESCRIPTION" \
    release "$STAGING_DIR" > "$STAGING_DIR.release"
mv -- "$STAGING_DIR.release" "$STAGING_DIR/Release"
printf '%s\n' 'Acquire-By-Hash: yes' >> "$STAGING_DIR/Release"

gpg --batch --yes --local-user "$GPG_KEY" \
    --armor --detach-sign --output "$STAGING_DIR/Release.gpg" "$STAGING_DIR/Release"
gpg --batch --yes --local-user "$GPG_KEY" \
    --clearsign --output "$STAGING_DIR/InRelease" "$STAGING_DIR/Release"

# All generation and signing must succeed before changing any live index.
install_metadata() {
    local SOURCE_FILE="$1"
    local DESTINATION_FILE="$2"
    local DESTINATION_DIR TEMPORARY_FILE

    DESTINATION_DIR=$(dirname -- "$DESTINATION_FILE")
    mkdir -p -- "$DESTINATION_DIR"
    TEMPORARY_FILE=$(mktemp "$DESTINATION_DIR/.metadata-XXXXXX")
    install -m 644 -- "$SOURCE_FILE" "$TEMPORARY_FILE"
    mv -f -- "$TEMPORARY_FILE" "$DESTINATION_FILE"
}

DISTRIBUTION_DIR="dists/$CODENAME"
for ARCHITECTURE in $REPO_ARCHITECTURES; do
    for INDEX_NAME in Packages Packages.gz; do
        SOURCE_FILE="$STAGING_DIR/main/binary-$ARCHITECTURE/$INDEX_NAME"
        INDEX_DIR="$DISTRIBUTION_DIR/main/binary-$ARCHITECTURE"
        # Keep old hashes so clients holding an older Release can finish fetching.
        for ALGORITHM in 256 512; do
            read -r DIGEST _ < <("sha${ALGORITHM}sum" "$SOURCE_FILE")
            install_metadata "$SOURCE_FILE" "$INDEX_DIR/by-hash/SHA$ALGORITHM/$DIGEST"
        done
        install_metadata "$SOURCE_FILE" "$INDEX_DIR/$INDEX_NAME"
    done
done
for INDEX_NAME in Release.gpg Release InRelease; do
    install_metadata "$STAGING_DIR/$INDEX_NAME" "$DISTRIBUTION_DIR/$INDEX_NAME"
done
echo "Published signed repository: $CODENAME"
